"""Bank-switched hot cues, and a sampler bank sharing the same buttons.

Two idioms that Mixxx has no declarative form for, and that a controller with
four cue buttons per deck needs if it is to reach eight hot cues:

  * A *bank* button that shifts which hot cues four buttons address. Mixxx has
    no bank concept, so the offset lives in the mapping's own state and every
    press has to be routed through script.
  * A hardware *mode* that re-addresses the same buttons. This is not state the
    mapping tracks: the firmware sends different notes, so both sets are bound
    at once and whichever arrives is the one the user is looking at. What does
    need tracking is only what Mixxx cannot represent -- whether a sampler pad
    plays while held or toggles.

LED policy. Pad lights are driven from script rather than from an <output>,
because what a pad should show depends on the bank: with cues 5-8 selected, pad
1 must follow `hotcue_5_status`, and an <output> cannot be re-pointed at
runtime. The bank button's own light is pure mapping state and has no Mixxx
control behind it at all.

The profile declares all of this under a `banks` key; nothing here is specific
to one controller beyond the numbers it reads from there.

SPDX-License-Identifier: MIT
"""


def _decks(profile):
    return ((profile.data.get("banks") or {}).get("decks")) or []


def _bank_control(deck):
    """The deck's optional `bank_control`, "[Group],key", as a JS pair or null.

    Where the mapping publishes the deck's current bank (0 = the first) for a
    skin to follow. The control belongs to the skin; see followBankControl."""
    spec = deck.get("bank_control")
    if not spec:
        return "null"
    group, sep, key = spec.partition(",")
    if not (sep and group.startswith("[") and group.endswith("]") and key):
        raise ValueError(
            f'banks: deck {deck.get("deck")}: bank_control {spec!r} is not'
            ' "[Group],key"')
    return f'["{group}", "{key}"]'


def _hex(n):
    return f"0x{n:02X}"


