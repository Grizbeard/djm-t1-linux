"""Generate jog-wheel handling: nudge, scratch, and the vinyl button that arms it.

A jog wheel is three controls that only make sense together, which is why
binding them separately never works:

  * the rim sends a relative tick stream;
  * the platter is a touch sensor;
  * a VINYL button decides whether touching the platter scratches or does
    nothing.

Mixxx has no single control for any of this. `jog` nudges the playback rate and
is what the rim should drive when the platter is not held, but scratching goes
through engine.scratchEnable/scratchTick/scratchDisable, which are script-only.
So the whole wheel has to be generated together.

The vinyl button is a mode, not a Mixxx control: it arms the touch sensor. Its
LED is driven from the mapping's own state rather than from Mixxx, because Mixxx
has no value that corresponds to it.

SPDX-License-Identifier: MIT
"""

# A jog wheel's resolution in ticks per revolution, and the speed it emulates.
# 1024 and 33 1/3 rpm are the usual defaults and what Mixxx's own mappings use.
DEFAULT_TICKS = 1024
DEFAULT_RPM = 33 + 1 / 3
DEFAULT_ALPHA = 1.0 / 8
DEFAULT_BETA = (1.0 / 8) / 32


def generate(profile, prefix):
    """Return the jog section of the script, or [] if the profile has no jogs."""
    spec = profile.data.get("jog") or {}
    decks = spec.get("decks") or {}
    if not decks:
        return []

    ticks = spec.get("ticks", DEFAULT_TICKS)
    rpm = spec.get("rpm", DEFAULT_RPM)
    alpha = spec.get("alpha", DEFAULT_ALPHA)
    beta = spec.get("beta", DEFAULT_BETA)

    L = []
    a = L.append
    a("// ---------------------------------------------------------------")
    a("// Jog wheels.")
    a("//")
    a("// Three controls that only work together: the rim sends ticks, the")
    a("// platter is a touch sensor, and VINYL decides whether touching the")
    a("// platter scratches. Mixxx has no control for the combination, so it")
    a("// is assembled here.")
    a("")
    a(f"{prefix}.JOG_TICKS = {ticks};   // ticks per revolution")
    a(f"{prefix}.JOG_RPM = {rpm:.4f};")
    a(f"{prefix}.JOG_ALPHA = {alpha};")
    a(f"{prefix}.JOG_BETA = {beta};")
    a("")
    a("// VINYL arms the touch sensor. It is a mode the mapping holds, not a")
    a("// Mixxx control, so its LED is driven from here.")
    a(f"{prefix}.vinylMode = {{}};")
    a(f"{prefix}.scratching = {{}};")
    a("")
    a("// A relative tick: 1 is one step forward, 127 one step back.")
    a(f"{prefix}.jogDelta = function (value) {{")
    a("    return (value < 64) ? value : value - 128;")
    a("};")
    a("")

    for key, d in sorted(decks.items()):
        group = d["group"]
        deck = d.get("deck") or 1
        led_ch = d.get("vinyl_led_channel", d.get("channel", 1))
        led_note = d.get("vinyl_led_note")

        a(f"// ---- deck {key.upper()} ({group}) ----")
        a("")
        a(f"{prefix}.setVinyl_{key} = function (on) {{")
        a(f"    {prefix}.vinylMode[\"{group}\"] = on;")
        if led_note is not None:
            a("    // The LED shows whether the platter is armed.")
            a(f"    midi.sendShortMsg(0x90 + {led_ch - 1}, {led_note}, "
              f"on ? 0x7F : 0x00);")
        a("};")
        a("")
        a(f"{prefix}.vinyl_{key} = function (channel, control, value, status, group) {{")
        a("    if (value === 0) {")
        a("        return;   // toggle on the press edge")
        a("    }")
        a(f"    {prefix}.setVinyl_{key}("
          f"!{prefix}.vinylMode[\"{group}\"]);")
        a("};")
        a("")
        a(f"{prefix}.jogTouch_{key} = function (channel, control, value, status, group) {{")
        a(f"    if (!{prefix}.vinylMode[\"{group}\"]) {{")
        a("        return;   // platter is not armed; the rim still nudges")
        a("    }")
        a("    if (value > 0) {")
        a(f"        engine.scratchEnable({deck}, {prefix}.JOG_TICKS, "
          f"{prefix}.JOG_RPM,")
        a(f"                             {prefix}.JOG_ALPHA, {prefix}.JOG_BETA, true);")
        a(f"        {prefix}.scratching[\"{group}\"] = true;")
        a("    } else {")
        a(f"        engine.scratchDisable({deck}, true);")
        a(f"        {prefix}.scratching[\"{group}\"] = false;")
        a("    }")
        a("};")
        a("")
        a(f"{prefix}.jogTurn_{key} = function (channel, control, value, status, group) {{")
        a(f"    var delta = {prefix}.jogDelta(value);")
        a(f"    if ({prefix}.scratching[\"{group}\"]) {{")
        a(f"        engine.scratchTick({deck}, delta);")
        a("    } else {")
        a("        // Not scratching: nudge the playback rate, which is what the")
        a("        // rim does in pitch-bend mode.")
        a(f"        engine.setValue(\"{group}\", \"jog\", delta);")
        a("    }")
        a("};")
        a("")
        a("// SHIFT + turn scrolls quickly through the track.")
        a(f"{prefix}.jogSeek_{key} = function (channel, control, value, status, group) {{")
        a(f"    var delta = {prefix}.jogDelta(value);")
        a(f"    var pos = engine.getValue(\"{group}\", \"playposition\") || 0;")
        a(f"    engine.setValue(\"{group}\", \"playposition\",")
        a("                    Math.max(0, Math.min(1, pos + delta * 0.005)));")
        a("};")
        a("")

    a(f"{prefix}.initJogs = function () {{")
    for key, d in sorted(decks.items()):
        a(f"    {prefix}.setVinyl_{key}(false);")
    a("};")
    a("")
    return L
