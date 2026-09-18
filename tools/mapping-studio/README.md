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

**LEDs** — the studio lights one note and asks which region lit.

Probing sweeps **channels, plural**. A controller can split its surface across
several: the Reloop Ready puts deck transport on channels 1 and 2, the eight
pads per deck on 5 and 6, and more on 9, 10 and 15. Its LEDs live on those same
channels, so a single-channel sweep silently finds almost nothing. `channels`
defaults to `seen` — whatever channels the surface has actually transmitted on
this session.

Three strategies, and the default is not a sweep:

| Strategy | Sends | When |
|---|---|---|
| `observed` (default) | only (channel, note) pairs the controller has emitted | a button's LED answers to its own note on nearly all gear, so the traffic already says where to look |
| `smart` | full sweep, known button notes first | when `observed` missed LEDs that no button drives |
| `linear` | full sweep, in order | last resort |

On the Reloop Ready that is **41 sends instead of 896**. Press the buttons
first: `observed` is built from what it heard.

Clicking the wrong region is the mistake this loop invites, so **Undo last**
restores the previous binding and re-lights that note. The panel also shows
`last: note N chC -> PAD A2` as you go, and a note claimed by two controls is
reported by `info` as an output collision, which is nearly always a mis-click.

Not every LED can be driven. The Reloop Ready's MODE buttons are lit
permanently by the device and merely brighten on press. Mark those **LED is
firmware-driven**: it is the output-side twin of `silent`, it exports as a
comment rather than an `<output>`, and it stops the next person sweeping 128
notes looking for something that was never addressable.

### Colour pads

A probe that only ever sends velocity 127 can discover *which* note lights a
pad, never what colour it shows. Controllers with RGB pads usually pack the
components into the velocity byte; there is no standard for it, but the shape
recurs.

The Reloop Ready's was recovered the same way everything else here works --
light something, ask a human what they see:

    velocity = bright<<6 | R<<4 | G<<2 | B          R, G, B each 0..3

Two bits per channel, 64 colours, one brightness bit that leaves hue alone. It
was confirmed by *prediction*: eight pure colours computed from the model, sent
without ever having been tried, all correct.

What a profile stores is the **encoding, not a palette**. A table describes one
controller; an encoding describes a family, and a device with a different depth
or component order is the same code with different numbers. An encoding too
wide for a velocity is refused rather than silently truncated.

Pick a colour in the Layout pane and it appears on the pad immediately, which is
the only way to be sure the encoding is right for a given device. Export emits a
`colourValue` / `setPadColour` helper plus named constants, because Mixxx's
`<output>` carries a single on-value and cannot express colour at all -- the
mapping declares the script file even when nothing else is script-bound.

Not every LED is addressable, and not every addressable one is RGB. The Reloop's
MODE, CUE and PLAY are fixed-colour (blue, red, green); marking them `rgb: false`
records that so nobody tries to colour them later.

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

Diagrams that number their controls get a fourth signal. A manual's callout is
a number in a small box with a leader to the control, and those boxes are
exactly the size and shape of buttons — so naive matching names *the box*, which
is worse than no name. Boxes are recognised and removed when a label says it is
a callout (`"callout": true` or `"number": N` in the sidecar) and nearly every
box of that size holds one. On the Reloop Ready that removes **37** of them and
the names then land on real controls.

The detector will not infer this from the text being numeric. That was tried:
panels legitimately label controls 1, 2, 3, and guessing deleted 46 real
controls from the DJM-T1 pass. Declaring it is cheap; guessing is not.

**It does not find faders or jog wheels.** A fader is drawn as a ladder of
scale ticks plus a cap, and a jog wheel is a ring enclosing its own tick marks,
so neither is a single findable shape. The three faders on the DJM-T1 are placed
by hand in the shipped profile and marked provisional. Expect to draw these
yourself on any new controller — it is a few seconds each.

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
| Input learn, with mirror and relative detection | ✅ run against a Reloop Ready |
| LED probe loop | ✅ run against a Reloop Ready: 40 LEDs in one pass |
| Mixxx XML + script export | ✅ validated against the hand-written mapping |
| SHIFT layer capture | ✅ supported; nobody has done the pass yet |
| Reloop Ready profile | 🟡 72 regions, 40 LEDs mapped, inputs barely started |

`profiles/reloop-ready.json` is geometry derived from the plan view in the
Reloop Ready instruction manual (article 243598), named through the manual's own
callout legend. Scaling it by the published 325 mm width reproduces the
published 220 mm depth to 0.9%, which is the check that says the drawing is a
true projection rather than a stylised one. Jog wheels and faders still need
placing by hand; the 16 pads were placed by hand because the plan view does not
draw them as findable shapes.

Its LED map came out of one probe pass and is regular enough to trust: pads A1-A8
answer to notes 20-27 on channel 5, pads B1-B8 to the same notes on channel 6,
and PLAY/CUE/SYNC to notes 0/1/2 on channels 1 and 2. Inputs are almost entirely
unmapped -- only the left GAIN knob (CC 0x16) has been learned.

The hardware that taught this tool about channels: the Reloop Ready spreads its
surface over channels 1, 2, 5, 6, 9, 10 and 15.

Both hardware-facing halves have now been run against a real controller: a
Reloop Ready over the rtmidi backend on Windows, where the learn loop captured
a full knob sweep and one LED pass identified 40 outputs. The DJM-T1 side is
still offline-only -- the ALSA reader is the mechanism `tools/calibrate.py`
already proves on that mixer, and the sender is `tools/probe-leds.sh`'s, but
neither has been driven from this tool against a DJM-T1 yet.
