"""FX sections that switch between effect units.

A panel FX section - an ON button, a DRY/WET knob, and a level knob and on
button per effect slot - addresses one effect unit. Mixxx has four, so a
controller with two sections reaches all four by giving each section a pair
and a pair of select buttons: FX1 plays unit 1 or 2, FX2 unit 3 or 4.

Selecting a unit changes only what the section's controls address. Each unit
keeps its own on/off state, so a unit left on keeps playing while the section
works the other one - an echo left running while the second unit is dialled
in, say.

Why script, not <output>s and plain bindings: every control in the section is
re-pointed at runtime, which an XML binding cannot be, and every light has to
follow whichever unit is selected. The knobs use soft takeover, so after a
switch a knob does nothing until it reaches the new unit's value, rather than
jumping it to wherever the knob happens to be.

The profile declares the sections under `fx_sections`:

    "fx_sections": [
      {"name": "FX1", "units": [1, 2],
       "select": ["fx1_assign_a", "fx2_assign_a"],
       "on": "fx1_on", "mix": "fx1_dry_wet", "knob_key": "mix",
       "levels": ["fx1_1_level", "fx1_2_level", "fx1_3_level"],
       "slots": ["fx1_1_on", "fx1_2_on", "fx1_3_on"]}
    ]

`knob_key` is the unit control the `mix` knob turns: "mix" (dry/wet, the
default) or "super1" (the unit's super knob, which drives every slot's meta
knob at once).

`knob_choice` lets a control elsewhere - a skin button, one per unit - pick
that per unit instead:

    "knob_choice": {"control": "[TerminalWide],fx{unit}_knob_drywet",
                    "keys": ["super1", "mix"]}

`{unit}` is the unit's number, and the control's value indexes `keys`. Until
the control exists (on the Pi the controller starts before the skin has
loaded; a mapping run with another skin never sees it) the knob turns
`knob_key`. The mapping retries the connection once a second for 30 s. Soft
takeover covers every key, so switching a unit over makes the knob pick up
the other control where it stands rather than jump it.

Each entry names panel controls by id; their lights are read from the
controls' base-layer outputs. The handlers are generated with names derived
from `name` (see handler_names), and the profile binds the controls to them as
external script targets.

SPDX-License-Identifier: MIT
"""

import json


def sections(profile):
    return profile.data.get("fx_sections") or []


def handler_names(section):
    """The script functions a section's controls bind to, by role."""
    n = section["name"].lower()
    units = section["units"]
    slots = len(section.get("levels") or section.get("slots") or [])
    return {
        "select": [f"{n}Select{k + 1}" for k in range(len(units))],
        "on": f"{n}On",
        "next_chain": f"{n}NextChain",
        "mix": f"{n}Mix",
        "levels": [f"{n}Level{j + 1}" for j in range(slots)],
        "slots": [f"{n}Slot{j + 1}" for j in range(slots)],
        "next_effect": [f"{n}NextEffect{j + 1}" for j in range(slots)],
    }


def _led(controls, cid, name):
    c = controls.get(cid)
    if c is None:
        raise ValueError(f"fx_sections {name}: no control {cid!r}")
    out = ((c.get("bindings") or {}).get("base") or {}).get("output")
    if not out or out.get("status", "note") not in ("note", "cc"):
        return None
    status = (0x90 if out.get("status", "note") == "note" else 0xB0) \
        | (out.get("channel", 1) - 1)
    return {"status": status, "midino": out["number"],
            "on": out.get("on", 0x7F), "off": out.get("off", 0x00)}


def _knob_choice(section, units):
    c = section.get("knob_choice")
    if not c:
        return None
    keys = list(c.get("keys") or [])
    if len(keys) < 2:
        raise ValueError(f"fx_sections {section['name']}: knob_choice needs two or more keys")
    controls = []
    for u in units:
        group, _, key = c["control"].replace("{unit}", str(u)).partition(",")
        if not (group.startswith("[") and group.endswith("]") and key):
            raise ValueError(f"fx_sections {section['name']}: knob_choice control "
                             f"{c['control']!r} is not \"[Group],key\"")
        controls.append([group, key])
    return {"controls": controls, "keys": keys}


