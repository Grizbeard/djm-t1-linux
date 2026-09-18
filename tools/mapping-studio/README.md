# Mapping Studio

Map a MIDI controller by clicking its picture.

Point at a control on screen, move the real one, and the binding is captured.
Then let the studio light the LEDs one at a time and click whichever one lit.
What comes out is a Mixxx `.midi.xml` mapping and its script file.

It runs as a local web app with no dependencies outside the Python standard
library, so it works over SSH on the Pi that the mixer is plugged into.

```sh
tools/mapping-studio/mapping-studio serve \
    tools/mapping-studio/profiles/pioneer-djm-t1.json \
    --midi-port "Pioneer DJM-T1" --open
```

## Contents

- [Why](#why)
- [The four modes](#the-four-modes)
- [Quick start](#quick-start)
- [Adding a controller](#adding-a-controller)
- [What the first pass can and cannot see](#what-the-first-pass-can-and-cannot-see)
- [Profiles, and what is worth keeping](#profiles-and-what-is-worth-keeping)
- [Artwork and licensing](#artwork-and-licensing)
- [Command reference](#command-reference)
- [Status](#status)

## Why

Mapping an unsupported controller means correlating two things that are hard to
hold in your head at once: a physical panel under your hands, and a stream of
numbers. The usual tools give you one or the other. `tools/calibrate.py` in this
repository does the input half well as a terminal list, and it is what produced
[docs/midi-map.md](../../docs/midi-map.md) — but you still read a control's name
off a list rather than pointing at it.

Output mapping is worse. [tools/probe-leds.sh](../probe-leds.sh) sends all 128
notes in order, about 1.4 seconds apart, while you watch the panel and try to
remember which of forty LEDs lit on which note. That is three minutes of
staring and a transcription problem at the end. It is why most community
mappings have no LED feedback at all.

Both halves get much easier with a picture in the loop. Pointing at a control is
faster and less error-prone than finding it in a list, and "click the thing that
just lit" is a question anyone can answer instantly.

## The four modes

**Layout** — correct the auto-detected regions. Drag to move, corner dot to
resize, `N` to add, `Del` to remove. Regions the detector guessed are drawn
dashed until you touch them.

**Learn** — click a region, move the control, click Done. The capture is
analysed rather than just recorded, which is where the useful part is:

- A relative encoder is told apart from a knob, because it emits many messages
  but only two or three distinct values. It exports as `<selectknob/>`.
- The resting value is kept, so a detented control whose centre is not MIDI 64
  can have its real centre written into the generated script.
- **Anything else that fired at the same time is flagged as a mirror.** The
  DJM-T1's crossfader emits CC `0x17` and CC `0x18` together; binding the mirror
  is what made the crossfader drag Mixxx's headphone mix, a bug recorded in
  `docs/midi-map.md`. The studio now surfaces it instead of letting you bind it.
- A control that emits nothing is recorded as **silent**, which is a finding.
  The DJM-T1's master, booth and headphone knobs are analogue; writing that down
  is what stops the next person re-testing them.

**LEDs** — the studio lights one note and asks which region lit. Notes already
captured as button inputs are tried first, because on most gear a button's LED
answers to the button's own note. Where that convention holds, the output map
falls out in the first few dozen sends rather than after all 128.

**Assign** — choose what each captured control drives in Mixxx. Deliberately
separate from the capture: changing your mind about what a button does must
never cost you the measurement of what it emits.

## Quick start

```sh
# what MIDI ports exist
tools/mapping-studio/mapping-studio ports

# open the DJM-T1 profile against the running djm_midi bridge
tools/mapping-studio/mapping-studio serve \
    tools/mapping-studio/profiles/pioneer-djm-t1.json \
    --midi-port "Pioneer DJM-T1" --open

# no hardware to hand? everything but capture still works
tools/mapping-studio/mapping-studio serve \
    tools/mapping-studio/profiles/pioneer-djm-t1.json --backend offline
```

Then browse to <http://127.0.0.1:8733/>. Export writes `<Name>.midi.xml` and
`<Name>-scripts.js`; an existing script is never overwritten, it is written
alongside as `.js.new`.

For the DJM-T1 specifically, the bridge has to be running or the mixer transmits
nothing — see the [top-level README](../../README.md).

## Adding a controller

If you have a vector panel drawing (a manual's plan view is usually vector, not
a photo):

```sh
tools/mapping-studio/mapping-studio detect panel.svg \
    --name "Reloop Ready" -o profiles/reloop-ready.json
tools/mapping-studio/mapping-studio serve profiles/reloop-ready.json
```

If all you have is a photo, start an empty profile, pass `--backdrop photo.jpg`
and place regions by hand with `N`. The backdrop is only ever read from your
local disk; it is not part of the profile.

Labels are picked up from `<text>` in the SVG. When the artwork has its text
outlined into paths — normal for PDF-derived drawings — extract the text
separately and pass `--labels labels.json`, a list of `{"text","x","y"}` in the
drawing's own units.

## What the first pass can and cannot see

On the DJM-T1's plan view the detector reduces **3,656 subpaths to 82 candidate
regions** and names **70** of them from the panel's own labels — TRIM, HI, CUE,
SYNC, DRY/WET — rather than `button_37`. It gets there on three signals:

- **Both dimensions large enough to press.** This alone removes 1,671
  glyph-sized shapes and every hairline rule.
- **Concentric clustering.** Art draws a knob as a cap plus a skirt, so shapes
  sharing a centre are merged, and how many merged is itself evidence.
- **Modal sizing.** Panels reuse a few part sizes. On this panel the four button
  aperture classes recur 13, 11, 8 and 4 times; a one-off shape is probably
  decoration.

**It does not find faders.** A fader is drawn as a ladder of scale ticks plus a
cap, so there is no single shape to detect. The three on the DJM-T1 are placed
by hand in the shipped profile and marked provisional. Expect to draw fader
regions yourself on any new controller.

Everything it emits is provisional, carries a confidence and lists its evidence.
A wrong region that looks confident costs more than a missing one.

## Profiles, and what is worth keeping

A profile is one JSON file holding three separable things:

| Part | What it is | Lifetime |
|---|---|---|
| Geometry | where each control sits, in millimetres | permanent — it is a measurement of hardware |
| Bindings | what each control emits, per layer | until the hardware changes |
| Targets | what it should drive in Mixxx | a decision, revisable at any time |

Keeping them apart is the point. Re-deciding what a button does, or exporting
for a different host, must never cost you the measurements.

Layers are first class, because SHIFT is not a modifier the mapping can infer:
holding it makes the DJM-T1's pads emit different codes entirely. Capture the
`base` layer, then switch to `shift` and capture again.

The shipped `profiles/pioneer-djm-t1.json` has geometry for 86 regions — the 82
detected, plus the three faders and the browse encoder's push, placed by hand —
and 18 bindings seeded from `docs/midi-map.md`. **Every seeded binding is tagged
`"verified": false`**, because it came from a document rather than from this
tool watching the hardware. Re-learn them to clear the flag.

As a check on the exporter, that profile generates a mapping that agrees with
the hand-written `mixxx/Pioneer-DJM-T1.midi.xml` on **17 of 19 bindings, with no
binding the hand-written file does not also have**. The remainder is the deck
transport, deliberately not seeded.

## Artwork and licensing

**A profile stores measured geometry, never traced vendor artwork**, and the
panel you see is drawn from that geometry rather than from an image.

This follows the same rule as [docs/INTERFACE-SPEC.md](../../docs/INTERFACE-SPEC.md):
positions and sizes are facts about hardware, and facts are not protected
expression. A manual's line art is. So a profile is safe to publish under this
repository's MIT licence, while a scan or a photo is not, and the studio never
asks you to commit one. Point `--backdrop` at your own copy if you want it
behind the regions while you work.

It is also the better design. Because the panel is generated, every control is a
real element with an id, there is no hit-region reverse engineering, and the
drawing restyles with the rest of the UI.

## Command reference

| Command | What |
|---|---|
| `serve PROFILE` | run the web app |
| `detect SVG -o PROFILE` | first-pass region detection from panel art |
| `ports` | list MIDI ports the host can see |
| `info PROFILE` | coverage summary, and any address claimed twice |
| `export PROFILE -d DIR` | write the Mixxx mapping without the UI |

Useful `serve` flags: `--backend {auto,alsa,rtmidi,offline}`, `--midi-port`
(ALSA `client:port` or a name fragment), `--backdrop IMAGE`, `--layer`,
`--host`/`--port`, `--open`.

MIDI backends: **alsa** drives `aseqdump` and `aplaymidi` and needs no Python
packages; **rtmidi** works anywhere `python-rtmidi` is installed, including
Windows and macOS; **offline** has no hardware, and the whole UI, the profile
editing and the exporters work against it.

Tests: `python3 -m unittest discover tools/mapping-studio` (34 cases, stdlib
only).

## Status

| Piece | State |
|---|---|
| Region auto-detection from vector art | ✅ working; faders need a human |
| Layout editing | ✅ |
| Input learn, with mirror and relative detection | ✅ logic tested; **not yet run against hardware** |
| LED probe loop | ✅ logic tested; **not yet run against hardware** |
| Mixxx XML + script export | ✅ validated against the hand-written mapping |
| SHIFT layer capture | ✅ supported; nobody has done the pass yet |
| Reloop Ready profile | ⬜ artwork not yet sourced |

The hardware-facing halves have been exercised end to end against the offline
backend only. The ALSA reader is the mechanism `tools/calibrate.py` already
proves out on this mixer, and the sender is the one `tools/probe-leds.sh` uses,
but neither has been run against a DJM-T1 from this tool yet. Expect the first
session on real hardware to find something.
