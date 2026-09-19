"""Generate the pad-mode layer of a Mixxx script.

Mixxx has no notion of a performance-pad mode. A controller that has one --
where holding a modifier and pressing a pad changes what all eight pads do --
has to carry that state in its own mapping. So this emits three things:

  * a mode variable per deck, switched by the modifier+pad notes the studio
    captured;
  * a dispatcher, so one pad press does something different in each mode;
  * a repaint, so the pads show the mode you are in.

The repaint is the point. On the hardware's own software the modes are told
apart by colour, and a mapping that lights every pad the same colour loses the
one cue that makes eight identical rubber squares usable. Hot cue mode is
special-cased to read Mixxx's own `hotcue_N_color` and quantise it to whatever
depth the device has, so the pads match the colours on the waveform rather than
a palette someone guessed.

What a pad *does* in each mode is deliberately conservative: the modes that map
cleanly onto Mixxx controls are wired up, and the ones that do not (Scratch
Bank, Pitch Play, which need library features Mixxx does not expose) are left as
commented stubs rather than approximated.

SPDX-License-Identifier: MIT
"""

from . import colour

# What a pad does per mode, as (control key template, needs_value).
# {n} is the 1-based pad number. None means "no sensible Mixxx equivalent".
MODE_ACTIONS = {
    "hotcue": {
        "row1": "hotcue_{n}_activate",
        "row2": "hotcue_{n}_activate",
        "shift": "hotcue_{n}_clear",
        "comment": "8 hot cues; SHIFT clears. Colour comes from Mixxx.",
    },
    "autoloop": {
        "sizes": [1, 2, 4, 8],
        "row1": "beatloop_{size}_toggle",
        "row2": ["loop_move_1_backward", "loop_halve", "loop_double",
                 "loop_move_1_forward"],
        "comment": "row 1 sets a loop length, row 2 moves and resizes it.",
    },
    "manualloop": {
        "row1": ["loop_in", "loop_out", "reloop_toggle", "reloop_andstop"],
        "row2": ["loop_move_1_backward", "loop_halve", "loop_double",
                 "loop_move_1_forward"],
        "comment": "manual loop in/out, then move and resize.",
    },
    "sampler": {
        "sampler": True,
        "shift": "stop",
        "comment": "pads 1-8 fire samplers 1-8; SHIFT stops one.",
    },
    "looproll": {
        "sizes": ["0.125", "0.25", "0.5", "1"],
        "row1": "beatlooproll_{size}_activate",
        "row2": ["beatjump_backward", "beatjump_size_halve",
                 "beatjump_size_double", "beatjump_forward"],
        "comment": "row 1 rolls 1/8 to 1 beat, row 2 beat-jumps.",
    },
    "beatgrid": {
        "row1": ["beats_translate_curpos", "beats_translate_earlier",
                 "beats_translate_later", "beats_translate_match_alignment"],
        "row2": None,
        "comment": "row 1 adjusts the grid; row 2 unassigned.",
    },
    "pitchplay": {"row1": None, "row2": None,
                  "comment": "needs key-shifted cue playback; no Mixxx equivalent."},
    "scratchbank": {"row1": None, "row2": None,
                    "comment": "loads library files to a deck; not exposed by Mixxx."},
}


def _rgb(spec, levels):
    """A colour spec from the profile to device component values."""
    if isinstance(spec, (list, tuple)):
        return [max(0, min(levels - 1, int(v))) for v in spec]
    return [levels - 1] * 3


