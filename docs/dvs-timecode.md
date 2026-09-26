# Digital vinyl (DVS / timecode) on the DJM-T1 with Mixxx

The "T" in DJM-T1 is Traktor: the mixer was built as the front end of a Traktor
Scratch digital-vinyl setup. Its built-in soundcard digitizes the phono/line
inputs, so control vinyl (or control CD) can drive a software deck. Now that the
soundcard works on Linux ([`../audio/`](../audio/)), that same path can drive
**Mixxx's vinyl control**. This documents the wiring and what still needs a bench
check.

## How DVS works here

```
 control record  ->  turntable  ->  DJM-T1 phono in  ->  built-in ADC  ->  USB in
                                                                             |
                                       Mixxx vinyl control (xwax decoder)  <-+
                                       decodes timecode -> deck position/speed
```

The timecode (a tone + noise pattern pressed onto control vinyl) reaches Mixxx as
ordinary audio on the mixer's USB input channels. Mixxx's built-in vinyl-control
decoder turns it into scratch/position/pitch for the assigned deck. No extra
hardware beyond the control records the setup already uses with Traktor.

The input selector position does **not** gate this. The manual is explicit that
DVS runs with the selector on `USB` (Operating Instructions p.12, step 1); the
phono/CD jacks are digitized and sent to the computer regardless of where the
selector sits. That is the whole trick of a Traktor Scratch certified mixer: the
channel plays the software's audio while the same channel's analog input is
being digitized for timecode.

## The channel map

This was an open bench question here. The manual answers it outright (p.26,
*Setting the source of audio data output from this unit to the computer*), and
the pairs are fixed except for USB 5/6:

| USB pair | To the computer | From the computer |
|---|---|---|
| 1/2 | CH1 timecode, PHONO or CD | CH1 audio (selector on `USB`) |
| 3/4 | CH2 timecode, PHONO or CD | CH2 audio (selector on `USB`) |
| 5/6 | selectable: post CH1 fader, post CH2 fader, crossfader A or B, MIC/AUX post EQ, REC OUT | master return |

Whether 1/2 and 3/4 carry the **PHONO** or the **CD** input is set in the
DJM-T1 Setting Utility, `MIXER OUTPUT` tab. Turntables need *CH1/CH2 Timecode
PHONO*; CDJs need *Timecode CD*.

The capture work ([../audio/README.md](../audio/README.md)) found input channels
0/1 and 4/5 carrying signal with 2/3 near-silent, which fits: 0/1 is CH1's
timecode, 2/3 was CH2 with nothing connected, and 4/5 is the USB 5/6 return
carrying whatever that tab was set to. What looked like the USB output "looping
back" onto input 4/5 was most likely REC OUT returning the master mix, not a
loopback.

## Sound Hardware: use hardware mixing

The DJM-T1 is a real mixer, so Mixxx should not mix. Each deck goes out its own
USB pair, into that channel's strip, and the analog EQ, faders and crossfader do
the work.

```
Mixxx deck 1 --USB out 1/2--> CH1 --+  analog EQ / fader / crossfader
Mixxx deck 2 --USB out 3/4--> CH2 --+--> MASTER
```

In Mixxx, Preferences, Sound Hardware:

| | Setting |
|---|---|
| Deck 1 output | DJM-T1 channels 1/2 |
| Deck 2 output | DJM-T1 channels 3/4 |
| Vinyl Control In 1 | DJM-T1 channels 1/2 |
| Vinyl Control In 2 | DJM-T1 channels 3/4 |
| **Main output** | **unassigned** |

**Main must stay unassigned.** USB 5/6 is the master return, so pointing Mixxx's
main output at it sums the complete internal mix into the master *on top of* the
two channel strips already carrying the same audio by the analog path. It is
audibly louder and the two copies have different gain staging, because one
carries Mixxx's faders and crossfader and the other the analog ones. For the
same reason, do not assign an Auxiliary input to 5/6 while main is going out on
it -- that is a feedback loop.

### Turn the mixer-section MIDI off

The `CH1` / `CH2` buttons in the MIDI section decide whether the mixer strip
sends MIDI. For hardware mixing they should be **off**.

