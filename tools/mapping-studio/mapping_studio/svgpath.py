"""Minimal, dependency-free SVG geometry reader.

Only what region auto-detection needs: the bounding box, curve count and winding
of every subpath in a document, in the document's own user units. No rendering,
no transforms beyond translate/scale/matrix on ancestor groups, no CSS.

Why not an SVG library: this ships next to a USB driver and gets run on a Pi
during a mapping session. A hard dependency on lxml or svgpathtools is a worse
trade than 200 lines of parser, and the input we care about (CAD line art and
hand-drawn panel art) uses a small, boring subset of the spec.

Bounding boxes use path *endpoints* only, not Bezier control points. For the
shapes this module is looking for -- circles drawn as four cubics with knots on
the cardinal points, and rounded rectangles with knots at the tangent points --
the endpoint hull is the true bbox. Control points would inflate it.

SPDX-License-Identifier: MIT
"""

import math
import re

_TOKEN = re.compile(r"[MmLlHhVvCcSsQqTtAaZz]|-?\d*\.?\d+(?:[eE][-+]?\d+)?")
_TAG = re.compile(r"<(/?)([a-zA-Z][\w:-]*)((?:\s+[\w:-]+\s*=\s*(?:\"[^\"]*\"|'[^']*'))*)\s*(/?)>")
_ATTR = re.compile(r"([\w:-]+)\s*=\s*(?:\"([^\"]*)\"|'([^']*)')")
_NUM = re.compile(r"-?\d*\.?\d+(?:[eE][-+]?\d+)?")


class SubPath:
    """One M...Z run of a path, reduced to the facts a detector needs."""

    __slots__ = ("pts", "curves", "closed", "fill", "stroke", "tag")

    def __init__(self, pts, curves, closed, fill, stroke, tag):
        self.pts = pts
        self.curves = curves
        self.closed = closed
        self.fill = fill
        self.stroke = stroke
        self.tag = tag

    @property
    def bbox(self):
        xs = [p[0] for p in self.pts]
        ys = [p[1] for p in self.pts]
        return min(xs), min(ys), max(xs), max(ys)

    @property
    def size(self):
        x0, y0, x1, y1 = self.bbox
        return x1 - x0, y1 - y0

    @property
    def center(self):
        x0, y0, x1, y1 = self.bbox
        return (x0 + x1) / 2.0, (y0 + y1) / 2.0

    @property
    def area(self):
        w, h = self.size
        return w * h

    def __repr__(self):
        cx, cy = self.center
        w, h = self.size
        return f"<SubPath {self.tag} {w:.2f}x{h:.2f} @ {cx:.2f},{cy:.2f} c={self.curves}>"


def _attrs(blob):
    out = {}
    for m in _ATTR.finditer(blob or ""):
        out[m.group(1)] = m.group(2) if m.group(2) is not None else m.group(3)
    return out


def _f(d, key, default=0.0):
    try:
        return float(str(d.get(key, default)).strip().rstrip("abcdefghijklmnopqrstuvwxyz%"))
    except (TypeError, ValueError):
        return default


def parse_transform(text):
    """Return a 6-tuple affine (a,b,c,d,e,f) for a transform attribute."""
    m = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    if not text:
        return m
    for name, args in re.findall(r"(\w+)\s*\(([^)]*)\)", text):
        v = [float(n) for n in _NUM.findall(args)]
        if name == "translate":
            t = (1.0, 0.0, 0.0, 1.0, v[0], v[1] if len(v) > 1 else 0.0)
        elif name == "scale":
            sx = v[0]
            sy = v[1] if len(v) > 1 else sx
            t = (sx, 0.0, 0.0, sy, 0.0, 0.0)
        elif name == "matrix" and len(v) >= 6:
            t = tuple(v[:6])
        elif name == "rotate" and v:
            r = math.radians(v[0])
            t = (math.cos(r), math.sin(r), -math.sin(r), math.cos(r), 0.0, 0.0)
        else:
            continue
        m = _mul(m, t)
    return m


def _mul(m, n):
    a1, b1, c1, d1, e1, f1 = m
    a2, b2, c2, d2, e2, f2 = n
    return (
        a1 * a2 + c1 * b2,
        b1 * a2 + d1 * b2,
        a1 * c2 + c1 * d2,
        b1 * c2 + d1 * d2,
        a1 * e2 + c1 * f2 + e1,
        b1 * e2 + d1 * f2 + f1,
    )


def _apply(m, x, y):
    a, b, c, d, e, f = m
    return a * x + c * y + e, b * x + d * y + f


