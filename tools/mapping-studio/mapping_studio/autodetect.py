"""First-pass region detection: panel artwork in, candidate controls out.

The tool is useless if a human has to hand-place a hit region for all ~90
controls on a mixer before mapping even starts. This module does that pass
automatically and leaves a human to correct it, which is a much shorter job
than drawing them.

Detection is geometric, not semantic. Panel art -- whether CAD line art lifted
from a manual or a drawing someone made -- encodes controls as a small,
repetitive vocabulary of shapes: circles for rotaries, rounded rectangles for
buttons, long thin slots for faders. Those are separable by size and aspect
alone, with two refinements that carry most of the accuracy:

  * Concentric clustering. Art almost always draws a control as several nested
    outlines (a knob cap plus its skirt, a button aperture plus its bezel). Left
    alone that yields three candidates per control. Shapes sharing a centre are
    merged, and the *number* merged is itself evidence: a lone stray line is
    probably decoration, three concentric rings is almost certainly a control.

  * Modal sizing. Real panels reuse a handful of part sizes. Once every
    candidate is measured, sizes that recur across the panel are promoted and
    one-off sizes are demoted, which is what separates twenty real knobs from
    the stray circle in a logo.

Everything emitted is provisional and carries a confidence and the evidence
behind it, because a wrong region that looks confident costs more than a
missing one.

SPDX-License-Identifier: MIT
"""

import json
import math
import re
from collections import Counter, defaultdict

from . import svgpath

# Shape families, in the units of the source document (millimetres for a 1:1
# panel drawing). Generous bands: the modal-size pass does the real narrowing.
DEFAULTS = {
    # Tier A -- things a finger operates. Both dimensions have to be big enough
    # to touch, which alone removes outlined glyphs and hairline rules.
    "min_dim": 4.6,
    "max_size": 90.0,
    "max_aspect": 12.0,
    "corner_curves": (0, 4, 8),  # a box or a rounded box; glyphs use 2,3,5,6...

    # Tier B -- indicators. Too small to be controls, only admitted when many
    # identical copies appear, which is what a meter ladder or LED row looks like.
    "indicator_min_dim": 1.4,
    "indicator_min_area": 4.0,
    "indicator_recurrence": 4,

    "cluster_tol": 1.2,      # centres this close are the same control
    "circle_aspect": 0.18,   # |w-h|/w below this is "round"
    "slot_aspect": 2.8,      # length/width above this is "slot-like"
    "min_slot_len": 20.0,
    "label_radius": 14.0,    # how far to look for a naming label
}


class Candidate:
    __slots__ = ("cx", "cy", "w", "h", "shape", "rings", "kind", "label",
                 "confidence", "why", "members", "tier")

    def __init__(self, cx, cy, w, h, shape, rings, members, tier="control"):
        self.cx, self.cy, self.w, self.h = cx, cy, w, h
        self.shape = shape
        self.rings = rings
        self.members = members
        self.tier = tier
        self.kind = None
        self.label = None
        self.confidence = 0.0
        self.why = []

    @property
    def aspect(self):
        lo, hi = sorted((self.w, self.h))
        return hi / lo if lo > 0 else 999.0

    def to_dict(self, ident):
        d = {
            "id": ident,
            "label": self.label or ident.replace("_", " ").upper(),
            "kind": self.kind,
            "provisional": True,
            "confidence": round(self.confidence, 3),
            "evidence": self.why,
            "tier": self.tier,
        }
        if self.shape == "circle":
            d["shape"] = {
                "type": "circle",
                "cx": round(self.cx, 3),
                "cy": round(self.cy, 3),
                "d": round((self.w + self.h) / 2.0, 3),
            }
        else:
            d["shape"] = {
                "type": "rect",
                "cx": round(self.cx, 3),
                "cy": round(self.cy, 3),
                "w": round(self.w, 3),
                "h": round(self.h, 3),
                "round": self.shape == "rrect",
            }
        return d


def _classify_shape(sp, cfg):
    w, h = sp.size
    if w <= 0 or h <= 0:
        return None
    lo, hi = sorted((w, h))
    if sp.curves >= 3 and abs(w - h) <= cfg["circle_aspect"] * max(w, h):
        return "circle"
    if hi / lo >= cfg["slot_aspect"] and hi >= cfg["min_slot_len"]:
        return "slot"
    if sp.curves >= 1:
        return "rrect"
    return "rect"