Mixxx's deck outputs are not tapped before its own fader. `getChannelBuffer`
returns the channel's buffer after `ChannelMixer::applyEffectsInPlaceAndMixChannels`
has worked on it in place -- EQ and pregain, then Mixxx's volume fader and
crossfader gain, then the effect units routed to that deck -- so everything
Mixxx does to a deck is in its USB output. With mixer-section MIDI on, the stock
mapping would drive Mixxx's EQ *and* the analog EQ -- every tone shift applied
twice -- and Mixxx's channel faders and crossfader *and* the analog ones, so a
fader pulled halfway would attenuate twice.

(An earlier version of this page said the volume and crossfader gains were
applied only when summing to main. The engine source says otherwise.)

The DJM-T1_Custom mapping leaves the faders, TRIM, the EQ and the crossfader
unmapped, so with it nothing is applied twice even if the mixer-section MIDI is
on.

The performance controls are not in that section and keep working either way.
Those buttons are really the switch between two whole configurations:

| | Deck outs | Main out | Mixer MIDI | Selectors |
|---|---|---|---|---|
| **Hardware mixing** (this document) | 1/2, 3/4 | unassigned | off | USB |
| **Software mixing** (DJM as a control surface) | unassigned | 5/6 | on | USB |

Software mixing costs the headphone cue, because the mixer's PHONES jack
monitors the analog CUE buses and Mixxx's headphone bus has nowhere to go. It
can be bought back by giving Mixxx's Headphones output its own channel -- main
to CH1, headphones to CH2 with the fader down and CUE pressed -- at the cost of
a channel and of the mixer no longer mixing anything.

## Vinyl control settings

Mixxx, Preferences, Vinyl Control:

- Pick the **timecode type** matching your control records. Mixxx supports
  Serato CV02, **Traktor MK1/MK2** and MixVibes. A mixer that shipped with
  Traktor Scratch often means Traktor control vinyl, which Mixxx decodes
  directly -- worth checking, since the default is Serato CV02.
- Set lead-in, and choose absolute (position) or relative (scratch-only) mode.
  The panel selects these live: SHIFT + PLAY is relative, SHIFT + CUE is
  absolute, both writing `vinylcontrol_mode`. See
  [mixxx-mapping.md](mixxx-mapping.md).
- Enable vinyl control on a deck and drop the needle.

On Linux, run the audio service first so the mixer is a PipeWire device
(`djmt1-pipewire`).

## Post-fader FX

Hardware mixing cannot do post-fader effects on stock Mixxx. An effect unit
routed to a deck is an insert in that deck's USB output, so the channel fader
comes after it and cuts an echo's tail along with the dry signal.

**The stock workaround does not work.** The idea was a unit on Mixxx's main bus
at Dry/Wet 1.0, with main going out on USB 5/6, which skips the channel faders.
But at Dry/Wet 1.0 Echo and Reverb still pass the dry signal: both output only
their tail and set `addDryToWet`, and `EngineEffectChain::process` adds their
input back before the crossfade. Dry+Wet always adds it, and a unit that is off
or empty passes its input straight through. Any of these puts the whole mix on
the master a second time.

A patched Mixxx that does it -- wet-only effect units as returns on the
crossfader buses, sent to the master on USB 5/6 past the channel faders, with
the faders driving the sends -- was built and tried, and is kept on the
`post-fader-fx` branch of this repository and of the Terminal-wide repository.
The working configuration is the stock one above: effects are pre-fader
inserts on the decks.

Verified on the bench (2026-09-25): USB out 5/6 bypasses the channel strips.
With both channel faders fully down, test tones on out 5 and 6 played on master
left and right, and the master meter moved while the channel meters stayed
still. So anything Mixxx sends to 5/6, an echo tail included, is untouched by
the channel faders.

## Still to check on the bench

- **Signal level / phono stage:** confirm the inputs deliver a clean, correctly
  leveled timecode signal (the mixer's phono preamp is already in the path;
  verify the decoder locks and shows a steady quality reading).
- **Timecode type:** confirm which format your control records use and that
  Mixxx locks onto them.

The audio path that makes DVS possible is already built and verified, so what
remains is configuration rather than new code. This is the DJM-T1's original
purpose, running on Linux.