def generate(profile, prefix):
    """JS for every deck's hot cue bank and sampler bank. [] if none declared."""
    decks = _decks(profile)
    if not decks:
        return []

    out = ["// ---------------------------------------------------------------",
           "// Hot cue banks and the sampler bank behind the same buttons.",
           "// ---------------------------------------------------------------",
           ""]

    # The table the handlers read. Keeping it as data rather than baking the
    # numbers into each function means a re-export is a one-line diff.
    out.append(f"{prefix}.BANKS = [")
    for d in decks:
        out.append("    {")
        out.append(f'        deck: "{d["deck"]}", group: "{d["group"]}",')
        out.append(f'        channel: {d.get("channel", 1) - 1},')
        out.append(f'        hotcues: {list(d.get("hotcues") or [])},')
        out.append(f'        perBank: {d.get("per_bank", 4)},'
                   f' banks: {d.get("banks", 2)},')
        out.append(f'        bankLed: {d.get("bank_led", "null")},')
        samplers = d.get("samplers") or []
        out.append("        samplers: ["
                   + ", ".join(f'"{s}"' for s in samplers) + "],")
        out.append(f'        samplerPads: {list(d.get("sampler_buttons") or [])},')
        out.append(f'        samplerModeLed: {d.get("sampler_mode_led", "null")},')
        out.append(f"        bankControl: {_bank_control(d)},")
        out.append("    },")
    out += ["];", ""]

    out += [
        "// Which four hot cues each deck's buttons currently address, and",
        "// whether its sampler pads play while held. Both are mapping state:",
        "// Mixxx has no control to read them back from. The bank is also",
        "// published to bankControl, when the profile names one and the skin",
        "// has it, so a screen showing four cues can show the same four.",
        f"{prefix}.bank = [];",
        f"{prefix}.samplerHold = [];",
        f"{prefix}.bankPublished = [];",
        "",
        f"{prefix}.initBanks = function () {{",
        f"    for (var i = 0; i < {prefix}.BANKS.length; i++) {{",
        f"        {prefix}.bank[i] = 0;",
        f"        {prefix}.samplerHold[i] = false;",
        f"        {prefix}.connectBank(i);",
        f"        {prefix}.paintBank(i);",
        "    }",
        "};",
        "",
        "// The control is the skin's, so it exists only under a skin that",
        "// declares it, and only once that skin has loaded - which in a",
        "// QOpenGL build of Mixxx is after the controllers have started.",
        "// Connecting doubles as the test for it, so a failed connect is",
        "// retried once a second for a while, and a success publishes the",
        "// bank the deck is on by then. No control at all, and the bank stays",
        "// private to the mapping. Following the control as well as writing",
        "// it keeps the pads right if anything else ever sets it.",
        f"{prefix}.bankRetryMs = 1000;",
        f"{prefix}.bankRetries = 30;",
        "",
        f"{prefix}.connectBankControl = function (i) {{",
        f"    var d = {prefix}.BANKS[i];",
        "    var conn = engine.makeConnection(d.bankControl[0], d.bankControl[1],",
        "        function (value) {",
        "            var b = Math.round(value);",
        f"            if (b >= 0 && b < d.banks && b !== {prefix}.bank[i]) {{",
        f"                {prefix}.bank[i] = b;",
        f"                {prefix}.paintBank(i);",
        "            }",
        "        });",
        f"    {prefix}.bankPublished[i] = conn !== undefined;",
        f"    {prefix}.publishBank(i);",
        f"    return {prefix}.bankPublished[i];",
        "};",
        "",
        f"{prefix}.followBankControl = function (i) {{",
        f"    {prefix}.bankPublished[i] = false;",
        f"    if ({prefix}.BANKS[i].bankControl === null",
        f"            || {prefix}.connectBankControl(i)) {{",
        "        return;",
        "    }",
        "    var tries = 0;",
        f"    var timer = engine.beginTimer({prefix}.bankRetryMs, function () {{",
        "        tries++;",
        f"        if ({prefix}.connectBankControl(i) || tries >= {prefix}.bankRetries) {{",
        "            engine.stopTimer(timer);",
        "        }",
        "    });",
        "};",
        "",
        f"{prefix}.publishBank = function (i) {{",
        f"    var d = {prefix}.BANKS[i];",
        f"    if ({prefix}.bankPublished[i]) {{",
        f"        engine.setValue(d.bankControl[0], d.bankControl[1], {prefix}.bank[i]);",
        "    }",
        "};",
        "",
        f"{prefix}.shutdownBanks = function () {{",
        f"    for (var i = 0; i < {prefix}.BANKS.length; i++) {{",
        f"        var d = {prefix}.BANKS[i];",
        "        for (var p = 0; p < d.hotcues.length; p++) {",
        "            midi.sendShortMsg(0x90 | d.channel, d.hotcues[p], 0);",
        "        }",
        "        for (var s = 0; s < d.samplerPads.length; s++) {",
        "            midi.sendShortMsg(0x90 | d.channel, d.samplerPads[s], 0);",
        "        }",
        "        if (d.bankLed !== null) {",
        "            midi.sendShortMsg(0x90 | d.channel, d.bankLed, 0);",
        "        }",
        "        if (d.samplerModeLed !== null) {",
        "            midi.sendShortMsg(0x90 | d.channel, d.samplerModeLed, 0);",
        "        }",
        "    }",
        "};",
        "",
        "// Every hot cue in every bank is watched, not just the visible four:",
        "// setting a cue in the other bank has to be true the moment the bank",
        "// is switched, not one press later.",
        f"{prefix}.connectBank = function (i) {{",
        f"    var d = {prefix}.BANKS[i];",
        "    var total = d.perBank * d.banks;",
        "    for (var n = 1; n <= total; n++) {",
        '        engine.makeConnection(d.group, "hotcue_" + n + "_status",',
        f"            function () {{ {prefix}.paintBank(i); }});",
        "    }",
        "    for (var s = 0; s < d.samplers.length; s++) {",
        '        engine.makeConnection(d.samplers[s], "track_loaded",',
        f"            function () {{ {prefix}.paintBank(i); }});",
        '        engine.makeConnection(d.samplers[s], "play",',
        f"            function () {{ {prefix}.paintBank(i); }});",
        "    }",
        f"    {prefix}.followBankControl(i);",
        "};",
        "",
        f"{prefix}.paintBank = function (i) {{",
        f"    var d = {prefix}.BANKS[i];",
        f"    var base = {prefix}.bank[i] * d.perBank;",
        "    var status = 0x90 | d.channel;",
        "    for (var p = 0; p < d.hotcues.length; p++) {",
        '        var set = engine.getValue(d.group, "hotcue_" + (base + p + 1)',
        '            + "_status") > 0;',
        "        midi.sendShortMsg(status, d.hotcues[p], set ? 0x7F : 0x00);",
        "    }",
        "    // A sampler pad is lit when it holds something and brighter is",
        "    // not available here, so playing and loaded look the same.",
        "    for (var s = 0; s < d.samplerPads.length && s < d.samplers.length;"
        " s++) {",
        '        var live = engine.getValue(d.samplers[s], "track_loaded") > 0;',
        "        midi.sendShortMsg(status, d.samplerPads[s], live ? 0x7F : 0x00);",
        "    }",
        "    if (d.bankLed !== null) {",
        "        // The light says 'not the first bank', which on a two-bank",
        "        // controller reads as 'cues 5-8'.",
        "        midi.sendShortMsg(status, d.bankLed,",
        f"            {prefix}.bank[i] > 0 ? 0x7F : 0x00);",
        "    }",
        "    if (d.samplerModeLed !== null) {",
        "        midi.sendShortMsg(status, d.samplerModeLed,",
        f"            {prefix}.samplerHold[i] ? 0x7F : 0x00);",
        "    }",
        "};",
        "",
        "// --- hot cue pads ----------------------------------------------",
        "",
        f"{prefix}.hotcuePress = function (i, pad, value) {{",
        "    if (value === 0) {",
        "        return;   // release; a hot cue acts on the press",
        "    }",
        f"    var d = {prefix}.BANKS[i];",
        f"    var n = {prefix}.bank[i] * d.perBank + pad + 1;",
        '    engine.setValue(d.group, "hotcue_" + n + "_activate", 1);',
        '    engine.setValue(d.group, "hotcue_" + n + "_activate", 0);',
        "};",
        "",
        f"{prefix}.hotcueClear = function (i, pad, value) {{",
        "    if (value === 0) {",
        "        return;",
        "    }",
        f"    var d = {prefix}.BANKS[i];",
        f"    var n = {prefix}.bank[i] * d.perBank + pad + 1;",
        '    engine.setValue(d.group, "hotcue_" + n + "_clear", 1);',
        "};",
        "",
        f"{prefix}.toggleBank = function (i, value) {{",
        "    if (value === 0) {",
        "        return;",
        "    }",
        f"    var d = {prefix}.BANKS[i];",
        f"    {prefix}.bank[i] = ({prefix}.bank[i] + 1) % d.banks;",
        f"    {prefix}.publishBank(i);",
        f"    {prefix}.paintBank(i);",
        "};",
        "",
        "// --- sampler pads ----------------------------------------------",
        "",
        f"{prefix}.samplerPress = function (i, pad, value) {{",
        f"    var d = {prefix}.BANKS[i];",
        "    var s = d.samplers[pad];",
        "    if (s === undefined) {",
        "        return;",
        "    }",
        '    if (engine.getValue(s, "track_loaded") === 0) {',
        "        if (value !== 0) {",
        "            // Nothing in the slot yet, so the press loads rather than",
        "            // plays, which is what the hardware's own manual promises.",
        '            engine.setValue(s, "LoadSelectedTrack", 1);',
        "        }",
        "        return;",
        "    }",
        f"    if ({prefix}.samplerHold[i]) {{",
        "        // Trigger mode: sound for exactly as long as the pad is down.",
        "        if (value !== 0) {",
        '            engine.setValue(s, "cue_gotoandplay", 1);',
        "        } else {",
        '            engine.setValue(s, "play", 0);',
        '            engine.setValue(s, "playposition", 0);',
        "        }",
        "        return;",
        "    }",
        "    if (value === 0) {",
        "        return;",
        "    }",
        '    if (engine.getValue(s, "play") > 0) {',
        '        engine.setValue(s, "play", 0);',
        '        engine.setValue(s, "playposition", 0);',
        "    } else {",
        '        engine.setValue(s, "cue_gotoandplay", 1);',
        "    }",
        "};",
        "",
        f"{prefix}.samplerEject = function (i, pad, value) {{",
        "    if (value === 0) {",
        "        return;",
        "    }",
        f"    var s = {prefix}.BANKS[i].samplers[pad];",
        "    if (s !== undefined) {",
        '        engine.setValue(s, "eject", 1);',
        '        engine.setValue(s, "eject", 0);',
        "    }",
        "};",
        "",
        f"{prefix}.toggleSamplerHold = function (i, value) {{",
        "    if (value === 0) {",
        "        return;",
        "    }",
        f"    {prefix}.samplerHold[i] = !{prefix}.samplerHold[i];",
        f"    {prefix}.paintBank(i);",
        "};",
        "",
        f"{prefix}.toggleSamplerRepeat = function (i, value) {{",
        "    if (value === 0) {",
        "        return;",
        "    }",
        f"    var d = {prefix}.BANKS[i];",
        '    var on = engine.getValue(d.samplers[0], "repeat") ? 0 : 1;',
        "    for (var s = 0; s < d.samplers.length; s++) {",
        '        engine.setValue(d.samplers[s], "repeat", on);',
        "    }",
        "};",
        "",
        f"{prefix}.samplerGain = function (i, value) {{",
        "    // Signed relative: 1..30 clockwise, 127..98 anticlockwise.",
        "    var delta = (value < 64 ? value : value - 128) / 64;",
        f"    var d = {prefix}.BANKS[i];",
        "    for (var s = 0; s < d.samplers.length; s++) {",
        '        var v = engine.getValue(d.samplers[s], "pregain") + delta;',
        '        engine.setValue(d.samplers[s], "pregain",',
        "            Math.max(0, Math.min(4, v)));",
        "    }",
        "};",
        "",
        f"{prefix}.samplerGainReset = function (i, value) {{",
        "    if (value === 0) {",
        "        return;",
        "    }",
        f"    var d = {prefix}.BANKS[i];",
        "    for (var s = 0; s < d.samplers.length; s++) {",
        '        engine.setValue(d.samplers[s], "pregain", 1);',
        "    }",
        "};",
        "",
    ]

    # One thin named function per button, because a Mixxx <key> can only name a
    # function, never call one with arguments.
    out.append("// Per-button entry points; a mapping <key> cannot pass arguments.")
    for i, d in enumerate(decks):
        deck = d["deck"]
        for pad in range(len(d.get("hotcues") or [])):
            out += [
                f"{prefix}.hotcue{deck}{pad + 1} = function (ch, ctrl, value) {{",
                f"    {prefix}.hotcuePress({i}, {pad}, value);",
                "};",
                f"{prefix}.hotcue{deck}{pad + 1}Clear = function (ch, ctrl, value) {{",
                f"    {prefix}.hotcueClear({i}, {pad}, value);",
                "};",
            ]
        for pad in range(len(d.get("sampler_buttons") or [])):
            out += [
                f"{prefix}.sampler{deck}{pad + 1} = function (ch, ctrl, value) {{",
                f"    {prefix}.samplerPress({i}, {pad}, value);",
                "};",
                f"{prefix}.sampler{deck}{pad + 1}Eject = function (ch, ctrl, value) {{",
                f"    {prefix}.samplerEject({i}, {pad}, value);",
                "};",
            ]
        out += [
            f"{prefix}.bank{deck} = function (ch, ctrl, value) {{",
            f"    {prefix}.toggleBank({i}, value);",
            "};",
            f"{prefix}.samplerHold{deck} = function (ch, ctrl, value) {{",
            f"    {prefix}.toggleSamplerHold({i}, value);",
            "};",
            f"{prefix}.samplerRepeat{deck} = function (ch, ctrl, value) {{",
            f"    {prefix}.toggleSamplerRepeat({i}, value);",
            "};",
            f"{prefix}.samplerGain{deck} = function (ch, ctrl, value) {{",
            f"    {prefix}.samplerGain({i}, value);",
            "};",
            f"{prefix}.samplerGainReset{deck} = function (ch, ctrl, value) {{",
            f"    {prefix}.samplerGainReset({i}, value);",
            "};",
            "",
        ]
    return out


