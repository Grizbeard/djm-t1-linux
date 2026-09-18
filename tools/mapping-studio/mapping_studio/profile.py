"""The controller profile: what the panel looks like and what each control emits.

A profile is one JSON file describing a physical control surface, independent of
any host program. It holds three separable things:

  1. Geometry -- where every control sits on the panel, in millimetres. This is
     measured fact about hardware, so it is the part worth keeping forever.
  2. Bindings -- what each control emits, per layer. Filled in by a mapping
     session; this is the part the hardware tells you.
  3. Targets  -- what each binding should drive in the host (Mixxx). A human
     decision, deliberately kept separate from the two above.

Keeping those apart is what makes a profile durable. Re-mapping to a different
host, or re-deciding what a button should do, must never cost you the
measurements or the captured MIDI.

Artwork policy. A profile stores geometry, never traced vendor artwork. The
renderer draws a schematic from the geometry, so a profile is safe to publish
under this repository's licence. If you want a photo or a manual scan behind the
regions while you work, point `backdrop.href` at a local file; it is your copy
and is not part of the profile's redistributable content.

SPDX-License-Identifier: MIT
"""

import copy
import json
import os
import re
import time

SCHEMA = 1

KINDS = ("knob", "encoder", "fader", "jog", "button", "pad", "switch", "led", "meter")

# Controls that report a continuous position, as opposed to an event.
CONTINUOUS = ("knob", "fader", "jog")


class ProfileError(ValueError):
    pass


def _slug(text):
    s = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")
    return s or "ctl"


class Profile:
    def __init__(self, data):
        self.data = data
        self._index = {c["id"]: c for c in self.controls}

    # ---------------------------------------------------------------- factory

    @classmethod
    def new(cls, ident, name, panel, controls=None):
        return cls({
            "schema": SCHEMA,
            "id": ident,
            "name": name,
            "created": time.strftime("%Y-%m-%d"),
            "units": panel.get("units", "mm"),
            "panel": {"w": panel["w"], "h": panel["h"]},
            "backdrop": {"kind": "schematic"},
            "layers": ["base"],
            "midi": {"channel": 1},
            "controls": controls or [],
        })

    @classmethod
    def load(cls, path):
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if data.get("schema") != SCHEMA:
            raise ProfileError(
                f"{path}: schema {data.get('schema')!r}, this build speaks {SCHEMA}")
        p = cls(data)
        p.validate()
        return p

    def save(self, path):
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, indent=1, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, path)

    # ---------------------------------------------------------------- access

    @property
    def controls(self):
        return self.data.setdefault("controls", [])

    @property
    def layers(self):
        return self.data.setdefault("layers", ["base"])

    @property
    def panel(self):
        return self.data["panel"]

    def get(self, control_id):
        return self._index.get(control_id)

    def reindex(self):
        self._index = {c["id"]: c for c in self.controls}

    def unique_id(self, base):
        base = _slug(base)
        if base not in self._index:
            return base
        n = 2
        while f"{base}_{n}" in self._index:
            n += 1
        return f"{base}_{n}"

    # ---------------------------------------------------------------- mutate

    def add_control(self, control):
        control = copy.deepcopy(control)
        control["id"] = self.unique_id(control.get("id") or control.get("label") or "ctl")
        control.setdefault("kind", "button")
        control.setdefault("label", control["id"].replace("_", " ").upper())
        control.setdefault("bindings", {})
        self.controls.append(control)
        self._index[control["id"]] = control
        return control

    def update_control(self, control_id, patch):
        c = self.get(control_id)
        if c is None:
            raise ProfileError(f"no such control: {control_id}")
        for k, v in patch.items():
            if k == "id":
                continue
            if v is None:
                c.pop(k, None)
            else:
                c[k] = v
        # A control a human has touched is no longer a guess.
        if any(k in patch for k in ("label", "kind", "shape")):
            c.pop("provisional", None)
            c.pop("confidence", None)
            c.pop("evidence", None)
        return c

    def remove_control(self, control_id):
        c = self.get(control_id)
        if c is None:
            return False
        self.controls.remove(c)
        del self._index[control_id]
        return True

    def rename_control(self, control_id, new_id):
        c = self.get(control_id)
        if c is None:
            raise ProfileError(f"no such control: {control_id}")
        new_id = _slug(new_id)
        if new_id != control_id and new_id in self._index:
            raise ProfileError(f"id already in use: {new_id}")
        del self._index[control_id]
        c["id"] = new_id
        self._index[new_id] = c
        return c

    # ---------------------------------------------------------------- binding

    def set_binding(self, control_id, layer, direction, binding):
        """direction is 'input' (control -> host) or 'output' (host -> LED)."""
        if direction not in ("input", "output"):
            raise ProfileError(f"bad direction: {direction}")
        c = self.get(control_id)
        if c is None:
            raise ProfileError(f"no such control: {control_id}")
        if layer not in self.layers:
            self.layers.append(layer)
        b = c.setdefault("bindings", {}).setdefault(layer, {})
        if binding is None:
            b.pop(direction, None)
            if not b:
                c["bindings"].pop(layer, None)
        else:
            b[direction] = binding
        c.pop("provisional", None)
        return c

    def binding(self, control_id, layer, direction):
        c = self.get(control_id)
        if not c:
            return None
        return (c.get("bindings", {}).get(layer, {}) or {}).get(direction)

    def find_by_message(self, status, number, channel=None, layer=None):
        """Which control already claims this message? Used to warn about collisions."""
        hits = []
        for c in self.controls:
            for lname, b in (c.get("bindings") or {}).items():
                if layer and lname != layer:
                    continue
                inp = b.get("input")
                if not inp:
                    continue
                if inp.get("status") == status and inp.get("number") == number:
                    if channel is None or inp.get("channel", 1) == channel:
                        hits.append((c, lname))
        return hits

    # ---------------------------------------------------------------- reports

    def validate(self):
        seen = set()
        for c in self.controls:
            cid = c.get("id")
            if not cid:
                raise ProfileError("control with no id")
            if cid in seen:
                raise ProfileError(f"duplicate control id: {cid}")
            seen.add(cid)
            if c.get("kind") not in KINDS:
                raise ProfileError(f"{cid}: unknown kind {c.get('kind')!r}")
            sh = c.get("shape") or {}
            if sh.get("type") not in ("circle", "rect"):
                raise ProfileError(f"{cid}: shape must be circle or rect")
        return True

    def collisions(self):
        """Distinct (layer, status, number) claimed by more than one control."""
        claims = {}
        for c in self.controls:
            for lname, b in (c.get("bindings") or {}).items():
                inp = b.get("input")
                if not inp:
                    continue
                key = (lname, inp.get("status"), inp.get("channel", 1), inp.get("number"))
                claims.setdefault(key, []).append(c["id"])
        return {k: v for k, v in claims.items() if len(v) > 1}

    def stats(self):
        total = len(self.controls)
        prov = sum(1 for c in self.controls if c.get("provisional"))
        mapped = {}
        for layer in self.layers:
            mapped[layer] = sum(
                1 for c in self.controls
                if (c.get("bindings", {}).get(layer, {}) or {}).get("input"))
        outputs = sum(
            1 for c in self.controls
            for b in (c.get("bindings") or {}).values() if b.get("output"))
        targeted = sum(1 for c in self.controls if c.get("target"))
        return {
            "controls": total,
            "provisional": prov,
            "mapped_inputs": mapped,
            "mapped_outputs": outputs,
            "targeted": targeted,
            "collisions": len(self.collisions()),
        }
