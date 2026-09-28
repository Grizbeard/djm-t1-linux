"""Library favorites on buttons: tap to jump there, hold to remember.

Mixxx patch 0014 (Terminal-wide repository) gives the library six numbered
favorites, [Library],favorite_N_store / favorite_N_activate: store remembers
whatever is selected in the sidebar, activate selects and opens it again. A
recall whose item is not in the sidebar - a visiting DJ's drive that has
left - does nothing. Each successful recall bumps [Library],favorite_recalls,
which is how the mapping knows there is something to show.

This module puts those on buttons. A tap recalls the favorite and, when it
was found, switches the skin to the library page with the track list focused
(page_nav). Holding the button for `hold_ms` or longer stores the sidebar's
current selection instead; the button's lamp flashes when the hold reaches
that point, to say that letting go now will store, and so does a lamp
elsewhere on the panel (`confirm_control`, the DJM-T1's SNAP), three times,
which is easier to see under a finger. The store itself still waits for the
release.

The decision is made on the release, not by a timer firing while held. On a
panel whose SHIFT is firmware-only - the DJM-T1's sends no MIDI - a shifted
button's release can arrive on the unshifted note if SHIFT is let go first,
and the handler never sees it. Deciding on release makes that case do
nothing at all; storing on a timer would overwrite a favorite after what was
meant as a quick tap.

The profile declares:

    "favorites": {
      "hold_ms": 1000,
      "confirm_control": "snap",
      "slots": [{"slot": 1, "control": "fx1_1_on", "layer": "shift"}, ...]
    }

and binds each control's layer to the handler handler_name(slot) as an
external script target. The lamp is the control's base-layer output. The
confirmation blinks every layer's output of confirm_control, since the panel
shows whichever layer SHIFT picks; if that lamp is a gang lamp (SNAP shows
quantize and slip), the gangs are repainted afterwards.

SPDX-License-Identifier: MIT
"""

import json


def spec(profile):
    return profile.data.get("favorites") or {}


def handler_name(slot):
    return f"favorite{int(slot)}"


def _led(controls, cid):
    c = controls.get(cid)
    if c is None:
        raise ValueError(f"favorites: no control {cid!r}")
    out = ((c.get("bindings") or {}).get("base") or {}).get("output")
    if not out or out.get("status", "note") not in ("note", "cc"):
        return None
    status = (0x90 if out.get("status", "note") == "note" else 0xB0) \
        | (out.get("channel", 1) - 1)
    return {"status": status, "midino": out["number"],
            "on": out.get("on", 0x7F), "off": out.get("off", 0x00)}


def _confirm_leds(controls, cid):
    c = controls.get(cid)
    if c is None:
        raise ValueError(f"favorites: no control {cid!r}")
    leds = []
    for layer in (c.get("bindings") or {}).values():
        out = (layer or {}).get("output")
        if not out or out.get("status", "note") != "note":
            continue
        leds.append({"status": 0x90 | (out.get("channel", 1) - 1),
                     "midino": out["number"],
                     "on": out.get("on", 0x7F), "off": out.get("off", 0x00)})
    if not leds:
        raise ValueError(f"favorites: {cid!r} has no lamp to confirm with")
    return leds


def _table(profile):
    s = spec(profile)
    if not s:
        return None
    controls = {c["id"]: c for c in profile.controls}
    slots = []
    seen = set()
    for entry in s.get("slots") or []:
        n = int(entry["slot"])
        if not 1 <= n <= 6:
            raise ValueError(f"favorites: slot {n} is outside 1..6")
        if n in seen:
            raise ValueError(f"favorites: slot {n} is on two buttons")
        seen.add(n)
        slots.append({"slot": n, "led": _led(controls, entry["control"])})
    confirm = _confirm_leds(controls, s["confirm_control"])         if s.get("confirm_control") else []
    return {"holdMs": int(s.get("hold_ms", 1000)), "slots": slots,
            "confirm": confirm}


def init_calls(profile, prefix):
    return [f"    {prefix}.initFavorites();"] if spec(profile) else []