def generate_gangs(profile, prefix):
    """One button driving the same control on several groups at once.

    A mixer's global buttons -- quantize, slip -- are per deck in Mixxx but
    single on the panel. Binding one of them declaratively would silently make
    it a deck A button.
    """
    gangs = profile.data.get("gangs") or []
    if not gangs:
        return []
    out = ["// One button, same control on several decks.", ""]
    lit = [g for g in gangs if g.get("led") is not None]
    for g in gangs:
        groups = ", ".join(f'"{x}"' for x in g["groups"])
        out += [
            f"{prefix}.{g['id']} = function (ch, ctrl, value) {{",
            "    if (value === 0) {",
            "        return;",
            "    }",
            f"    var groups = [{groups}];",
            f'    var on = engine.getValue(groups[0], "{g["key"]}") ? 0 : 1;',
            "    for (var i = 0; i < groups.length; i++) {",
            f'        engine.setValue(groups[i], "{g["key"]}", on);',
            "    }",
            "};",
            "",
        ]
    if not lit:
        return out

    # A ganged button needs its lamp driven from here rather than by an
    # <output>: the button stands for several controls, and an <output> can
    # only follow one. Following the first deck is the honest reading, since
    # the button always sets them together.
    out += ["// Their lamps, which no <output> can drive: the button stands for",
            "// several controls at once.", ""]
    out.append(f"{prefix}.paintGangs = function () {{")
    for g in lit:
        ch = g.get("channel", 1) - 1
        out += [
            f'    midi.sendShortMsg(0x90 | {ch}, {g["led"]},',
            f'        engine.getValue("{g["groups"][0]}", "{g["key"]}")'
            " ? 0x7F : 0x00);",
        ]
    out += ["};", ""]
    out.append(f"{prefix}.connectGangs = function () {{")
    for g in lit:
        out += [
            f'    engine.makeConnection("{g["groups"][0]}", "{g["key"]}",',
            f"        function () {{ {prefix}.paintGangs(); }});",
        ]
    out += ["};", ""]
    out.append(f"{prefix}.gangLedsOff = function () {{")
    for g in lit:
        ch = g.get("channel", 1) - 1
        out.append(f'    midi.sendShortMsg(0x90 | {ch}, {g["led"]}, 0);')
    out += ["};", ""]
    return out


