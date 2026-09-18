"""Emit a Mixxx controller mapping from a profile.

Two files come out: the `.midi.xml` mapping and a `-scripts.js` scaffold holding
whatever cannot be expressed declaratively. The split follows Mixxx's own rule --
anything that is a direct control-to-value binding stays in XML, and only genuine
behaviour (toggles driven off a press edge, relative encoders, centre remapping)
becomes script.

Three things this exporter will not do quietly, because each one has already
cost someone a debugging session on this hardware:

  * A control captured as `silent` is written out as a comment, not dropped. The
    fact that a knob sends nothing is a finding; losing it means the next person
    re-tests it.
  * A control whose capture flagged a mirror is exported once, and the mirror is
    recorded in a comment. Binding both is how a crossfader ends up dragging the
    headphone mix.
  * A detented control with a measured centre that is not 64 gets its measured
    value written into the script, because that is the whole point of having
    measured it.

SPDX-License-Identifier: MIT
"""

import re
import time
from . import colour
from xml.etree import ElementTree
from xml.sax.saxutils import escape

_STATUS_BYTE = {"note": 0x90, "cc": 0xB0}


def _hex(n):
    return f"0x{n:02X}"


def _comment_safe(text):
    """Make text legal inside an XML comment.

    A double hyphen may not appear in a comment and a comment may not end in
    one, which matters here because the capture notes are written in prose and
    use ' -- ' freely. Collapse to a single hyphen rather than substituting an
    en dash: this file is parsed by Mixxx, and there is no reason to put a
    non-ASCII character into it for the sake of a comment.
    """
    s = re.sub(r"-{2,}", "-", str(text))
    return s.rstrip("-") if s.endswith("-") else s


def _status_for(binding):
    base = _STATUS_BYTE.get(binding.get("status"))
    if base is None:
        return None
    ch = max(1, int(binding.get("channel", 1))) - 1
    return base | (ch & 0x0F)


def _ident(text):
    s = re.sub(r"[^A-Za-z0-9]+", "_", text or "").strip("_")
    if not s or s[0].isdigit():
        s = f"c_{s}"
    return s


def _options(control, binding, target=None):
    """Pick the Mixxx <options> for a binding, from its kind and capture."""
    target = target or {}
    if target.get("options"):
        return list(target["options"])
    if binding.get("mode") == "relative":
        return ["selectknob"]
    if binding.get("status") == "note":
        return ["normal"]
    return ["normal"]


def _detent_usable(binding):
    """Is a detented capture good enough to build a centre remap from?

    The remap divides by (centre - min) and (max - centre), so a capture that
    never left one end produces a curve that is wrong everywhere. A pitch fader
    swept over only eight values would otherwise export a fader that does
    nothing across half its travel. Better a plain binding and a note saying so.
    """
    lo, hi, rest = binding.get("min"), binding.get("max"), binding.get("resting")
    if None in (lo, hi, rest):
        return False
    # An absolute threshold rather than a fraction of the encoding's range: a
    # device may use only part of what its encoding could express. The Reloop's
    # pitch fader is sent as 14-bit but travels about 1024 steps, so judging it
    # against a full 16384 would reject a perfectly good sweep.
    return (hi - lo) >= 100 and lo < rest < hi


def _needs_script(control, binding, target=None):
    target = target or {}
    if target.get("script"):
        return True
    if binding.get("mode") == "relative" and not target.get("options"):
        return False          # selectknob handles the common case natively
    if target.get("toggle"):
        return True
    if (control.get("detent") and binding.get("resting") not in (None, 64)
            and _detent_usable(binding)):
        return True
    return False


