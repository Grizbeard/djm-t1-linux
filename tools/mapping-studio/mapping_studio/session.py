"""The mapping session: turning gestures and blinks into bindings.

Two loops run here, and they are mirror images of each other.

LEARN (input). You point at a control on screen, then move the physical one.
Everything that arrives in that window is attributed to it. The interesting part
is not capturing the messages but deciding which of them the control *is*, since
a single knob can produce several message streams at once.

PROBE (output). The studio lights one LED at a time and you say which region lit
by clicking it. This is the inverse of watching a blind 0..127 sweep and trying
to remember what happened, and it is ordered by prior probability rather than by
note number: on most gear a button's LED answers to the button's own note, so
every note already captured as a button input is tried first. On a panel where
that convention holds, the whole output map falls out in the first few dozen
sends instead of after 128 of them.

SPDX-License-Identifier: MIT
"""

import time
from collections import Counter, defaultdict

# A relative encoder parks on a couple of sentinel values (commonly 1 and 127,
# or 63/65) instead of sweeping. If nearly every message is one of a tiny set of
# values but there are many messages, it is counting, not positioning.
_REL_SENTINELS = ({1, 127}, {63, 65}, {1, 65}, {63, 127})


class CaptureResult:
    """What a learn window saw, and what the studio thinks it means."""

    def __init__(self, control_id, layer, events):
        self.control_id = control_id
        self.layer = layer
        self.events = events
        self.groups = []
        self.binding = None
        self.mirrors = []
        self.notes = []

    def to_dict(self):
        return {
            "control_id": self.control_id,
            "layer": self.layer,
            "event_count": len(self.events),
            "binding": self.binding,
            "groups": self.groups,
            "mirrors": self.mirrors,
            "notes": self.notes,
        }


def analyse(events, kind=None):
    """Reduce a burst of MIDI into a proposed binding plus what else was seen.

    Returns (binding, groups, mirrors, notes).
    """
    notes = []
    if not events:
        return None, [], [], ["nothing arrived"]

    buckets = defaultdict(list)
    for ev in events:
        if ev["status"] == "note_off":
            key = ("note", ev["channel"], ev["number"])
        elif ev["status"] == "note_on":
            key = ("note", ev["channel"], ev["number"])
        elif ev["status"] == "cc":
            key = ("cc", ev["channel"], ev["number"])
        elif ev["status"] == "pitch":
            key = ("pitch", ev["channel"], 0)
        else:
            continue
        buckets[key].append(ev)

    if not buckets:
        return None, [], [], ["no mappable messages (only clock or sysex?)"]

    groups = []
    for (status, channel, number), evs in buckets.items():
        values = [e["value"] for e in evs]
        distinct = set(values)
        g = {
            "status": status,
            "channel": channel,
            "number": number,
            "count": len(evs),
            "min": min(values),
            "max": max(values),
            "resting": values[-1],
            "distinct": len(distinct),
        }
        if status == "note":
            ons = sum(1 for e in evs if e["status"] == "note_on" and e["value"] > 0)
            g["presses"] = ons
        groups.append(g)
    groups.sort(key=lambda g: -g["count"])

    top = groups[0]
    status, channel, number = top["status"], top["channel"], top["number"]

    binding = {"status": status, "channel": channel, "number": number}

    if status == "note":
        binding["mode"] = "button"
        binding["press_value"] = max(
            (e["value"] for e in events
             if e["status"] == "note_on" and e["value"] > 0), default=127)
        if top["count"] >= 2 and top.get("presses", 0) >= 1:
            notes.append(
                "button sends a press and an immediate release; drive it on the "
                "press edge")
    else:
        vals = [e["value"] for e in events
                if e["status"] == "cc" and e["channel"] == channel
                and e["number"] == number]
        distinct = set(vals)
        relative = any(distinct and distinct.issubset(s) for s in _REL_SENTINELS)
        if not relative and len(vals) >= 8 and len(distinct) <= 3:
            relative = True
        if relative:
            binding["mode"] = "relative"
            binding["sentinels"] = sorted(distinct)
            notes.append(
                f"looks relative: {len(vals)} messages but only "
                f"{sorted(distinct)} as values")
        else:
            binding["mode"] = "absolute"
            binding["min"] = top["min"]
            binding["max"] = top["max"]
            binding["resting"] = top["resting"]
            if top["max"] - top["min"] < 40:
                notes.append(
                    f"only covered {top['min']}..{top['max']} -- sweep the full "
                    f"range for a trustworthy span")
            if kind in ("knob", "fader") and top["max"] < 120:
                notes.append("never reached the top of the range")

    # Anything else that fired at the same time is almost certainly the same
    # physical control reported twice. The DJM-T1's crossfader does exactly this,
    # and a mapping that binds the mirror by mistake drags an unrelated control.
    mirrors = []
    for g in groups[1:]:
        if g["count"] >= max(3, top["count"] * 0.4):
            mirrors.append(g)
    if mirrors:
        pretty = ", ".join(
            f"{m['status']} {m['number']} ({m['count']}x)" for m in mirrors)
        notes.append(
            f"this control also emitted {pretty} -- likely a mirror, bind only one")

    return binding, groups, mirrors, notes