def generate_loops(profile, prefix):
    """A loop button that starts a new loop rather than recalling the old one.

    `reloop_toggle` alone re-enters the loop that was last set, which is wrong
    for a button the user presses wherever they happen to be: leave a loop,
    press again, and the deck jumps backwards to where the last one started.
    `beatloop_activate` alone cannot switch a loop off. Together they give the
    behaviour the panel implies -- press to loop here, press again to leave.
    """
    loops = profile.data.get("loop_buttons") or []
    if not loops:
        return []
    out = ["// Loop on/off, where 'on' means here and not where it was last time.",
           ""]
    for lp in loops:
        g = lp["group"]
        out += [
            f"{prefix}.{lp['id']} = function (ch, ctrl, value) {{",
            "    if (value === 0) {",
            "        return;",
            "    }",
            f'    if (engine.getValue("{g}", "loop_enabled") > 0) {{',
            f'        engine.setValue("{g}", "reloop_toggle", 1);',
            "    } else {",
            "        // Takes its length from beatloop_size, which the encoder",
            "        // sets, and its start from the play position.",
            f'        engine.setValue("{g}", "beatloop_activate", 1);',
            f'        engine.setValue("{g}", "beatloop_activate", 0);',
            "    }",
            "};",
            "",
        ]
    return out