def build_xml(profile, layer="base", name=None, author="", description=None,
              script_file=None, prefix=None, controller_id=None, layers=None):
    p = profile
    name = name or p.data.get("name") or p.data.get("id")
    prefix = prefix or _ident(name)
    script_file = script_file or f"{name.replace(' ', '-')}-scripts.js"
    controller_id = controller_id or p.data.get("controller_id") or name

    controls, outputs, comments = [], [], []
    scripted = []
    # Mixxx loads one mapping, so every layer goes into it. That works because a
    # layer here is not a modifier the host tracks: on this hardware holding
    # SHIFT changes the note a button sends, so the layers are simply different
    # MIDI addresses. Identical addresses are emitted once -- a knob sends the
    # same CC whether or not SHIFT is held, and binding it twice is a conflict.
    layers = list(layers or p.layers or [layer])
    seen_in, seen_out = set(), set()

    for c in sorted(p.controls, key=lambda c: (c.get("section", ""), c["id"])):
        label = c.get("label", c["id"])
        for ly in layers:
            binds = (c.get("bindings") or {}).get(ly) or {}
            inp = binds.get("input")
            out = binds.get("output")
            target = p.target(c, ly) or {}
            suffix = "" if ly == layers[0] else f" ({ly})"

            if inp and inp.get("status") == "silent":
                if ly == layers[0]:
                    comments.append(f"{label}: sends no MIDI (verified silent)")
                continue

            if inp:
                addr = (inp.get("status"), inp.get("channel", 1), inp.get("number"))
                if addr in seen_in:
                    inp = None          # same message as another layer; bind once
                else:
                    seen_in.add(addr)

            if inp and not target.get("group"):
                comments.append(
                    f"{label}{suffix}: captured as {inp.get('status')} "
                    f"{inp.get('number')} but no Mixxx control chosen yet")

            if (inp and c.get("detent") and inp.get("mode") == "absolute"
                    and not _detent_usable(inp)):
                comments.append(
                    f"{label}{suffix}: marked detented but the capture only "
                    f"covers {inp.get('min')}..{inp.get('max')} resting at "
                    f"{inp.get('resting')}, too partial to build a centre "
                    f"remap from; exported as a plain binding. Re-learn it with "
                    f"a full sweep ending at the detent.")

            if inp and target.get("group") and target.get("key"):
                status = _status_for(inp)
                if status is None:
                    comments.append(f"{label}: cannot export status {inp.get('status')!r}")
                else:
                    opts = _options(c, inp, target)
                    fn_id = c["id"] if ly == layers[0] else f"{c['id']}_{ly}"
                    entry = {
                        "group": target["group"],
                        "key": target["key"],
                        "description": f"{label}{suffix}",
                        "status": status,
                        "midino": inp["number"],
                        "options": opts,
                    }
                    if inp.get("mode") == "14bit" and inp.get("lsb") is not None:
                        # Mixxx pairs the two halves itself: two entries on the
                        # same group and key, one flagged msb and one lsb. No
                        # script, and the full resolution survives.
                        entry["options"] = ["fourteen-bit-msb"]
                        controls.append(entry)
                        controls.append(dict(entry,
                                             description=f"{label}{suffix} (LSB)",
                                             midino=inp["lsb"],
                                             options=["fourteen-bit-lsb"]))
                        seen_in.add(("cc", inp.get("channel", 1), inp["lsb"]))
                        continue
                    if _needs_script(c, inp, target):
                        fn = target.get("script") or f"{prefix}.{_ident(fn_id)}"
                        entry["key"] = fn
                        entry["options"] = ["script-binding"]
                        scripted.append((c, inp, fn, target))
                    controls.append(entry)
                    for m in (inp.get("mirrors") or []):
                        comments.append(
                            f"{label}{suffix}: also emits {m} -- mirror, "
                            f"intentionally unbound")

            if out and out.get("status") == "local":
                if ly == layers[0]:
                    comments.append(
                        f"{label}: LED is driven by the device firmware and cannot "
                        f"be addressed from the host, so no output is possible")
                out = None
            if out:
                oaddr = (out.get("channel", 1), out.get("number"))
                if oaddr in seen_out:
                    out = None
                else:
                    seen_out.add(oaddr)
            if out and not target.get("group"):
                comments.append(
                    f"{label}{suffix}: LED answers to note {out.get('number')} but "
                    f"no Mixxx control chosen yet, so no <output> was written")
            if out and target.get("group"):
                key = target.get("output_key") or target.get("key")
                if not key:
                    comments.append(
                        f"{label}: LED found on note {out.get('number')} but the "
                        f"target has no key to drive it")
                if key:
                    outputs.append({
                        "group": target["group"],
                        "key": key,
                        "description": f"{label} LED{suffix}",
                        "status": _status_for({"status": out.get("status", "note"),
                                               "channel": out.get("channel", 1)}),
                        "midino": out["number"],
                        "on": out.get("on", 0x7F),
                        "off": out.get("off", 0x00),
                        "minimum": target.get("output_minimum", 0.5),
                    })

    if description is None:
        description = _describe(p, layer, len(controls), len(outputs), comments)

    lines = ["<?xml version='1.0' encoding='utf-8'?>",
             '<MixxxControllerPreset schemaVersion="1" mixxxVersion="2.5.0+">',
             "    <info>",
             f"        <name>{escape(name)}</name>",
             f"        <author>{escape(author)}</author>",
             f"        <description>{escape(description)}</description>",
             "    </info>",
             f'    <controller id="{escape(controller_id)}">']
    # The script file is also needed when nothing is script-bound but the
    # controller has colour pads: the helper lives there and Mixxx will not load
    # it unless the mapping declares it.
    if scripted or _colour_helper(p, prefix, layer):
        lines += ["        <scriptfiles>",
                  f'            <file functionprefix="{escape(prefix)}" '
                  f'filename="{escape(script_file)}"/>',
                  "        </scriptfiles>"]
    lines.append("        <controls>")
    for e in controls:
        lines += ["            <control>",
                  f"                <group>{escape(e['group'])}</group>",
                  f"                <key>{escape(e['key'])}</key>",
                  f"                <description>{escape(e['description'])}</description>",
                  f"                <status>{_hex(e['status'])}</status>",
                  f"                <midino>{_hex(e['midino'])}</midino>",
                  "                <options>"
                  + "".join(f"<{o}/>" for o in e["options"])
                  + "</options>",
                  "            </control>"]
    lines.append("        </controls>")

    lines.append("        <outputs>")
    for e in outputs:
        lines += ["            <output>",
                  f"                <group>{escape(e['group'])}</group>",
                  f"                <key>{escape(e['key'])}</key>",
                  f"                <description>{escape(e['description'])}</description>",
                  f"                <status>{_hex(e['status'])}</status>",
                  f"                <midino>{_hex(e['midino'])}</midino>",
                  f"                <on>{_hex(e['on'])}</on>",
                  f"                <off>{_hex(e['off'])}</off>",
                  f"                <minimum>{e['minimum']}</minimum>",
                  "            </output>"]
    lines.append("        </outputs>")

    if comments:
        lines.append("        <!-- Not exported, recorded so the work is not repeated:")
        for cm in comments:
            lines.append(f"             - {_comment_safe(escape(cm))}")
        lines.append("        -->")

    lines += ["    </controller>", "</MixxxControllerPreset>", ""]
    xml = "\n".join(lines)

    # A mapping Mixxx cannot parse is worse than no mapping: it fails at load
    # time, in the GUI, away from here. Catch it while the cause is still known.
    try:
        ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        raise ValueError(f"generated mapping is not well-formed XML: {exc}") from exc
    return xml, scripted