def generate(profile, prefix):
    """JS for the favorite buttons. [] if none declared."""
    table = _table(profile)
    if not table:
        return []
    p = prefix
    has_nav = bool(profile.data.get("page_nav"))
    has_fx = bool(profile.data.get("fx_sections"))
    has_gang_leds = any(g.get("led") is not None
                        for g in profile.data.get("gangs") or [])
    out = [
        "// ---------------------------------------------------------------",
        "// Library favorites: tap to jump there, hold to remember.",
        "// ---------------------------------------------------------------",
        "",
        f"{p}.FAVORITES = " + json.dumps(table, indent=4) + ";",
        "",
        f"{p}.favDown = [];    // when each button went down, while it is down",
        f"{p}.favTimer = [];   // the hold timer, while it is running",
        f"{p}.favConfirmTimer = undefined;",
        "",
        f"{p}.initFavorites = function () {{",
        "    // Bumped by Mixxx on every recall that found its item: only then",
        "    // is there something worth switching pages for.",
        '    engine.makeConnection("[Library]", "favorite_recalls", function () {',
    ]
    if has_nav:
        out.append(f"        {p}.navShowLibrary(3);   // the track list")
    else:
        out.append('        engine.setValue("[Library]", "focused_widget", 3);')
    out += [
        "    });",
        "};",
        "",
        f"{p}.favPulse = function (key, n) {{",
        '    engine.setValue("[Library]", "favorite_" + n + "_" + key, 1);',
        '    engine.setValue("[Library]", "favorite_" + n + "_" + key, 0);',
        "};",
        "",
        "// Blink the button's lamp, then give it back to whatever owns it.",
        f"{p}.favFlash = function (i) {{",
        f"    var led = {p}.FAVORITES.slots[i].led;",
        "    if (!led) {",
        "        return;",
        "    }",
        "    // On at once, so the moment the hold counts is the moment it shows.",
        "    midi.sendShortMsg(led.status, led.midino, led.on);",
        "    var left = 5;",
        "    var timer = engine.beginTimer(80, function () {",
        "        left--;",
        "        midi.sendShortMsg(led.status, led.midino, left % 2 ? led.on : led.off);",
        "        if (left <= 0) {",
        "            engine.stopTimer(timer);",
        f"            {p}.favRestoreLed(i);",
        "        }",
        "    });",
        "};",
        "",
        f"{p}.favRestoreLed = function (i) {{",
    ]
    if has_fx:
        out += [
            "    // The lamp belongs to an FX section button: repaint the sections.",
            f"    for (var s = 0; s < {p}.FX_SECTIONS.length; s++) {{",
            f"        {p}.paintFx(s);",
            "    }",
        ]
    else:
        out += [
            f"    var led = {p}.FAVORITES.slots[i].led;",
            "    midi.sendShortMsg(led.status, led.midino, led.off);",
        ]
    out += [
        "};",
        "",
        "// Three blinks of the confirmation lamp: held long enough to store.",
        "// Off first, so that a lamp already lit still shows three, and a",
        "// longer dark pause at the end so they read as three before the lamp",
        "// goes back to what it shows.",
        f"{p}.favConfirm = function () {{",
        f"    var leds = {p}.FAVORITES.confirm;",
        "    if (!leds.length) {",
        "        return;",
        "    }",
        f"    if ({p}.favConfirmTimer !== undefined) {{",
        f"        engine.stopTimer({p}.favConfirmTimer);",
        "    }",
        "    var step = 0;",
        "    var paint = function () {",
        "        for (var j = 0; j < leds.length; j++) {",
        "            midi.sendShortMsg(leds[j].status, leds[j].midino,",
        "                step % 2 ? leds[j].on : leds[j].off);",
        "        }",
        "    };",
        "    paint();",
        f"    {p}.favConfirmTimer = engine.beginTimer(120, function () {{",
        "        step++;",
        "        if (step < 7) {",
        "            paint();",
        "        }",
        "        if (step < 10) {",
        "            return;",
        "        }",
        f"        engine.stopTimer({p}.favConfirmTimer);",
        f"        {p}.favConfirmTimer = undefined;",
        f"        {p}.favRestoreConfirm();",
        "    });",
        "};",
        "",
        f"{p}.favRestoreConfirm = function () {{",
    ]
    if has_gang_leds:
        out.append(f"    {p}.paintGangs();   // the lamp also shows a gang's state")
    else:
        out += [
            f"    var leds = {p}.FAVORITES.confirm;",
            "    for (var j = 0; j < leds.length; j++) {",
            "        midi.sendShortMsg(leds[j].status, leds[j].midino, leds[j].off);",
            "    }",
        ]
    out += [
        "};",
        "",
        f"{p}.favPress = function (i, value, status) {{",
        "    var pressed = value > 0 && (status & 0xF0) !== 0x80;",
        f"    var holdMs = {p}.FAVORITES.holdMs;",
        "    if (pressed) {",
        f"        {p}.favDown[i] = Date.now();",
        f"        {p}.favTimer[i] = engine.beginTimer(holdMs, function () {{",
        f"            {p}.favTimer[i] = undefined;",
        f"            {p}.favFlash(i);   // letting go now will store",
        f"            {p}.favConfirm();",
        "        }, true);",
        "        return;",
        "    }",
        f"    if ({p}.favDown[i] === undefined) {{",
        "        return;   // a release whose press this handler never saw",
        "    }",
        f"    var held = Date.now() - {p}.favDown[i];",
        f"    {p}.favDown[i] = undefined;",
        f"    if ({p}.favTimer[i] !== undefined) {{",
        f"        engine.stopTimer({p}.favTimer[i]);",
        f"        {p}.favTimer[i] = undefined;",
        "    }",
        f"    var n = {p}.FAVORITES.slots[i].slot;",
        f'    {p}.favPulse(held >= holdMs ? "store" : "activate", n);',
        "};",
        "",
    ]
    for i, s in enumerate(table["slots"]):
        out.append(f"{p}.{handler_name(s['slot'])} = function (ch, ctrl, value, status) "
                   f"{{ {p}.favPress({i}, value, status); }};")
    out.append("")
    return out
