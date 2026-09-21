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

from . import colour

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


def _detect_14bit(groups):
    """Spot a high-resolution control sent as two CCs, and say which is which.

    A 14-bit fader sends a coarse byte and a fine byte together, so the two
    arrive in near-equal numbers. Without this they look like a control and its
    mirror, and the studio binds the coarse half alone -- which is how a pitch
    fader ended up captured as "0..7".

    Told apart by behaviour, not by number: the fine byte sweeps the whole
    0..127 range many times over while the coarse byte takes a handful of
    values. The convention that the low byte lives at CC n+32 is *not* assumed;
    the Reloop Ready pairs CC 9 with CC 63.
    """
    ccs = [g for g in groups if g["status"] == "cc"]
    if len(ccs) < 2:
        return None
    for i, a in enumerate(ccs):
        for b in ccs[i + 1:]:
            if a["channel"] != b["channel"]:
                continue
            lo, hi = sorted((a, b), key=lambda g: g["distinct"])
            if lo["count"] == 0 or hi["count"] == 0:
                continue
            ratio = min(a["count"], b["count"]) / max(a["count"], b["count"])
            if ratio < 0.7:                      # not sent together
                continue
            if hi["distinct"] < 32 or hi["max"] < 100:
                continue                          # fine byte must really sweep
            if lo["distinct"] > hi["distinct"] / 2:
                continue                          # coarse byte must be coarse
            return lo, hi                         # (msb, lsb)
    return None


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

    pair = _detect_14bit(groups)
    if pair:
        msb, lsb = pair
        span = msb["max"] * 128 + lsb["max"]
        binding = {
            "status": "cc",
            "channel": msb["channel"],
            "number": msb["number"],
            "lsb": lsb["number"],
            "mode": "14bit",
            "min": msb["min"] * 128 + lsb["min"],
            "max": span,
            "resting": msb["resting"] * 128 + lsb["resting"],
        }
        notes.append(
            f"14-bit: CC {msb['number']} carries the high bits and CC "
            f"{lsb['number']} the low ones, about {span + 1} steps of travel. "
            f"Both are exported; Mixxx pairs them itself.")
        others = [g for g in groups if g not in (msb, lsb)]
        return binding, groups, others, notes

    top = groups[0]
    status, channel, number = top["status"], top["channel"], top["number"]

    binding = {"status": status, "channel": channel, "number": number}

    if status == "note":
        binding["mode"] = "button"
        binding["press_value"] = max(
            (e["value"] for e in events
             if e["status"] == "note_on" and e["value"] > 0), default=127)
        # How the release arrives decides whether the mapping needs a second
        # binding: 0x8n is a different status byte from 0x9n, and a mapping
        # bound only to note-on never sees a real note-off.
        offs = [e for e in events if e["status"] == "note_off"
                and e["channel"] == channel and e["number"] == number]
        if offs:
            bytes_seen = {e.get("status_byte") for e in offs
                          if e.get("status_byte") is not None}
            if any(b is not None and (b & 0xF0) == 0x80 for b in bytes_seen):
                binding["release"] = "note_off"
                notes.append(
                    "releases arrive as note-off (0x8n), not note-on with "
                    "velocity 0; anything that must follow the release needs "
                    "both status bytes bound")
            else:
                binding["release"] = "note_on_zero"
        else:
            binding["release"] = "none_seen"
            notes.append("no release was seen; a gated control needs one")
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
        # Which channels this surface actually uses. Worth tracking because a
        # controller can spread its decks and pads across several, and that set
        # is what the LED probe should sweep.
        self.seen = {}

    # ------------------------------------------------------------ plumbing

    def pump(self):
        """Move backend events into whichever loop is active. Call often."""
        events = self.backend.drain()
        if not events:
            return []
        self._monitor.extend(events)
        del self._monitor[:-200]
        for ev in events:
            ch = self.seen.setdefault(ev["channel"], {"note": set(), "cc": set()})
            if ev["status"] in ("note_on", "note_off"):
                ch["note"].add(ev["number"])
            elif ev["status"] == "cc":
                ch["cc"].add(ev["number"])
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

    def mark_local_led(self, control_id, layer=None):
        """Record that a control's LED is driven by the device, not the host.

        The output-side twin of `silent`. Some LEDs are wired into the
        firmware -- the Reloop Ready's MODE buttons are lit permanently and
        simply brighten on press -- so no note will ever control them. Without
        somewhere to write that down, the only evidence is an absence, and the
        next person re-probes the whole range looking for it.
        """
        self.profile.set_binding(control_id, layer or self.layer, "output",
                                 {"status": "local"})
        c = self.profile.get(control_id) or {}
        self.note(f"{c.get('label', control_id)}: LED is firmware-driven, "
                  f"not host-addressable")

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

    def build_probe_queue(self, lo=0, hi=127, channels=(1,), strategy="smart"):
        """Order the (channel, note) pairs to try. Prior knowledge first.

        Channels are a list, not a single value. A controller that splits its
        surface across channels -- decks on 1 and 2, pads on 5 and 6 -- puts its
        LEDs on those same channels, and a one-channel sweep silently misses
        most of them.
        """
        channels = [int(c) for c in (channels or (1,))] or [1]
        known = []
        for c in self.profile.controls:
            for _layer, b in (c.get("bindings") or {}).items():
                inp = b.get("input")
                if inp and inp.get("status") == "note":
                    pair = (int(inp.get("channel", 1)), inp.get("number"))
                    if pair[0] in channels and lo <= pair[1] <= hi \
                            and pair not in known:
                        known.append(pair)
        if strategy == "observed":
            # Only the (channel, note) pairs this surface has actually emitted.
            # A button's LED answers to the button's own note on nearly all
            # gear, so the traffic already tells you where to look -- 41 sends
            # instead of 896 for a controller using seven channels.
            pairs = sorted(
                (ch, n) for ch, d in self.seen.items()
                for n in d["note"] if ch in channels and lo <= n <= hi)
            order = known + [p for p in pairs if p not in known]
        elif strategy == "linear":
            order = [(ch, n) for ch in channels for n in range(lo, hi + 1)]
        else:
            allpairs = [(ch, n) for ch in channels for n in range(lo, hi + 1)]
            order = known + [p for p in allpairs if p not in known]
        return [{"note": n, "channel": ch, "prior": (ch, n) in known}
                for ch, n in order]

    def start_probe(self, lo=0, hi=127, channels=(1,), strategy="smart",
                    hold_ms=900):
        self._probe = {
            "queue": self.build_probe_queue(lo, hi, channels, strategy),
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
        chans = sorted({x["channel"] for x in q})
        self.note(
            f"LED probe: {len(q)} sends across channel(s) "
            f"{','.join(str(c) for c in chans)}, {priors} already known as "
            f"button inputs and tried first")
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

    def led_off(self, channel, note):
        """Turn an LED off, both ways, because devices disagree about which.

        A real note-off (0x8n) and a note-on with velocity 0 (0x9n) mean the
        same thing to a person and are different bytes on the wire. The DJM-T1
        answers only to the second -- `tools/probe-leds.sh` has always used
        `90 nn 00` -- so a probe that sent note-offs lit every LED it touched
        and turned none of them back off.

        Sending both costs one extra message at human pace and works whichever
        the device honours.
        """
        style = ((self.profile.data.get("midi") or {}).get("led_off")
                 or "both")
        if style in ("both", "note_on_zero"):
            self.backend.send("note_on", channel, note, 0)
        if style in ("both", "note_off"):
            self.backend.send("note_off", channel, note, 0)

    def all_leds_off(self, lo=0, hi=127, channels=None):
        """Darken a range, for clearing up after a pass."""
        chans = channels or sorted(self.seen) or [1]
        n = 0
        for ch in chans:
            for note in range(lo, hi + 1):
                self.led_off(ch, note)
                n += 1
        self.note(f"cleared {n} LEDs on channel(s) "
                  f"{','.join(str(c) for c in chans)}")
        return n

    def _probe_off(self):
        p = self._probe
        if p and p.get("current"):
            cur = p["current"]
            self.led_off(cur["channel"], cur["note"])
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
                 "control_id": control_id, "index": p["index"],
                 "layer": self.layer,
                 # Kept so undo restores what was there rather than just
                 # deleting: this control may already have had an LED.
                 "previous": self.profile.binding(control_id, self.layer, "output")
                 if control_id else None}
        p["results"].append(entry)
        if control_id:
            self.profile.set_binding(
                control_id, self.layer, "output",
                {"status": "note", "channel": cur["channel"],
                 "number": cur["note"], "on": 127, "off": 0})
            c = self.profile.get(control_id) or {}
            self.note(f"LED {c.get('label', control_id)} = note {cur['note']}")
        return self.probe_next()

    def probe_undo(self):
        """Take back the last answer and light that note again.

        Clicking the wrong region is the one mistake this loop invites, and
        without a way back it silently writes an LED onto the wrong control and
        moves on. Undo puts the binding back the way it was and re-lights the
        note so it can be answered again.
        """
        if self._probe is None:
            return {"active": False}
        p = self._probe
        if not p["results"]:
            self.note("nothing to undo")
            return self.probe_status()
        last = p["results"].pop()
        cid = last.get("control_id")
        if cid:
            self.profile.set_binding(cid, last.get("layer", self.layer),
                                     "output", last.get("previous"))
            c = self.profile.get(cid) or {}
            self.note(f"undid LED {c.get('label', cid)} = note {last['note']}")
        else:
            self.note(f"undid 'nothing lit' for note {last['note']}")
        self._probe_off()
        p["index"] = last["index"] - 1      # probe_next steps forward onto it
        return self.probe_next()

    def probe_status(self, done=False):
        if self._probe is None:
            return {"active": False}
        p = self._probe
        cur = p.get("current")
        last = p["results"][-1] if p["results"] else None
        if last:
            c = self.profile.get(last.get("control_id") or "") or {}
            last = dict(last, control_label=c.get("label"))
        return {
            "active": not done,
            "done": done,
            "index": p["index"],
            "total": len(p["queue"]),
            "current": cur,
            "hold_ms": p["hold_ms"],
            "found": sum(1 for r in p["results"] if r["control_id"]),
            "answered": len(p["results"]),
            "last": last,
        }

    def stop_probe(self, clear=True):
        if self._probe is None:
            return
        self._probe_off()
        found = sum(1 for r in self._probe["results"] if r["control_id"])
        if clear:
            # Every note the pass touched, darkened. A probe that lights 71
            # LEDs and leaves them lit is worse than one that never ran.
            chans = sorted({q["channel"] for q in self._probe["queue"]})
            notes = [q["note"] for q in self._probe["queue"]]
            for ch in chans:
                for n in sorted(set(notes)):
                    self.led_off(ch, n)
        self.note(f"LED probe stopped: {found} outputs identified")
        self._probe = None
        self.mode = "idle"

    # --------------------------------------------------------------- verify

    # --------------------------------------------------------------- colour

    def light(self, control_id, r, g, b, bright=True, remember=False):
        """Show a colour on a control's LED, optionally storing it as its default.

        Sending immediately is the whole point: picking a colour and seeing it
        on the pad is the same click-and-confirm loop as the rest of the tool,
        and it is the only way to be sure the encoding is right for a given
        device.
        """
        out = self.profile.binding(control_id, self.layer, "output")
        if not out or out.get("status") == "local":
            return False
        led = (self.profile.data.get("led") or {})
        vel = colour.encode(r, g, b, bright=bright, led=led)
        ok = self.backend.send("note_on", out.get("channel", 1), out["number"], vel)
        if remember:
            c = self.profile.get(control_id)
            if c is not None:
                c["colour"] = {"r": r, "g": g, "b": b, "bright": bool(bright),
                               "velocity": vel}
        return ok

    def light_all(self, r, g, b, bright=True, kinds=("pad",)):
        """Set every control of the given kinds at once, for checking a colour."""
        n = 0
        for c in self.profile.controls:
            if kinds and c.get("kind") not in kinds:
                continue
            if self.light(c["id"], r, g, b, bright=bright):
                n += 1
        return n

    def blink(self, control_id, times=2, ms=250):
        """Flash a control's known LED, to confirm a binding points where it should."""
        out = self.profile.binding(control_id, self.layer, "output")
        if not out:
            return False
        for _ in range(times):
            self.backend.send("note_on", out.get("channel", 1), out["number"],
                              out.get("on", 127))
            time.sleep(ms / 1000.0)
            self.led_off(out.get("channel", 1), out["number"])
            time.sleep(ms / 1000.0)
        return True

    def state(self):
        # Drain on every status poll, not just while learning. A jog wheel
        # emits thousands of messages a minute, and if nothing is reading the
        # backend queue they simply accumulate until someone opens Learn.
        self.pump()
        return {
            "mode": self.mode,
            "layer": self.layer,
            "backend": self.backend.name,
            "backend_status": self.backend.status,
            # Reported separately: a controller can read perfectly while
            # nothing you send reaches it, which is invisible until an LED
            # pass quietly does nothing.
            "output_status": self.backend.out_status,
            "learn": self.learn_status(),
            "probe": self.probe_status() if self._probe else {"active": False},
            "stats": self.profile.stats(),
            "log": self.log[-30:],
            "seen": self.seen_summary(),
        }

    def seen_summary(self):
        """Channels observed so far, with how many distinct numbers on each."""
        return sorted(
            ({"channel": ch,
              "notes": len(d["note"]),
              "ccs": len(d["cc"]),
              "note_lo": min(d["note"]) if d["note"] else None,
              "note_hi": max(d["note"]) if d["note"] else None}
             for ch, d in self.seen.items()),
            key=lambda d: d["channel"])