def _describe(profile, layer, n_controls, n_outputs, comments):
    st = profile.stats()
    bits = [
        f"MIDI mapping for the {profile.data.get('name')}, generated by "
        f"mapping-studio from a measured control map.",
        f"Layer '{layer}': {n_controls} controls and {n_outputs} LED outputs "
        f"bound out of {st['controls']} known controls on the panel.",
    ]
    if comments:
        bits.append(f"{len(comments)} controls are captured but not yet assigned "
                    f"to a Mixxx control; see the comment block at the end of "
                    f"this file.")
    bits.append(f"Generated {time.strftime('%Y-%m-%d')}.")
    return " ".join(bits)


def build_script(profile, scripted, prefix, layer="base"):
    """Emit the JS scaffold for the bindings that need real behaviour."""
    out = [
        "// Generated by mapping-studio. Edit freely: regenerating will not",
        "// clobber this file, it is written alongside as .js.new if it exists.",
        "//",
        f"// Controller: {profile.data.get('name')}",
        f"// Layer:      {layer}",
        f"// Generated:  {time.strftime('%Y-%m-%d')}",
        "",
        f"var {prefix} = {{}};",
        "",
        f"{prefix}.init = function (id, debugging) {{",
        "};",
        "",
        f"{prefix}.shutdown = function () {{",
        "};",
        "",
    ]
    out.extend(_colour_helper(profile, prefix, layer))

    if not scripted:
        out.append("// No scripted bindings beyond the colour helper above.")
        out.append("")
        return "\n".join(out)

    for control, binding, fn, target in scripted:
        target = target or {}
        short = fn.split(".", 1)[-1]
        label = control.get("label", control["id"])
        group = target.get("group", "[Channel1]")
        key = target.get("key", "")
        out.append(f"// {label}")
        out.append(f"{prefix}.{short} = function (channel, control, value, "
                   f"status, group) {{")
        if binding.get("status") == "note":
            press = binding.get("press_value", 127)
            out.append(f"    if (value !== {press}) {{")
            out.append("        return;   // release edge; act on the press only")
            out.append("    }")
            if target.get("toggle"):
                # Set an explicit 0/1 rather than a JS boolean: engine values
                # are numeric and the explicit form is what Mixxx mappings use.
                out.append(f'    engine.setValue("{group}", "{key}",')
                out.append(f'        engine.getValue("{group}", "{key}") ? 0 : 1);')
            else:
                out.append(f'    engine.setValue("{group}", "{key}", 1);')
        elif binding.get("mode") == "relative":
            out.append("    var delta = (value < 64) ? value : value - 128;")
            out.append(f'    engine.setValue("{group}", "{key}", delta);')
        elif control.get("detent") and binding.get("resting") is not None:
            centre = binding["resting"]
            lo = binding.get("min", 0)
            hi = binding.get("max", 127)
            out.append(f"    // measured centre is {centre}, not 64; map it to 0.5")
            out.append(f"    var centre = {centre};")
            out.append(f"    var lo = {lo}, hi = {hi};")
            out.append("    var pos = (value <= centre)")
            out.append("        ? 0.5 * (value - lo) / Math.max(1, centre - lo)")
            out.append("        : 0.5 + 0.5 * (value - centre) / Math.max(1, hi - centre);")
            out.append(f'    engine.setParameter("{group}", "{key}", pos);')
        else:
            out.append(f'    engine.setValue("{group}", "{key}", value / 127);')
        out.append("};")
        out.append("")
    return "\n".join(out)


