"""Command line entry point.

    mapping-studio detect panel.svg -o profiles/thing.json --name "Thing"
    mapping-studio serve profiles/thing.json --midi-port "Pioneer DJM-T1"
    mapping-studio ports
    mapping-studio export profiles/thing.json -d mixxx/
    mapping-studio info profiles/thing.json

SPDX-License-Identifier: MIT
"""

import argparse
import json
import os
import sys
import webbrowser

from . import autodetect, export_mixxx, midi, server
from .profile import Profile


def cmd_detect(args):
    labels = autodetect.load_labels(args.labels) if args.labels else None
    cfg = {}
    if args.min_dim is not None:
        cfg["min_dim"] = args.min_dim
    panel, controls = autodetect.detect(args.svg, labels=labels, config=cfg)

    if args.min_confidence:
        controls = [c for c in controls if c["confidence"] >= args.min_confidence]
    if not args.indicators:
        controls = [c for c in controls if c.get("tier") != "indicator"]

    name = args.name or os.path.splitext(os.path.basename(args.svg))[0]
    ident = args.id or name.lower().replace(" ", "-")
    prof = Profile.new(ident, name, panel)
    for c in controls:
        prof.add_control(c)

    print(autodetect.summarise(controls))
    if args.out:
        prof.save(args.out)
        print(f"\nwrote {args.out}")
        print("Every region is provisional. Open it with `serve` and correct the "
              "pass before mapping:")
        print(f"  mapping-studio serve {args.out}")
    else:
        json.dump(prof.data, sys.stdout, indent=1)
    return 0


def cmd_ports(args):
    ports = midi.list_ports()
    if not ports:
        print("No MIDI ports found.")
        if not midi.AlsaBackend.available():
            print("  aseqdump is not installed (package: alsa-utils)")
        if not midi.RtMidiBackend.available():
            print("  python-rtmidi is not installed (optional, for non-Linux hosts)")
        print("\nYou can still run the studio with --backend offline to lay out")
        print("and review a profile without hardware.")
        return 1
    width = max(len(p["port"]) for p in ports)
    for p in ports:
        print(f"  [{p['backend']:6s}] {p['port']:<{width}}  {p['name']}")
    return 0


def cmd_info(args):
    prof = Profile.load(args.profile)
    st = prof.stats()
    print(f"{prof.data.get('name')}  ({prof.data.get('id')})")
    print(f"  panel      {prof.panel['w']} x {prof.panel['h']} "
          f"{prof.data.get('units', 'mm')}")
    print(f"  controls   {st['controls']}  ({st['provisional']} still provisional)")
    for layer, n in st["mapped_inputs"].items():
        print(f"  layer {layer:<8s} {n} inputs bound")
    print(f"  outputs    {st['mapped_outputs']} LEDs bound")
    print(f"  targets    {st['targeted']} assigned to Mixxx controls")
    if st["collisions"]:
        print(f"  COLLISIONS {st['collisions']}")
        for (layer, status, ch, num), ids in prof.collisions().items():
            print(f"    {layer} {status} ch{ch} {num}: {', '.join(ids)}")
    return 0


def cmd_export(args):
    prof = Profile.load(args.profile)
    xml, js, fname = export_mixxx.export(prof, layer=args.layer,
                                         author=args.author or "")
    if not args.dir:
        sys.stdout.write(xml)
        return 0
    os.makedirs(args.dir, exist_ok=True)
    base = (prof.data.get("name") or "mapping").replace(" ", "-")
    xml_path = os.path.join(args.dir, f"{base}.midi.xml")
    with open(xml_path, "w", encoding="utf-8") as fh:
        fh.write(xml)
    print(f"wrote {xml_path}")
    js_path = os.path.join(args.dir, fname)
    if os.path.exists(js_path):
        js_path += ".new"
        print(f"  (script exists; writing {js_path} rather than overwriting)")
    with open(js_path, "w", encoding="utf-8") as fh:
        fh.write(js)
    print(f"wrote {js_path}")
    return 0


def cmd_serve(args):
    port_hint = args.midi_port
    backend = args.backend
    if backend == "auto" and port_hint is None:
        # Nothing to connect to is not an error; it is the common case when
        # laying out a panel away from the rig.
        found = midi.list_ports()
        if found:
            port_hint = found[0]["port"]
            print(f"MIDI: using {found[0]['name']} ({found[0]['port']})")
        else:
            print("MIDI: no ports found, running offline "
                  "(layout and export still work)")
            backend = "offline"

    studio = server.load_studio(
        args.profile, backend_spec=backend, port_hint=port_hint,
        rawmidi=args.rawmidi, sender=args.sender, backdrop=args.backdrop,
        layer=args.layer)

    httpd = server.serve(studio, host=args.host, port=args.port)
    url = f"http://{args.host}:{args.port}/"
    print(f"\n  {studio.profile.data.get('name')}: "
          f"{len(studio.profile.controls)} controls")
    print(f"  MIDI backend: {studio.session.backend.name} "
          f"({studio.session.backend.status})")
    print(f"\n  Mapping Studio on {url}")
    print("  Ctrl+C to stop\n")
    if args.open:
        try:
            webbrowser.open(url)
        except Exception:                             # noqa: BLE001
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping...")
    finally:
        studio.session.backend.stop()
        if studio.dirty:
            path = studio.save()
            print(f"saved unsaved changes to {path}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="mapping-studio",
        description="Map a MIDI controller by clicking its picture.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("detect", help="first-pass region detection from panel art")
    d.add_argument("svg")
    d.add_argument("-o", "--out", help="profile JSON to write")
    d.add_argument("--labels", help="JSON sidecar of {text,x,y} panel labels")
    d.add_argument("--name", help="human name for the controller")
    d.add_argument("--id", help="profile id (default: slug of name)")
    d.add_argument("--min-dim", type=float,
                   help="smallest side of a real control, in drawing units")
    d.add_argument("--min-confidence", type=float, default=0.0)
    d.add_argument("--indicators", action="store_true",
                   help="also keep LED/meter segments")
    d.set_defaults(func=cmd_detect)

    s = sub.add_parser("serve", help="run the studio web app")
    s.add_argument("profile")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8733)
    s.add_argument("--backend", default="auto",
                   choices=["auto", "alsa", "rtmidi", "offline"])
    s.add_argument("--midi-port", help="ALSA port ('128:0') or a name fragment")
    s.add_argument("--rawmidi", help="hw:X,0,0 for the amidi sender")
    s.add_argument("--sender", default="aplaymidi", choices=["aplaymidi", "amidi"])
    s.add_argument("--backdrop", help="local image to show behind the regions")
    s.add_argument("--layer", default="base")
    s.add_argument("--open", action="store_true", help="open a browser")
    s.set_defaults(func=cmd_serve)

    p = sub.add_parser("ports", help="list MIDI ports")
    p.set_defaults(func=cmd_ports)

    i = sub.add_parser("info", help="summarise a profile")
    i.add_argument("profile")
    i.set_defaults(func=cmd_info)

    e = sub.add_parser("export", help="write a Mixxx mapping")
    e.add_argument("profile")
    e.add_argument("-d", "--dir", help="output directory (default: stdout)")
    e.add_argument("--layer", default="base")
    e.add_argument("--author", default="")
    e.set_defaults(func=cmd_export)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