class MappingSession:
    """Owns the live state that the web UI drives."""

    def __init__(self, profile, backend, layer="base"):
        self.profile = profile
        self.backend = backend
        self.layer = layer
        self.mode = "idle"
        self.log = []
        self._learn = None
        self._probe = None
        self._monitor = []

    # ------------------------------------------------------------ plumbing

    def pump(self):
        """Move backend events into whichever loop is active. Call often."""
        events = self.backend.drain()
        if not events:
            return []
        self._monitor.extend(events)
        del self._monitor[:-200]
        if self._learn is not None:
            self._learn["events"].extend(events)
        if self._probe is not None:
            self._probe.setdefault("echo", []).extend(events)
        return events

    def monitor(self, limit=50):
        return self._monitor[-limit:]

    def note(self, text):
        self.log.append({"t": time.time(), "text": text})
        del self.log[:-200]

    # --------------------------------------------------------------- learn

    def start_learn(self, control_id, layer=None):
        c = self.profile.get(control_id)
        if c is None:
            raise KeyError(control_id)
        self.pump()          # discard anything already queued
        self._learn = {
            "control_id": control_id,
            "layer": layer or self.layer,
            "started": time.time(),
            "events": [],
        }
        self.mode = "learn"
        self.note(f"learning {c['label']} -- move it now")
        return self.learn_status()

    def learn_status(self):
        if self._learn is None:
            return {"active": False}
        self.pump()
        return {
            "active": True,
            "control_id": self._learn["control_id"],
            "layer": self._learn["layer"],
            "elapsed": round(time.time() - self._learn["started"], 2),
            "event_count": len(self._learn["events"]),
            "recent": self._learn["events"][-12:],
        }

    def finish_learn(self, commit=True):
        if self._learn is None:
            return None
        self.pump()
        cid = self._learn["control_id"]
        layer = self._learn["layer"]
        events = self._learn["events"]
        ctl = self.profile.get(cid) or {}

        res = CaptureResult(cid, layer, events)
        res.binding, res.groups, res.mirrors, res.notes = analyse(
            events, kind=ctl.get("kind"))

        if res.binding:
            clash = [
                (c["id"], ln) for c, ln in self.profile.find_by_message(
                    res.binding["status"], res.binding["number"],
                    res.binding.get("channel"), layer)
                if c["id"] != cid]
            if clash:
                who = ", ".join(f"{i} ({ln})" for i, ln in clash)
                res.notes.append(f"already claimed by {who}")

        if commit and res.binding:
            self.profile.set_binding(cid, layer, "input", res.binding)
            self.note(
                f"{ctl.get('label', cid)} = {res.binding['status']} "
                f"{res.binding['number']}")
        elif commit:
            self.note(f"{ctl.get('label', cid)}: nothing captured")

        self._learn = None
        self.mode = "idle"
        return res

    def cancel_learn(self):
        self._learn = None
        self.mode = "idle"

    def mark_silent(self, control_id, layer=None):
        """Record that a control emits nothing, which is a real finding.

        Analogue controls on a mixer with its own audio path send no MIDI at all.
        Recording that is what stops the next person re-testing them.
        """
        self.profile.set_binding(control_id, layer or self.layer, "input",
                                 {"status": "silent"})
        c = self.profile.get(control_id) or {}
        self.note(f"{c.get('label', control_id)}: silent, sends no MIDI")

    # --------------------------------------------------------------- probe

    def build_probe_queue(self, lo=0, hi=127, channel=1, strategy="smart"):
        """Order the notes to try. Prior knowledge first, then the sweep."""
        known = []
        for c in self.profile.controls:
            for _layer, b in (c.get("bindings") or {}).items():
                inp = b.get("input")
                if inp and inp.get("status") == "note":
                    n = inp.get("number")
                    if lo <= n <= hi and n not in known:
                        known.append(n)
        if strategy == "linear":
            order = list(range(lo, hi + 1))
        else:
            rest = [n for n in range(lo, hi + 1) if n not in known]
            order = known + rest
        return [{"note": n, "channel": channel,
                 "prior": n in known} for n in order]

    def start_probe(self, lo=0, hi=127, channel=1, strategy="smart",
                    hold_ms=900):
        self._probe = {
            "queue": self.build_probe_queue(lo, hi, channel, strategy),
            "index": -1,
            "hold_ms": hold_ms,
            "results": [],
            "current": None,
            "sent_at": None,
            "lit": None,
        }
        self.mode = "probe"
        q = self._probe["queue"]
        priors = sum(1 for x in q if x["prior"])
        self.note(
            f"LED probe: {len(q)} notes, {priors} already known as button inputs "
            f"and tried first")
        return self.probe_next()

    def probe_next(self):
        """Light the next candidate. Returns the probe state for the UI."""
        if self._probe is None:
            return {"active": False}
        p = self._probe
        self._probe_off()
        p["index"] += 1
        if p["index"] >= len(p["queue"]):
            return self.probe_status(done=True)
        cur = p["queue"][p["index"]]
        p["current"] = cur
        p["sent_at"] = time.time()
        self.backend.send("note_on", cur["channel"], cur["note"], 127)
        return self.probe_status()

    def _probe_off(self):
        p = self._probe
        if p and p.get("current"):
            cur = p["current"]
            self.backend.send("note_off", cur["channel"], cur["note"], 0)
            p["current"] = None

    def probe_answer(self, control_id=None):
        """Record which region lit for the note currently being held.

        control_id None means 'nothing lit', which is just as useful: it retires
        a note so the sweep never offers it again.
        """
        if self._probe is None:
            return {"active": False}
        p = self._probe
        cur = p.get("current")
        if cur is None:
            return self.probe_status()
        entry = {"note": cur["note"], "channel": cur["channel"],
                 "control_id": control_id}
        p["results"].append(entry)
        if control_id:
            self.profile.set_binding(
                control_id, self.layer, "output",
                {"status": "note", "channel": cur["channel"],
                 "number": cur["note"], "on": 127, "off": 0})
            c = self.profile.get(control_id) or {}
            self.note(f"LED {c.get('label', control_id)} = note {cur['note']}")
        return self.probe_next()

    def probe_status(self, done=False):
        if self._probe is None:
            return {"active": False}
        p = self._probe
        cur = p.get("current")
        return {
            "active": not done,
            "done": done,
            "index": p["index"],
            "total": len(p["queue"]),
            "current": cur,
            "hold_ms": p["hold_ms"],
            "found": sum(1 for r in p["results"] if r["control_id"]),
            "answered": len(p["results"]),
        }

    def stop_probe(self):
        if self._probe is None:
            return
        self._probe_off()
        found = sum(1 for r in self._probe["results"] if r["control_id"])
        self.note(f"LED probe stopped: {found} outputs identified")
        self._probe = None
        self.mode = "idle"

    # --------------------------------------------------------------- verify

    def blink(self, control_id, times=2, ms=250):
        """Flash a control's known LED, to confirm a binding points where it should."""
        out = self.profile.binding(control_id, self.layer, "output")
        if not out:
            return False
        for _ in range(times):
            self.backend.send("note_on", out.get("channel", 1), out["number"],
                              out.get("on", 127))
            time.sleep(ms / 1000.0)
            self.backend.send("note_off", out.get("channel", 1), out["number"],
                              out.get("off", 0))
            time.sleep(ms / 1000.0)
        return True

    def state(self):
        return {
            "mode": self.mode,
            "layer": self.layer,
            "backend": self.backend.name,
            "backend_status": self.backend.status,
            "learn": self.learn_status(),
            "probe": self.probe_status() if self._probe else {"active": False},
            "stats": self.profile.stats(),
            "log": self.log[-30:],
        }