def generate(profile, prefix):
    """Return the pad-mode section of the script, or [] if not applicable."""
    pm = profile.data.get("pad_modes") or {}
    modes = pm.get("modes") or {}
    select = pm.get("select") or {}
    decks = pm.get("decks") or {}
    if not (modes and select and decks):
        return []

    led = colour.spec_from(profile.data.get("led") or {})
    levels = int(led.get("levels", 4))
    sh = led.get("shift") or {"r": 4, "g": 2, "b": 0}
    bright = led.get("bright_bit")

    L = []
    a = L.append
    a("// ---------------------------------------------------------------")
    a("// Performance pad modes.")
    a("//")
    a("// Mixxx has no pad modes, so the mapping holds the mode itself: the")
    a("// MODE button plus a pad selects one, every pad then dispatches on it,")
    a("// and the pads are repainted so you can see which mode you are in.")
    a("")
    a(f"{prefix}.PAD_COUNT = 8;")
    a("")
    a("// Which mode each MODE+pad note selects.")
    a(f"{prefix}.MODE_SELECT = {{")
    for note, mode in sorted(select.items(), key=lambda kv: int(kv[0])):
        label = (modes.get(mode) or {}).get("label", mode)
        a(f"    {note}: \"{mode}\",".ljust(34) + f"// {label}")
    a("};")
    a("")
    a("// Colour per mode. Hot cue is the exception: it takes each pad's colour")
    a("// from Mixxx so the pads match the cue colours on the waveform.")
    a(f"{prefix}.MODE_COLOUR = {{")
    for name, spec in modes.items():
        col = spec.get("colour")
        if col == "hotcue":
            unset = _rgb(spec.get("unset", [1, 0, 0]), levels)
            a(f"    {name}: {{ fromHotcue: true, "
              f"unset: [{unset[0]}, {unset[1]}, {unset[2]}] }},")
        else:
            c = _rgb(col, levels)
            pro = "   // Serato DJ Pro only" if spec.get("pro") else ""
            a(f"    {name}: {{ rgb: [{c[0]}, {c[1]}, {c[2]}] }},{pro}")
    a("};")
    a("")
    a("// Which deck each pad channel belongs to.")
    a(f"{prefix}.PAD_DECK = {{")
    for _key, info in sorted(decks.items()):
        a(f"    {info['channel']}: \"{info['group']}\",")
    a("};")
    a("")
    a(f"{prefix}.padMode = {{}};   // group -> mode name")
    a("")
    a("// -- mode selection ----------------------------------------------")
    a("")
    a(f"{prefix}.selectPadMode = function (group, note) {{")
    a(f"    var mode = {prefix}.MODE_SELECT[note];")
    a("    if (!mode) {")
    a("        return;")
    a("    }")
    a(f"    {prefix}.padMode[group] = mode;")
    a(f"    {prefix}.paintPads(group);")
    a("};")
    a("")
    a("// -- painting ----------------------------------------------------")
    a("")
    a("// Quantise a 0..255 component to the depth this device actually has.")
    a(f"{prefix}.quantise = function (v) {{")
    a(f"    return Math.max(0, Math.min({levels - 1}, "
      f"Math.round((v / 255) * {levels - 1})));")
    a("};")
    a("")
    a(f"{prefix}.paintPads = function (group) {{")
    a(f"    var mode = {prefix}.padMode[group] || \"hotcue\";")
    a(f"    var scheme = {prefix}.MODE_COLOUR[mode] || {{ rgb: [1, 1, 1] }};")
    a("    var channel = null;")
    a(f"    for (var ch in {prefix}.PAD_DECK) {{")
    a(f"        if ({prefix}.PAD_DECK[ch] === group) {{")
    a("            channel = parseInt(ch, 10);")
    a("        }")
    a("    }")
    a("    if (channel === null) {")
    a("        return;")
    a("    }")
    a(f"    for (var i = 1; i <= {prefix}.PAD_COUNT; i++) {{")
    a("        var rgb = scheme.rgb;")
    a("        var lit = true;")
    a("        if (scheme.fromHotcue) {")
    a("            // Mixxx stores a hot cue's colour as 0xRRGGBB.")
    a("            var set = engine.getValue(group, \"hotcue_\" + i + \"_enabled\");")
    a("            if (set) {")
    a("                var c = engine.getValue(group, \"hotcue_\" + i + \"_color\");")
    a(f"                rgb = [{prefix}.quantise((c >> 16) & 0xFF),")
    a(f"                       {prefix}.quantise((c >> 8) & 0xFF),")
    a(f"                       {prefix}.quantise(c & 0xFF)];")
    a("            } else {")
    a("                rgb = scheme.unset;")
    a("                lit = false;   // dim: the cue is empty")
    a("            }")
    a("        }")
    a(f"        {prefix}.setPadColour(channel, {prefix}.PAD_NOTE_BASE + i - 1,")
    a("                              rgb[0], rgb[1], rgb[2], lit);")
    a("    }")
    a("};")
    a("")
    a(f"{prefix}.paintAll = function () {{")
    a(f"    for (var ch in {prefix}.PAD_DECK) {{")
    a(f"        {prefix}.paintPads({prefix}.PAD_DECK[ch]);")
    a("    }")
    a("};")
    a("")
    a("// -- what a pad does in each mode --------------------------------")
    a("//")
    for name, spec in modes.items():
        act = MODE_ACTIONS.get(name) or {}
        a(f"//   {spec.get('label', name):14s} {act.get('comment', '')}")
    a("")
    a(f"{prefix}.padPress = function (group, pad, value, shifted) {{")
    a(f"    var mode = {prefix}.padMode[group] || \"hotcue\";")
    a(f"    var act = {prefix}.PAD_ACTION[mode];")
    a("    if (act) {")
    a("        // The whole edge is passed through. Some pad actions are gated:")
    a("        // they run while the pad is held and must be released, and")
    a("        // swallowing the release turns them into one-shots.")
    a("        act(group, pad, value > 0, shifted);")
    a("    }")
    a("};")
    a("")
    a("// A gated control follows the pad: pressed is 1, released is 0.")
    a(f"{prefix}.gate = function (group, key, down) {{")
    a("    engine.setValue(group, key, down ? 1 : 0);")
    a("};")
    a("")
    a("// A one-shot fires on the press and ignores the release.")
    a(f"{prefix}.fire = function (group, key, down) {{")
    a("    if (down) {")
    a("        engine.setValue(group, key, 1);")
    a("    }")
    a("};")
    a("")
    a(f"{prefix}.PAD_ACTION = {{")
    a("")
    a("    // Hot cues are GATED. Held from a stopped deck, a hot cue previews")
    a("    // and returns to where it was on release; that only works if the")
    a("    // release reaches Mixxx. SHIFT clears, which is a one-shot.")
    a("    hotcue: function (group, pad, down, shifted) {")
    a("        if (shifted) {")
    a(f"            {prefix}.fire(group, \"hotcue_\" + pad + \"_clear\", down);")
    a("            return;")
    a("        }")
    a(f"        {prefix}.gate(group, \"hotcue_\" + pad + \"_activate\", down);")
    a("    },")
    a("")
    a("    // Loop lengths latch: pressing again releases the loop, so these are")
    a("    // one-shots and the release must be ignored.")
    a("    autoloop: function (group, pad, down, shifted) {")
    a("        var sizes = [1, 2, 4, 8];")
    a("        var row2 = [\"loop_move_1_backward\", \"loop_halve\",")
    a("                    \"loop_double\", \"loop_move_1_forward\"];")
    a("        var key = (pad <= 4) ? \"beatloop_\" + sizes[pad - 1] + \"_toggle\"")
    a("                             : row2[pad - 5];")
    a(f"        {prefix}.fire(group, key, down);")
    a("    },")
    a("")
    a("    manualloop: function (group, pad, down, shifted) {")
    a("        var row1 = [\"loop_in\", \"loop_out\", \"reloop_toggle\",")
    a("                    \"reloop_andstop\"];")
    a("        var row2 = [\"loop_move_1_backward\", \"loop_halve\",")
    a("                    \"loop_double\", \"loop_move_1_forward\"];")
    a(f"        {prefix}.fire(group, (pad <= 4) ? row1[pad - 1] : row2[pad - 5], down);")
    a("    },")
    a("")
    a("    // One-shot, matching Serato DJ Lite: the pad triggers the sample and")
    a("    // it plays on. For hold-to-play, swap cue_gotoandplay for start_play")
    a("    // and gate it instead.")
    a("    sampler: function (group, pad, down, shifted) {")
    a("        var base = (group === \"[Channel1]\") ? 0 : 8;")
    a("        var s = \"[Sampler\" + (base + pad) + \"]\";")
    a(f"        {prefix}.fire(s, shifted ? \"stop\" : \"cue_gotoandplay\", down);")
    a("    },")
    a("")
    a("    // Loop rolls are GATED by definition: the roll lasts exactly as long")
    a("    // as the pad is held and the track snaps back when it is let go. A")
    a("    // roll that never receives its release never ends.")
    a("    looproll: function (group, pad, down, shifted) {")
    a("        var rolls = [0.125, 0.25, 0.5, 1];")
    a("        if (pad <= 4) {")
    a(f"            {prefix}.gate(group,")
    a("                     \"beatlooproll_\" + rolls[pad - 1] + \"_activate\", down);")
    a("            return;")
    a("        }")
    a("        var row2 = [\"beatjump_backward\", \"beatjump_size_halve\",")
    a("                    \"beatjump_size_double\", \"beatjump_forward\"];")
    a(f"        {prefix}.fire(group, row2[pad - 5], down);")
    a("    },")
    a("")
    a("    beatgrid: function (group, pad, down, shifted) {")
    a("        var row1 = [\"beats_translate_curpos\", \"beats_translate_earlier\",")
    a("                    \"beats_translate_later\",")
    a("                    \"beats_translate_match_alignment\"];")
    a("        if (pad <= 4) {")
    a(f"            {prefix}.fire(group, row1[pad - 1], down);")
    a("        }")
    a("    },")
    a("")
    a("    // Pitch Play needs key-shifted cue playback and Scratch Bank loads")
    a("    // library files to a deck. Mixxx exposes neither, so these select and")
    a("    // light like any other mode but do nothing on a press.")
    a("    pitchplay: function (group, pad, down, shifted) {},")
    a("    scratchbank: function (group, pad, down, shifted) {},")
    a("};")
    a("")
    a("// -- keep the pads in step with Mixxx ----------------------------")
    a("")
    a("// -- one handler per pad, per layer ------------------------------")
    a("//")
    a("// The XML binds each pad here rather than straight to a Mixxx control,")
    a("// because what a pad does depends on the mode the mapping is holding.")
    a("")
    for key, info in sorted(decks.items()):
        grp = info["group"]
        for i in range(1, 9):
            a(f"{prefix}.pad_{key}{i} = function (channel, control, value, "
              f"status, group) {{")
            a(f"    {prefix}.padPress(\"{grp}\", {i}, value, false);")
            a("};")
            a(f"{prefix}.pad_{key}{i}_shift = function (channel, control, value, "
              f"status, group) {{")
            a(f"    {prefix}.padPress(\"{grp}\", {i}, value, true);")
            a("};")
            a(f"{prefix}.pad_{key}{i}_mode = function (channel, control, value, "
              f"status, group) {{")
            a("    if (value) {")
            a(f"        {prefix}.selectPadMode(\"{grp}\", control);")
            a("    }")
            a("};")
        a("")
    a(f"{prefix}.allPadsOff = function () {{")
    a(f"    for (var ch in {prefix}.PAD_DECK) {{")
    a(f"        for (var i = 0; i < {prefix}.PAD_COUNT; i++) {{")
    a(f"            {prefix}.setPadColour(parseInt(ch, 10),")
    a(f"                                  {prefix}.PAD_NOTE_BASE + i,")
    a("                                  0, 0, 0, false);")
    a("        }")
    a("    }")
    a("};")
    a("")
    a(f"{prefix}.connectPads = function () {{")
    a(f"    for (var ch in {prefix}.PAD_DECK) {{")
    a(f"        var group = {prefix}.PAD_DECK[ch];")
    a(f"        for (var i = 1; i <= {prefix}.PAD_COUNT; i++) {{")
    a("            engine.makeConnection(group, \"hotcue_\" + i + \"_enabled\",")
    a(f"                                  function (v, g) {{ {prefix}.paintPads(g); }});")
    a("            engine.makeConnection(group, \"hotcue_\" + i + \"_color\",")
    a(f"                                  function (v, g) {{ {prefix}.paintPads(g); }});")
    a("        }")
    a("    }")
    a("};")
    a("")
    return L