def _cluster(cands, tol, tier="control"):
    """Merge shapes sharing a centre; the outermost survives, carrying a ring count."""
    buckets = defaultdict(list)
    for c in cands:
        buckets[(round(c["cx"] / tol), round(c["cy"] / tol))].append(c)

    # A shape can straddle a bucket edge, so grow each bucket by its neighbours
    # and then do an explicit distance check.
    used = set()
    out = []
    keys = sorted(buckets)
    for key in keys:
        pool = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                pool.extend(buckets.get((key[0] + dx, key[1] + dy), []))
        for seed in buckets[key]:
            if id(seed) in used:
                continue
            group = []
            for other in pool:
                if id(other) in used:
                    continue
                if math.hypot(other["cx"] - seed["cx"], other["cy"] - seed["cy"]) <= tol:
                    group.append(other)
            if not group:
                continue
            for g in group:
                used.add(id(g))
            outer = max(group, key=lambda g: g["w"] * g["h"])
            shapes = [g["shape"] for g in group]
            shape = "circle" if "circle" in shapes else (
                "slot" if "slot" in shapes else (
                    "rrect" if "rrect" in shapes else "rect"))
            out.append(Candidate(outer["cx"], outer["cy"], outer["w"], outer["h"],
                                 shape, len(group), group, tier))
    return out


def _modal_sizes(cands, quant=0.5):
    """Count how often each (shape, quantised size) recurs across the panel."""
    tally = Counter()
    for c in cands:
        tally[(c.shape, round(c.w / quant), round(c.h / quant))] += 1
    return tally


def _assign_kind(c):
    """Map geometry to a control kind. Deliberately coarse; the human fixes it."""
    if c.tier == "indicator":
        return "meter" if c.aspect >= 2.0 else "led"
    if c.shape == "circle":
        d = (c.w + c.h) / 2.0
        if d >= 45.0:
            return "jog"
        if d >= 20.0:
            return "encoder"
        if d >= 11.0:
            return "knob"
        if d >= 6.0:
            return "knob"
        return "led"
    if c.shape == "slot":
        return "fader"
    if c.shape in ("rrect", "rect"):
        area = c.w * c.h
        if area < 6.0:
            return "led"
        if c.aspect >= 2.2 and max(c.w, c.h) >= 18.0:
            return "fader"
        return "button"
    return "button"


def _slug(text, taken):
    s = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")
    s = s or "ctl"
    base, n = s, 2
    while s in taken:
        s = f"{base}_{n}"
        n += 1
    taken.add(s)
    return s


def _attach_labels(cands, texts, cfg):
    """Name each candidate from the nearest plausible label.

    A panel label sits *outside* the control it names -- usually directly above
    or below it -- so this scores by distance with a bias toward text that is
    vertically adjacent and horizontally centred, and refuses text that sits
    inside a different, closer candidate.
    """
    if not texts:
        return
    radius = cfg["label_radius"]
    for c in cands:
        best, best_score = None, 1e9
        for t in texts:
            dx = abs(t["x"] - c.cx)
            dy = t["y"] - c.cy
            dist = math.hypot(dx, dy)
            if dist > radius:
                continue
            # prefer text just above (negative dy) or just below, well centred
            score = dist + 0.6 * dx + (0.0 if abs(dy) > c.h / 2 else 3.0)
            if score < best_score:
                best, best_score = t, score
        if best is not None:
            # refuse the label if some other candidate is a clearly better owner
            contested = False
            for other in cands:
                if other is c:
                    continue
                if math.hypot(best["x"] - other.cx, best["y"] - other.cy) < \
                        math.hypot(best["x"] - c.cx, best["y"] - c.cy) - 0.5:
                    contested = True
                    break
            if not contested:
                c.label = best["text"]
                c.why.append(f"label {best['text']!r} at {best_score:.1f}")


def detect(svg_path, labels=None, config=None, panel=None):
    """Detect candidate controls in an SVG panel drawing.

    labels: optional list of {text,x,y} in the same units as the drawing, for
    sources whose text was outlined into paths (common in PDF-derived art).
    Returns (panel_dict, [control_dict, ...]).
    """
    return _detect(svgpath.load(svg_path), labels, config, panel)