def _table(profile):
    controls = {c["id"]: c for c in profile.controls}
    table = []
    for s in sections(profile):
        name = s["name"]
        units = [int(u) for u in s["units"]]
        if len(units) < 2:
            raise ValueError(f"fx_sections {name}: needs two or more units")
        if len(s.get("select") or []) != len(units):
            raise ValueError(f"fx_sections {name}: one select button per unit")
        n_slots = len(s.get("levels") or [])
        if len(s.get("slots") or []) != n_slots:
            raise ValueError(f"fx_sections {name}: levels and slots differ")
        table.append({
            "name": name,
            "units": [f"[EffectRack1_EffectUnit{u}]" for u in units],
            "slotGroups": [[f"[EffectRack1_EffectUnit{u}_Effect{n + 1}]"
                            for n in range(n_slots)] for u in units],
            "slots": n_slots,
            "knobKey": s.get("knob_key", "mix"),
            "knobChoice": _knob_choice(s, units),
            "selectLeds": [_led(controls, cid, name) for cid in s["select"]],
            "onLed": _led(controls, s["on"], name) if s.get("on") else None,
            "slotLeds": [_led(controls, cid, name) for cid in s["slots"]],
        })
    return table


def init_calls(profile, prefix):
    return [f"    {prefix}.initFxSections();"] if sections(profile) else []


def shutdown_calls(profile, prefix):
    return [f"    {prefix}.fxLedsOff();"] if sections(profile) else []


