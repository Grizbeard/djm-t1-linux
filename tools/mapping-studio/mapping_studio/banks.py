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


def _second_mode(profile):
    """The profile's optional `banks.second_mode`, validated.

    What the controller's own SAMPLER mode does with the four cue buttons,
    ACTIVE and the AUTO LOOP encoder: `modes` lists what each value of
    `control`, "[Group],key", selects. The control is the skin's; see
    followSecondMode."""
    spec = (profile.data.get("banks") or {}).get("second_mode")
    if not spec:
        return None
    group, sep, key = (spec.get("control") or "").partition(",")
    if not (sep and group.startswith("[") and group.endswith("]") and key):
        raise ValueError(
            f"banks: second_mode control {spec.get('control')!r} is not"
            ' "[Group],key"')
    modes = list(spec.get("modes") or [])
    unknown = [m for m in modes if m not in SECOND_MODES]
    if not modes or unknown or modes[0] != "sampler":
        raise ValueError(
            f"banks: second_mode modes {modes!r} must start with \"sampler\""
            f" and be some of {', '.join(SECOND_MODES)}")
    return group, key, modes


# What SAMPLER mode can be made to do.
SECOND_MODES = ("sampler", "cueloop", "looproll")


def _second_mode_table(profile, prefix):
    spec = _second_mode(profile)
    if spec is None:
        control, modes = "null", ["sampler"]
    else:
        group, key, modes = spec
        control = f'["{group}", "{key}"]'
    return [
        "// What the controller's SAMPLER mode does with the cue buttons:",
        "// the mode `control` selects, by index into `modes`.",
        f"{prefix}.SECOND_MODE = {{",
        f"    control: {control},",
        "    modes: [" + ", ".join(f'"{m}"' for m in modes) + "],",
        "};",
        "",
    ]


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
    out += _second_mode_table(profile, prefix)

    out += [
        "// Which four hot cues each deck's buttons currently address, and",
        "// whether its sampler pads play while held. Both are mapping state:",
        "// Mixxx has no control to read them back from. The bank is also",
        "// published to bankControl, when the profile names one and the skin",
        "// has it, so a screen showing four cues can show the same four.",
        f"{prefix}.bank = [];",
        f"{prefix}.samplerHold = [];",
        f"{prefix}.bankPublished = [];",
        "// The hot cue each pad's press started, for its release.",
        f"{prefix}.hotcueHeld = [];",
        "",
        f"{prefix}.initBanks = function () {{",
        f"    for (var i = 0; i < {prefix}.BANKS.length; i++) {{",
        f"        {prefix}.bank[i] = 0;",
        f"        {prefix}.samplerHold[i] = false;",
        f"        {prefix}.hotcueHeld[i] = [];",
        f"        {prefix}.rollSet[i] = 0;",
        f"        {prefix}.rollHeld[i] = [];",
        f"        {prefix}.connectBank(i);",
        f"        {prefix}.paintBank(i);",
        "    }",
        f"    {prefix}.followSecondMode();",
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
        '    engine.makeConnection(d.group, "loop_enabled",',
        f"        function () {{ {prefix}.paintBank(i); }});",
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
        "    if (d.bankLed !== null) {",
        "        // The light says 'not the first bank', which on a two-bank",
        "        // controller reads as 'cues 5-8'.",
        "        midi.sendShortMsg(status, d.bankLed,",
        f"            {prefix}.bank[i] > 0 ? 0x7F : 0x00);",
        "    }",
        f"    {prefix}.paintSecondLayer(i);",
        "};",
        "",
        "// --- hot cue pads ----------------------------------------------",
        "",
        "// Press and release go to Mixxx as they happen, which is what makes",
        "// a hot cue on a paused deck play only while held and stop back on",
        "// the cue when let go; on a playing deck the press jumps and the deck",
        "// plays on. The release goes to the cue the press started, even if",
        "// the bank changed while the pad was held.",
        f"{prefix}.hotcuePress = function (i, pad, value) {{",
        f"    var d = {prefix}.BANKS[i];",
        "    if (value === 0) {",
        f"        var held = {prefix}.hotcueHeld[i][pad];",
        "        if (held) {",
        f"            {prefix}.hotcueHeld[i][pad] = 0;",
        '            engine.setValue(d.group, "hotcue_" + held + "_activate", 0);',
        "        }",
        "        return;",
        "    }",
        f"    var n = {prefix}.bank[i] * d.perBank + pad + 1;",
        f"    {prefix}.hotcueHeld[i][pad] = n;",
        '    engine.setValue(d.group, "hotcue_" + n + "_activate", 1);',
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
        f"{prefix}.samplerPlay = function (i, pad, value) {{",
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
        f"{prefix}.samplerEjectSlot = function (i, pad, value) {{",
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
        f"{prefix}.samplerToggleHold = function (i, value) {{",
        "    if (value === 0) {",
        "        return;",
        "    }",
        f"    {prefix}.samplerHold[i] = !{prefix}.samplerHold[i];",
        f"    {prefix}.paintBank(i);",
        "};",
        "",
        f"{prefix}.samplerToggleRepeat = function (i, value) {{",
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

    out += _second_mode_js(prefix)

    # One thin named function per button, because a Mixxx <key> can only name a
    # function, never call one with arguments.
    out.append("// Per-button entry points; a mapping <key> cannot pass arguments.")
    for i, d in enumerate(decks):
        deck = d["deck"]
        for pad in range(len(d.get("hotcues") or [])):
            out += [
                f"{prefix}.hotcue{deck}{pad + 1} = function (ch, ctrl, value, status) {{",
                "    // A note-off is a release, whatever its velocity.",
                f"    {prefix}.hotcuePress({i}, {pad}, (status & 0xF0) === 0x80 ? 0 : value);",
                "};",
                f"{prefix}.hotcue{deck}{pad + 1}Clear = function (ch, ctrl, value) {{",
                f"    {prefix}.hotcueClear({i}, {pad}, value);",
                "};",
            ]
        for pad in range(len(d.get("sampler_buttons") or [])):
            out += [
                f"{prefix}.sampler{deck}{pad + 1} = function (ch, ctrl, value, status) {{",
                "    // A note-off is a release, whatever its velocity.",
                f"    {prefix}.samplerPress({i}, {pad}, (status & 0xF0) === 0x80 ? 0 : value);",
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


_SECOND_MODE_JS = """
// --- what SAMPLER mode does --------------------------------------
//
// The firmware's SAMPLER mode (the SELECT button) re-addresses the four cue
// buttons, ACTIVE and the AUTO LOOP encoder, so their presses arrive here.
// What they do is picked on the skin's options page:
//
//   sampler    the deck's four samplers, as always
//   cueloop    each button loops from its hot cue, for beatloop_size beats:
//              the length AUTO LOOP sets. Pressing it again leaves the loop,
//              ACTIVE switches cues 1-4 and 5-8, SHIFT + button clears the cue.
//   looproll   each button rolls a loop while it is held, with slip on, so
//              the track carries on underneath and comes back where it would
//              have been. The buttons roll 1/8, 1/4, 1/2 and 1 beat, and ACTIVE
//              (lit) switches them to 1/32, 1/16, 1/8 and 1/4.
//
// AUTO LOOP is not part of this: the profile binds its SAMPLER-mode addresses
// to the same loop and beatjump controls as in hot cue mode.
// Until the skin's control exists, or under a skin without it, it is sampler.
@P@.secondMode = "sampler";
@P@.secondModeRetryMs = 1000;
@P@.secondModeRetries = 30;

// Loop roll lengths in beats, one per button: ACTIVE picks the set.
@P@.ROLL_SETS = [
    [0.125, 0.25, 0.5, 1],
    [0.03125, 0.0625, 0.125, 0.25],
];
@P@.rollSet = [];
// The length each button's press started rolling, for its release.
@P@.rollHeld = [];

@P@.setSecondMode = function (value) {
    var mode = @P@.SECOND_MODE.modes[Math.round(value)];
    if (mode === undefined || mode === @P@.secondMode) {
        return;
    }
    // A roll still held would never get its release.
    @P@.endRolls();
    @P@.secondMode = mode;
    for (var i = 0; i < @P@.BANKS.length; i++) {
        @P@.paintBank(i);
    }
};

// The control is the skin's, so like the bank controls it may only appear
// after the controllers have started: connecting is retried for a while.
@P@.connectSecondMode = function () {
    var c = @P@.SECOND_MODE.control;
    var conn = engine.makeConnection(c[0], c[1], @P@.setSecondMode);
    if (conn === undefined) {
        return false;
    }
    @P@.setSecondMode(engine.getValue(c[0], c[1]));
    return true;
};

@P@.followSecondMode = function () {
    if (@P@.SECOND_MODE.control === null || @P@.connectSecondMode()) {
        return;
    }
    var tries = 0;
    var timer = engine.beginTimer(@P@.secondModeRetryMs, function () {
        tries++;
        if (@P@.connectSecondMode() || tries >= @P@.secondModeRetries) {
            engine.stopTimer(timer);
        }
    });
};

@P@.endRolls = function () {
    for (var i = 0; i < @P@.BANKS.length; i++) {
        for (var pad = 0; pad < @P@.BANKS[i].samplerPads.length; pad++) {
            @P@.rollPress(i, pad, 0);
        }
    }
};

// SAMPLER-mode lights: what is loaded, which cues exist, what is rolling.
@P@.paintSecondLayer = function (i) {
    var d = @P@.BANKS[i];
    var status = 0x90 | d.channel;
    var mode = @P@.secondMode;
    var base = @P@.bank[i] * d.perBank;
    for (var p = 0; p < d.samplerPads.length; p++) {
        var lit;
        if (mode === "cueloop") {
            lit = engine.getValue(d.group, "hotcue_" + (base + p + 1) + "_status") > 0;
        } else if (mode === "looproll") {
            lit = !!@P@.rollHeld[i][p];
        } else {
            // Lit when it holds something; there is no brighter level, so
            // playing and loaded look the same.
            lit = p < d.samplers.length
                && engine.getValue(d.samplers[p], "track_loaded") > 0;
        }
        midi.sendShortMsg(status, d.samplerPads[p], lit ? 0x7F : 0x00);
    }
    if (d.samplerModeLed !== null) {
        var on = (mode === "cueloop") ? @P@.bank[i] > 0
            : (mode === "looproll") ? @P@.rollSet[i] > 0
            : @P@.samplerHold[i];
        midi.sendShortMsg(status, d.samplerModeLed, on ? 0x7F : 0x00);
    }
};

// -- the buttons --

@P@.cueLoopPress = function (i, pad, value) {
    if (value === 0) {
        return;
    }
    var d = @P@.BANKS[i];
    var n = @P@.bank[i] * d.perBank + pad + 1;
    var cue = "hotcue_" + n;
    // Mixxx's own cue loop: a loop of beatloop_size beats from the cue, left
    // again by a second press. An empty button sets a cue here first. It
    // only sets the loop, though: from before the cue the deck plays on to
    // it, so the button jumps there first, the jump a hot cue press makes -
    // unless this press is the one that leaves the loop.
    var leaving = engine.getValue(d.group, "loop_enabled") > 0
        && Math.abs(engine.getValue(d.group, "loop_start_position")
            - engine.getValue(d.group, cue + "_position")) < 1;
    if (!leaving && engine.getValue(d.group, cue + "_status") > 0) {
        engine.setValue(d.group, cue + "_goto", 1);
        engine.setValue(d.group, cue + "_goto", 0);
    }
    engine.setValue(d.group, cue + "_cueloop", 1);
    engine.setValue(d.group, cue + "_cueloop", 0);
};

@P@.rollPress = function (i, pad, value) {
    var d = @P@.BANKS[i];
    if (value === 0) {
        var held = @P@.rollHeld[i][pad];
        if (held) {
            @P@.rollHeld[i][pad] = 0;
            engine.setValue(d.group, "beatlooproll_" + held + "_activate", 0);
            @P@.paintBank(i);
        }
        return;
    }
    var size = @P@.ROLL_SETS[@P@.rollSet[i]][pad];
    if (size === undefined) {
        return;
    }
    @P@.rollHeld[i][pad] = size;
    engine.setValue(d.group, "beatlooproll_" + size + "_activate", 1);
    @P@.paintBank(i);
};

@P@.samplerPress = function (i, pad, value) {
    if (@P@.secondMode === "cueloop") {
        @P@.cueLoopPress(i, pad, value);
    } else if (@P@.secondMode === "looproll") {
        @P@.rollPress(i, pad, value);
    } else {
        @P@.samplerPlay(i, pad, value);
    }
};

// SHIFT + button.
@P@.samplerEject = function (i, pad, value) {
    if (@P@.secondMode === "cueloop") {
        @P@.hotcueClear(i, pad, value);
    } else if (@P@.secondMode === "sampler") {
        @P@.samplerEjectSlot(i, pad, value);
    }
};

// ACTIVE.
@P@.toggleSamplerHold = function (i, value) {
    if (@P@.secondMode === "cueloop") {
        @P@.toggleBank(i, value);
    } else if (@P@.secondMode === "looproll") {
        @P@.toggleRollSet(i, value);
    } else {
        @P@.samplerToggleHold(i, value);
    }
};

@P@.toggleRollSet = function (i, value) {
    if (value === 0) {
        return;
    }
    // A roll held across the switch still ends on its own length.
    @P@.rollSet[i] = (@P@.rollSet[i] + 1) % @P@.ROLL_SETS.length;
    @P@.paintBank(i);
};

// SHIFT + ACTIVE.
@P@.toggleSamplerRepeat = function (i, value) {
    if (@P@.secondMode === "sampler") {
        @P@.samplerToggleRepeat(i, value);
    }
};

"""


def _second_mode_js(prefix):
    """The SAMPLER-mode dispatch, and the cue loop and loop roll modes."""
    return _SECOND_MODE_JS.replace("@P@", prefix).split("\n")[1:]


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