def generate_actions(profile, prefix):
    """A button that writes one fixed value to one control.

    Needed whenever the value itself carries the meaning rather than just
    saying "pressed": `CloneFromDeck` takes the deck number to copy from, so a
    declarative binding would send it 127 and clone from a deck that does not
    exist.
    """
    actions = profile.data.get("actions") or []
    if not actions:
        return []
    out = ["// Buttons whose value means something other than 'pressed'.", ""]
    for a in actions:
        out += [
            f"{prefix}.{a['id']} = function (ch, ctrl, value) {{",
            "    if (value === 0) {",
            "        return;",
            "    }",
            f'    engine.setValue("{a["group"]}", "{a["key"]}", {a["value"]});',
            "};",
            "",
        ]
    return out


def generate_focus(profile, prefix):
    """Move library focus straight to the track list, and back.

    `GoToItem` only enters the track list from a leaf node in the tree; on a
    parent folder it expands instead, which leaves no way to reach the tracks
    without walking to the bottom. `[Library],focused_widget` is writable and
    goes there from anywhere.
    """
    spec = profile.data.get("library_focus")
    if not spec:
        return []
    a, b = spec.get("between", [2, 3])
    return [
        "// Library focus: straight to the track list from wherever the tree is.",
        "",
        f"{prefix}.{spec['id']} = function (ch, ctrl, value) {{",
        "    if (value === 0) {",
        "        return;",
        "    }",
        '    var now = engine.getValue("[Library]", "focused_widget");',
        f'    engine.setValue("[Library]", "focused_widget",',
        f"        now === {b} ? {a} : {b});",
        "};",
        "",
    ]
