"""Write a human-readable mapping reference from a profile.

The XML says what a button sends; this says what it does, which is the thing
anyone actually standing at the mixer wants. Generated rather than written so
it cannot drift from the mapping it describes.

Usage: python tools/mapping_doc.py profiles/x.json > docs/mapping.md

SPDX-License-Identifier: MIT
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mapping_studio.profile import Profile  # noqa: E402

LAYER_TITLE = {
    "base": "",
    "shift": "SHIFT +",
    "sampler": "SAMPLER mode",
    "sampler_shift": "SAMPLER mode, SHIFT +",
}


def describe(target):
    if not target:
        return ""
    key = target.get("key", "")
    if key.startswith("DJMT1.") or "." in key:
        return f"`{key.split('.', 1)[-1]}` (script)"
    if target.get("relative_action") == "beatjump":
        size = target.get("size_key", "beatjump_size")
        return f"`{target['group']}` `{key}` by `{size}`"
    if target.get("cycle"):
        steps = ", ".join(f"{v:g}" for v in target["cycle"])
        return f"`{target['group']}` `{key}` through {steps}"
    return f"`{target['group']}` `{key}`"


def main(path):
    p = Profile.load(path)
    out = [f"# {p.data.get('name')} - Mixxx mapping", ""]
    prov = (p.data.get("provenance") or {}).get("midi_map")
    if prov:
        out += ["> " + prov, ""]

    sections = {}
    for c in p.controls:
        sections.setdefault(c.get("section") or "Other", []).append(c)

    out += ["## What each control does", ""]
    for sec in sorted(sections):
        rows = []
        for c in sorted(sections[sec], key=lambda c: c["id"]):
            for layer in p.layers:
                target = p.target(c, layer)
                if not target:
                    continue
                inp = p.binding(c["id"], layer, "input") or {}
                if inp.get("status") == "switch":
                    addr = "3-pos"
                elif inp.get("status") in ("cc", "note"):
                    addr = f"{inp['status'].upper()} {inp['number']}"
                else:
                    addr = "-"
                prefix = LAYER_TITLE.get(layer, layer)
                name = f"{prefix} {c.get('label', c['id'])}".strip()
                rows.append((name, addr, describe(target)))
        if not rows:
            continue
        out += [f"### {sec}", "",
                "| Control | MIDI | Mixxx |", "|---|---|---|"]
        out += [f"| {a} | `{b}` | {c} |" for a, b, c in rows]
        out.append("")

    dev = p.data.get("deviations") or []
    if dev:
        out += ["## Where this departs from the TRAKTOR mapping", "",
                "The panel was designed around TRAKTOR, and a few of its",
                "functions have no Mixxx counterpart. Each one below is a",
                "deliberate substitution, not an oversight.", ""]
        out += [f"- {d}" for d in dev]
        out.append("")

    startup = p.data.get("startup") or []
    if startup:
        out += ["## Set at every start", "",
                "State the mapping depends on, asserted each time it loads. If a",
                "required value does not take, nothing below it is applied.", "",
                "| Mixxx | Value | |", "|---|---|---|"]
        out += [f"| `{e['group']}` `{e['key']}` | {e['value']} | "
                f"{'required' if e.get('require') else ''} |" for e in startup]
        out.append("")

    unmapped = []
    for c in p.controls:
        for layer in p.layers:
            inp = p.binding(c["id"], layer, "input")
            if not inp or inp.get("status") in ("silent", "local", "switch"):
                continue
            if p.target(c, layer):
                continue
            unmapped.append(
                f"- {LAYER_TITLE.get(layer, layer)} "
                f"{c.get('label', c['id'])} "
                f"(`{inp['status'].upper()} {inp['number']}`)".replace("  ", " "))
    if unmapped:
        out += ["## Sends MIDI, deliberately unmapped", "",
                "Mostly addresses the hardware emits for a TRAKTOR function",
                "that does not exist here, or that the manual lists as having",
                "no function at all. They are left free on purpose.", ""]
        out += sorted(set(unmapped))
        out.append("")

    silent = sorted(c.get("label", c["id"]) for c in p.controls
                    if (p.binding(c["id"], "base", "input") or {})
                    .get("status") == "silent")
    if silent:
        out += ["## Analog, sends nothing", "",
                "Verified silent during calibration, so correctly absent:", "",
                ", ".join(silent) + ".", ""]
    return "\n".join(out)


if __name__ == "__main__":
    # Written, not piped: a redirect on Windows encodes with the console
    # codepage and silently mangles anything outside it.
    text = main(sys.argv[1])
    if len(sys.argv) > 2:
        with open(sys.argv[2], "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)