def parse_path(d):
    """Split a path 'd' string into (points, curve_count, closed) subpaths."""
    toks = _TOKEN.findall(d or "")
    subs = []
    pts, curves, closed = [], 0, False
    cmd = None
    x = y = 0.0
    sx = sy = 0.0
    i = 0

    def flush():
        nonlocal pts, curves, closed
        if len(pts) >= 2:
            subs.append((pts, curves, closed))
        pts, curves, closed = [], 0, False

    while i < len(toks):
        t = toks[i]
        if t.isalpha():
            cmd = t
            i += 1
            if cmd in "Zz":
                closed = True
                if pts:
                    x, y = sx, sy
                    pts.append((x, y))
                flush()
                continue
        if cmd is None:
            i += 1
            continue
        rel = cmd.islower()
        c = cmd.upper()
        try:
            if c == "M":
                nx, ny = float(toks[i]), float(toks[i + 1])
                i += 2
                x, y = (x + nx, y + ny) if rel else (nx, ny)
                flush()
                sx, sy = x, y
                pts.append((x, y))
                cmd = "l" if rel else "L"  # implicit lineto for repeats
            elif c == "L":
                nx, ny = float(toks[i]), float(toks[i + 1])
                i += 2
                x, y = (x + nx, y + ny) if rel else (nx, ny)
                pts.append((x, y))
            elif c == "H":
                nx = float(toks[i])
                i += 1
                x = x + nx if rel else nx
                pts.append((x, y))
            elif c == "V":
                ny = float(toks[i])
                i += 1
                y = y + ny if rel else ny
                pts.append((x, y))
            elif c == "C":
                nx, ny = float(toks[i + 4]), float(toks[i + 5])
                i += 6
                x, y = (x + nx, y + ny) if rel else (nx, ny)
                pts.append((x, y))
                curves += 1
            elif c in ("S", "Q"):
                nx, ny = float(toks[i + 2]), float(toks[i + 3])
                i += 4
                x, y = (x + nx, y + ny) if rel else (nx, ny)
                pts.append((x, y))
                curves += 1
            elif c == "T":
                nx, ny = float(toks[i]), float(toks[i + 1])
                i += 2
                x, y = (x + nx, y + ny) if rel else (nx, ny)
                pts.append((x, y))
                curves += 1
            elif c == "A":
                nx, ny = float(toks[i + 5]), float(toks[i + 6])
                i += 7
                x, y = (x + nx, y + ny) if rel else (nx, ny)
                pts.append((x, y))
                curves += 1
            else:
                i += 1
        except (IndexError, ValueError):
            break
    flush()
    return subs


class Document:
    """A parsed SVG: its user-unit viewport, subpaths and text runs."""

    def __init__(self, width, height, subpaths, texts):
        self.width = width
        self.height = height
        self.subpaths = subpaths
        self.texts = texts


def _length(v, default):
    if v is None:
        return default
    m = _NUM.search(str(v))
    return float(m.group(0)) if m else default


def load(path):
    """Parse an SVG file into a Document. Text is returned with its anchor point."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        src = fh.read()
    return loads(src)


def loads(src):
    width = height = 0.0
    root = _TAG.search(src)
    if root:
        a = _attrs(root.group(3))
        vb = a.get("viewBox")
        if vb:
            v = [float(n) for n in _NUM.findall(vb)]
            if len(v) == 4:
                width, height = v[2], v[3]
        width = width or _length(a.get("width"), 0.0)
        height = height or _length(a.get("height"), 0.0)

    subpaths = []
    texts = []
    stack = [(1.0, 0.0, 0.0, 1.0, 0.0, 0.0)]
    pos = 0
    pending_text = None

    for m in _TAG.finditer(src):
        closing, tag, blob, selfclose = m.group(1), m.group(2), m.group(3), m.group(4)
        a = _attrs(blob)
        ctm = stack[-1]

        if tag == "text" and not closing:
            body = src[m.end():]
            end = body.find("</text>")
            raw = body[:end] if end >= 0 else ""
            txt = re.sub(r"<[^>]*>", " ", raw)
            txt = re.sub(r"\s+", " ", txt).strip()
            if txt:
                tx, ty = _apply(_mul(ctm, parse_transform(a.get("transform"))),
                                _f(a, "x"), _f(a, "y"))
                texts.append({"text": txt, "x": tx, "y": ty,
                              "size": _f(a, "font-size", 0.0)})
            continue

        if closing:
            if tag in ("g", "svg", "a") and len(stack) > 1:
                stack.pop()
            continue

        local = _mul(ctm, parse_transform(a.get("transform")))

        if tag in ("g", "svg", "a"):
            if not selfclose:
                stack.append(local)
            continue

        fill = a.get("fill", "")
        stroke = a.get("stroke", "")

        if tag == "path":
            for pts, curves, closed in parse_path(a.get("d", "")):
                tp = [_apply(local, px, py) for px, py in pts]
                subpaths.append(SubPath(tp, curves, closed, fill, stroke, "path"))
        elif tag == "rect":
            x, y = _f(a, "x"), _f(a, "y")
            w, h = _f(a, "width"), _f(a, "height")
            if w > 0 and h > 0:
                corners = [(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]
                tp = [_apply(local, px, py) for px, py in corners]
                rx = _f(a, "rx") or _f(a, "ry")
                subpaths.append(SubPath(tp, 4 if rx else 0, True, fill, stroke, "rect"))
        elif tag in ("circle", "ellipse"):
            cx, cy = _f(a, "cx"), _f(a, "cy")
            if tag == "circle":
                rx = ry = _f(a, "r")
            else:
                rx, ry = _f(a, "rx"), _f(a, "ry")
            if rx > 0 and ry > 0:
                knots = [(cx, cy - ry), (cx + rx, cy), (cx, cy + ry), (cx - rx, cy), (cx, cy - ry)]
                tp = [_apply(local, px, py) for px, py in knots]
                subpaths.append(SubPath(tp, 4, True, fill, stroke, tag))

    return Document(width, height, subpaths, texts)