def _colour_helper(profile, prefix, layer):
    """Emit the RGB pad helper, if this controller has colour LEDs.

    Mixxx's <output> carries a single on-value, so it can turn an LED on and
    off and nothing else. Colour has to be script. What goes in the file is the
    *encoder*, not a captured table: the device packs its components into the
    velocity byte arithmetically, so every colour it can show is computable.
    """
    pads = [c for c in profile.controls
            if (c.get("bindings", {}).get(layer, {}) or {}).get("output")
            and (c["bindings"][layer]["output"].get("status") != "local")
            and c.get("kind") in ("pad", "button")
            and c.get("rgb") is not False
            and (c.get("colour") or c.get("kind") == "pad")]
    if not pads:
        return []

    led = colour_spec(profile)
    sh = led.get("shift") or {"r": 4, "g": 2, "b": 0}
    levels = int(led.get("levels", 4))
    bit = led.get("bright_bit")
    lines = [
        "// ---------------------------------------------------------------",
        "// RGB pad LEDs.",
        f"// {colour.describe(led)}",
        "// Recovered by lighting pads and reading the colours off the panel,",
        "// so this is measured behaviour, not a guess from a datasheet.",
        "",
        f"{prefix}.LEVELS = {levels};   // values per channel, 0..{levels - 1}",
        "",
        "// Components are 0..%d. Returns the velocity byte to send." % (levels - 1),
        f"{prefix}.colourValue = function (r, g, b, bright) {{",
        f"    var v = (r << {int(sh['r'])}) | (g << {int(sh['g'])}) "
        f"| (b << {int(sh['b'])});",
    ]
    if bit is not None:
        lines += [f"    if (bright !== false) {{",
                  f"        v |= 1 << {int(bit)};",
                  "    }"]
    lines += [
        "    return v & 0x7F;",
        "};",
        "",
        "// Light one pad. channel is 1-based, as printed in the mapping.",
        f"{prefix}.setPadColour = function (channel, note, r, g, b, bright) {{",
        "    midi.sendShortMsg(0x90 + (channel - 1), note,",
        f"                      {prefix}.colourValue(r, g, b, bright));",
        "};",
        "",
        "// Named colours, as component triples at this device's depth.",
        f"{prefix}.COLOUR = {{",
    ]
    span = levels - 1
    for name, (r, g, b) in colour.NAMED.items():
        trip = [int(round(v * span)) for v in (r, g, b)]
        lines.append(f"    {name.upper()}: [{trip[0]}, {trip[1]}, {trip[2]}],")
    lines += ["};", ""]

    named_pads = [c for c in pads if c.get("colour")]
    if named_pads:
        lines.append("// Colours chosen for specific controls in the studio.")
        lines.append(f"{prefix}.PAD_DEFAULT = {{")
        for c in named_pads:
            col = c["colour"]
            out = c["bindings"][layer]["output"]
            trip = [colour.quantise(col.get(k, 0), levels) for k in ("r", "g", "b")]
            lines.append(
                f"    {_ident(c['id'])}: {{ channel: {out.get('channel', 1)}, "
                f"note: {out['number']}, rgb: [{trip[0]}, {trip[1]}, {trip[2]}], "
                f"bright: {str(bool(col.get('bright', True))).lower()} }},")
        lines += ["};", ""]
    return lines


def colour_spec(profile):
    return colour.spec_from(profile.data.get("led") or {})


def export(profile, layer="base", **kw):
    """Return (xml_text, script_text, script_filename)."""
    name = kw.get("name") or profile.data.get("name") or profile.data.get("id")
    prefix = kw.get("prefix") or _ident(name)
    script_file = kw.get("script_file") or f"{name.replace(' ', '-')}-scripts.js"
    xml, scripted = build_xml(profile, layer=layer, script_file=script_file,
                              prefix=prefix, **{k: v for k, v in kw.items()
                                                if k in ("name", "author",
                                                         "description",
                                                         "controller_id")})
    js = build_script(profile, scripted, prefix, layer=layer)
    return xml, js, script_file