def detect_from_string(src, labels=None, config=None, panel=None):
    """Same as detect(), for SVG already in memory."""
    return _detect(svgpath.loads(src), labels, config, panel)


def _detect(doc, labels=None, config=None, panel=None):
    cfg = dict(DEFAULTS)
    cfg.update(config or {})

    texts = list(doc.texts)
    if labels:
        texts.extend(labels)

    raw_control, raw_indicator = [], []
    for sp in doc.subpaths:
        w, h = sp.size
        lo, hi = sorted((w, h))
        if lo <= 0 or hi > cfg["max_size"]:
            continue
        aspect = hi / lo
        shape = _classify_shape(sp, cfg)
        if shape is None:
            continue
        rec = {"cx": sp.center[0], "cy": sp.center[1], "w": w, "h": h, "shape": shape}
        if (lo >= cfg["min_dim"] and aspect <= cfg["max_aspect"]
                and sp.curves in cfg["corner_curves"]):
            raw_control.append(rec)
        elif (lo >= cfg["indicator_min_dim"] and w * h >= cfg["indicator_min_area"]
                and aspect <= cfg["max_aspect"] and sp.curves == 0):
            raw_indicator.append(rec)

    cands = _cluster(raw_control, cfg["cluster_tol"], "control")

    # Indicators are only believable en masse: a single 3 mm box is noise, a row
    # of eleven identical ones is a level meter.
    ind = _cluster(raw_indicator, cfg["cluster_tol"], "indicator")
    ind_modal = _modal_sizes(ind)
    cands.extend(c for c in ind
                 if ind_modal[(c.shape, round(c.w / 0.5), round(c.h / 0.5))]
                 >= cfg["indicator_recurrence"])

    # Drop candidates that merely enclose other candidates: group boxes, panel
    # sections and decorative frames all look like big rounded rectangles.
    keep = []
    for c in cands:
        inner = 0
        for o in cands:
            if o is c:
                continue
            if (abs(o.cx - c.cx) < c.w / 2 and abs(o.cy - c.cy) < c.h / 2
                    and o.w * o.h < c.w * c.h * 0.5):
                inner += 1
        if inner >= 3:
            continue
        keep.append(c)
    cands = keep

    modal = _modal_sizes(cands)
    for c in cands:
        c.kind = _assign_kind(c)
        recurrence = modal[(c.shape, round(c.w / 0.5), round(c.h / 0.5))]
        score = 0.30
        if c.rings >= 2:
            score += 0.25
            c.why.append(f"{c.rings} concentric outlines")
        if c.rings >= 3:
            score += 0.10
        if recurrence >= 2:
            score += 0.20
            c.why.append(f"size recurs {recurrence}x on panel")
        if recurrence >= 6:
            score += 0.10
        if c.shape == "circle":
            score += 0.05
        c.confidence = min(score, 0.99)

    _attach_labels(cands, texts, cfg)
    for c in cands:
        if c.label:
            c.confidence = min(c.confidence + 0.10, 0.99)

    cands.sort(key=lambda c: (round(c.cy, 1), round(c.cx, 1)))

    taken = set()
    controls = []
    for c in cands:
        ident = _slug(c.label or f"{c.kind}", taken)
        controls.append(c.to_dict(ident))

    panel_dict = panel or {
        "w": round(doc.width, 3),
        "h": round(doc.height, 3),
        "units": "mm",
    }
    return panel_dict, controls


def summarise(controls):
    """Human-readable breakdown, for the CLI and for eyeballing a first pass."""
    by_kind = Counter(c["kind"] for c in controls)
    named = sum(1 for c in controls if not c["label"].startswith(("KNOB", "BUTTON", "LED", "FADER", "ENCODER", "JOG")))
    lines = [f"{len(controls)} candidate regions"]
    for kind, n in by_kind.most_common():
        lines.append(f"  {kind:>8s}  {n}")
    lines.append(f"  labelled from artwork: {named}")
    hi = sum(1 for c in controls if c["confidence"] >= 0.7)
    lines.append(f"  confidence >= 0.70:    {hi}")
    return "\n".join(lines)


def load_labels(path):
    """Read a labels sidecar: a JSON list of {text,x,y}."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    out = []
    for d in data:
        if "text" in d and "x" in d and "y" in d:
            out.append({"text": d["text"], "x": float(d["x"]), "y": float(d["y"]),
                        "size": float(d.get("size", 0) or 0)})
    return out