def generate(profile, prefix):
    """JS for every declared FX section. [] if none."""
    table = _table(profile)
    if not table:
        return []
    p = prefix
    out = [
        "// ---------------------------------------------------------------",
        "// FX sections: each switches between effect units.",
        "// ---------------------------------------------------------------",
        "",
        f"{p}.FX_SECTIONS = " + json.dumps(table, indent=4) + ";",
        "",
        "// Which unit each section is on: an index into its units.",
        f"{p}.fxSel = [];",
        "",
        f"{p}.fxUnit = function (s) {{",
        f"    return {p}.FX_SECTIONS[s].units[{p}.fxSel[s]];",
        "};",
        "",
        f"{p}.fxSlot = function (s, n) {{",
        f"    return {p}.FX_SECTIONS[s].slotGroups[{p}.fxSel[s]][n];",
        "};",
        "",
        "// 0 and 127 are the ends, and the centre detent is exactly the",
        "// middle: it can rest a step or two either side of 64, and a meta or",
        "// super knob a step off centre still leaves a send open (Filter Echo,",
        "// Filter Reverb) or a filter barely on. So 62-66 are all 0.5, and the",
        "// travel either side spreads evenly over the rest.",
        f"{p}.FX_KNOB_CENTRE_LOW = 62;",
        f"{p}.FX_KNOB_CENTRE_HIGH = 66;",
        f"{p}.fxKnob = function (value) {{",
        f"    var lo = {p}.FX_KNOB_CENTRE_LOW;",
        f"    var hi = {p}.FX_KNOB_CENTRE_HIGH;",
        "    if (value <= lo) {",
        "        return value / lo / 2;",
        "    }",
        "    if (value >= hi) {",
        "        return 0.5 + (value - hi) / (127 - hi) / 2;",
        "    }",
        "    return 0.5;",
        "};",
        "",
        "// Which key each unit's knob_choice control picks, once connected:",
        "// fxChoice[s][k] is an index into knobChoice.keys, or undefined.",
        f"{p}.fxChoice = [];",
        f"{p}.fxChoiceRetryMs = 1000;",
        f"{p}.fxChoiceRetries = 30;",
        "",
        "// The unit control the section's knob turns right now.",
        f"{p}.fxKnobKey = function (s) {{",
        f"    var d = {p}.FX_SECTIONS[s];",
        f"    var i = d.knobChoice ? {p}.fxChoice[s][{p}.fxSel[s]] : undefined;",
        "    if (i === undefined) {",
        "        return d.knobKey;",
        "    }",
        "    return d.knobChoice.keys[Math.max(0, Math.min(d.knobChoice.keys.length - 1, i))];",
        "};",
        "",
        "// Follow unit k's choice control; false while it does not exist yet.",
        f"{p}.connectFxChoice = function (s, k) {{",
        f"    var c = {p}.FX_SECTIONS[s].knobChoice.controls[k];",
        "    var conn = engine.makeConnection(c[0], c[1], function (value) {",
        f"        {p}.fxChoice[s][k] = Math.round(value);",
        "    });",
        "    if (!conn) {",
        "        return false;",
        "    }",
        f"    {p}.fxChoice[s][k] = Math.round(engine.getValue(c[0], c[1]));",
        "    return true;",
        "};",
        "",
        "// The skin makes the choice controls, and on the Pi it loads after",
        "// the controller has started: keep trying for a while.",
        f"{p}.followFxChoices = function () {{",
        "    var pending = [];",
        f"    for (var s = 0; s < {p}.FX_SECTIONS.length; s++) {{",
        f"        var d = {p}.FX_SECTIONS[s];",
        "        if (!d.knobChoice) {",
        "            continue;",
        "        }",
        "        for (var k = 0; k < d.units.length; k++) {",
        f"            if (!{p}.connectFxChoice(s, k)) {{",
        "                pending.push([s, k]);",
        "            }",
        "        }",
        "    }",
        "    if (!pending.length) {",
        "        return;",
        "    }",
        "    var tries = 0;",
        f"    var timer = engine.beginTimer({p}.fxChoiceRetryMs, function () {{",
        "        tries++;",
        "        pending = pending.filter(function (sk) {",
        f"            return !{p}.connectFxChoice(sk[0], sk[1]);",
        "        });",
        f"        if (!pending.length || tries >= {p}.fxChoiceRetries) {{",
        "            engine.stopTimer(timer);",
        "        }",
        "    });",
        "};",
        "",
        f"{p}.initFxSections = function () {{",
        f"    for (var s = 0; s < {p}.FX_SECTIONS.length; s++) {{",
        f"        var d = {p}.FX_SECTIONS[s];",
        f"        {p}.fxSel[s] = 0;",
        f"        {p}.fxChoice[s] = [];",
        "        var keys = [d.knobKey].concat(d.knobChoice ? d.knobChoice.keys : []);",
        "        for (var k = 0; k < d.units.length; k++) {",
        "            var u = d.units[k];",
        "            for (var j = 0; j < keys.length; j++) {",
        "                engine.softTakeover(u, keys[j], true);",
        "            }",
        "            for (var n = 0; n < d.slots; n++) {",
        '                engine.softTakeover(d.slotGroups[k][n], "meta", true);',
        "            }",
        f"            {p}.connectFxUnit(s, k);",
        "        }",
        f"        {p}.paintFx(s);",
        "    }",
        f"    {p}.followFxChoices();",
        "};",
        "",
        f"{p}.connectFxUnit = function (s, k) {{",
        f"    var d = {p}.FX_SECTIONS[s];",
        "    var u = d.units[k];",
        '    engine.makeConnection(u, "enabled", function () {',
        f"        {p}.paintFx(s);",
        "    });",
        "    for (var n = 0; n < d.slots; n++) {",
        '        engine.makeConnection(d.slotGroups[k][n], "enabled",',
        f'            function () {{ {p}.paintFx(s); }});',
        "    }",
        "};",
        "",
        "// Select unit k of section s: only what the section's controls",
        "// address. Both units keep their own on/off state.",
        f"{p}.fxSelect = function (s, k) {{",
        f"    var d = {p}.FX_SECTIONS[s];",
        "    if (k < 0 || k >= d.units.length) {",
        "        return;",
        "    }",
        f"    {p}.fxSel[s] = k;",
        f"    {p}.paintFx(s);",
        "};",
        "",
        f"{p}.fxLed = function (led, lit) {{",
        "    if (led) {",
        "        midi.sendShortMsg(led.status, led.midino, lit ? led.on : led.off);",
        "    }",
        "};",
        "",
        f"{p}.paintFx = function (s) {{",
        f"    var d = {p}.FX_SECTIONS[s];",
        f"    var u = {p}.fxUnit(s);",
        "    for (var k = 0; k < d.selectLeds.length; k++) {",
        f"        {p}.fxLed(d.selectLeds[k], k === {p}.fxSel[s]);",
        "    }",
        f'    {p}.fxLed(d.onLed, engine.getValue(u, "enabled") > 0);',
        "    for (var n = 0; n < d.slotLeds.length; n++) {",
        f'        {p}.fxLed(d.slotLeds[n], engine.getValue({p}.fxSlot(s, n), "enabled") > 0);',
        "    }",
        "};",
        "",
        f"{p}.fxLedsOff = function () {{",
        f"    for (var s = 0; s < {p}.FX_SECTIONS.length; s++) {{",
        f"        var d = {p}.FX_SECTIONS[s];",
        "        var leds = d.selectLeds.concat([d.onLed], d.slotLeds);",
        "        for (var i = 0; i < leds.length; i++) {",
        f"            {p}.fxLed(leds[i], false);",
        "        }",
        "    }",
        "};",
        "",
        "// --- handlers: buttons act on the press, knobs on every value ---",
        "",
        f"{p}.fxPressSelect = function (s, k, value) {{",
        "    if (value !== 0) {",
        f"        {p}.fxSelect(s, k);",
        "    }",
        "};",
        "",
        f"{p}.fxPressOn = function (s, value) {{",
        "    if (value !== 0) {",
        f"        var u = {p}.fxUnit(s);",
        '        engine.setValue(u, "enabled", engine.getValue(u, "enabled") > 0 ? 0 : 1);',
        "    }",
        "};",
        "",
        f"{p}.fxPressNextChain = function (s, value) {{",
        "    if (value !== 0) {",
        f'        engine.setValue({p}.fxUnit(s), "next_chain_preset", 1);',
        "    }",
        "};",
        "",
        f"{p}.fxTurnMix = function (s, value) {{",
        f'    engine.setParameter({p}.fxUnit(s), {p}.fxKnobKey(s), {p}.fxKnob(value));',
        "};",
        "",
        f"{p}.fxTurnLevel = function (s, n, value) {{",
        f'    engine.setParameter({p}.fxSlot(s, n), "meta", {p}.fxKnob(value));',
        "};",
        "",
        f"{p}.fxPressSlot = function (s, n, value) {{",
        "    if (value !== 0) {",
        f"        var g = {p}.fxSlot(s, n);",
        '        engine.setValue(g, "enabled", engine.getValue(g, "enabled") > 0 ? 0 : 1);',
        "    }",
        "};",
        "",
        f"{p}.fxPressNextEffect = function (s, n, value) {{",
        "    if (value !== 0) {",
        f'        engine.setValue({p}.fxSlot(s, n), "next_effect", 1);',
        "    }",
        "};",
        "",
    ]
    # One named entry point per control, as the XML binds by name.
    for s, sec in enumerate(sections(profile)):
        h = handler_names(sec)
        out.append(f"// {sec['name']}")
        for k, fn in enumerate(h["select"]):
            out.append(f"{p}.{fn} = function (ch, ctrl, value) "
                       f"{{ {p}.fxPressSelect({s}, {k}, value); }};")
        out.append(f"{p}.{h['on']} = function (ch, ctrl, value) "
                   f"{{ {p}.fxPressOn({s}, value); }};")
        out.append(f"{p}.{h['next_chain']} = function (ch, ctrl, value) "
                   f"{{ {p}.fxPressNextChain({s}, value); }};")
        out.append(f"{p}.{h['mix']} = function (ch, ctrl, value) "
                   f"{{ {p}.fxTurnMix({s}, value); }};")
        for n, fn in enumerate(h["levels"]):
            out.append(f"{p}.{fn} = function (ch, ctrl, value) "
                       f"{{ {p}.fxTurnLevel({s}, {n}, value); }};")
        for n, fn in enumerate(h["slots"]):
            out.append(f"{p}.{fn} = function (ch, ctrl, value) "
                       f"{{ {p}.fxPressSlot({s}, {n}, value); }};")
        for n, fn in enumerate(h["next_effect"]):
            out.append(f"{p}.{fn} = function (ch, ctrl, value) "
                       f"{{ {p}.fxPressNextEffect({s}, {n}, value); }};")
        out.append("")
    return out
