# DJM-T1_Custom - Mixxx mapping

> Pioneer DJM-T1 Operating Instructions (DRB1610), MIDI assignment map, pages 28-29. Note names read with C-1 = 0, which reproduced 114 of the 116 captured bindings exactly. Bindings marked source: manual come from that table and have not been confirmed on the wire.

## What each control does

### Browse

| Control | MIDI | Mixxx |
|---|---|---|
| BROWSE | `CC 0` | `[Library]` `MoveVertical` |
| SHIFT + BROWSE | `CC 64` | `[Playlist]` `SelectPlaylist` |
| BROWSE PUSH | `NOTE 0` | `browsePush` (script) |
| SHIFT + BROWSE PUSH | `NOTE 64` | `browseShiftPush` (script) |

### CH1

| Control | MIDI | Mixxx |
|---|---|---|
| CH1 CUE | `NOTE 47` | `[Channel1]` `pfl` |
| SHIFT + CH1 CUE | `NOTE 111` | `[Channel1]` `bpm_tap` |

### CH2

| Control | MIDI | Mixxx |
|---|---|---|
| CH2 CUE | `NOTE 48` | `[Channel2]` `pfl` |
| SHIFT + CH2 CUE | `NOTE 112` | `[Channel2]` `bpm_tap` |

### Deck A

| Control | MIDI | Mixxx |
|---|---|---|
| ACTIVE A | `NOTE 43` | `bankA` (script) |
| SAMPLER mode ACTIVE A | `NOTE 44` | `samplerHoldA` (script) |
| SAMPLER mode, SHIFT + ACTIVE A | `NOTE 108` | `samplerRepeatA` (script) |
| AUTO LOOP A | `CC 9` | `[Channel1]` `beatloop_size` |
| SHIFT + AUTO LOOP A | `CC 73` | `[Channel1]` `loop_move` |
| SAMPLER mode, SHIFT + AUTO LOOP A | `CC 74` | `samplerGainA` (script) |
| AUTO LOOP A Push | `NOTE 21` | `loopA` (script) |
| SAMPLER mode, SHIFT + AUTO LOOP A Push | `NOTE 86` | `samplerGainResetA` (script) |
| Cue A | `NOTE 11` | `[Channel1]` `cue_default` |
| SHIFT + Cue A | `NOTE 75` | `absoluteA` (script) |
| FX1 Assign A | `NOTE 7` | `fx1Select1` (script) |
| SHIFT + FX1 Assign A | `NOTE 71` | `[Channel1]` `rate_temp_down` |
| FX2 Assign A | `NOTE 9` | `fx1Select2` (script) |
| SHIFT + FX2 Assign A | `NOTE 73` | `[Channel1]` `rate_temp_up` |
| Hot Cue 1 A | `NOTE 27` | `hotcueA1` (script) |
| SHIFT + Hot Cue 1 A | `NOTE 91` | `hotcueA1Clear` (script) |
| SAMPLER mode Hot Cue 1 A | `NOTE 28` | `samplerA1` (script) |
| SAMPLER mode, SHIFT + Hot Cue 1 A | `NOTE 92` | `samplerA1Eject` (script) |
| Hot Cue 2 A | `NOTE 31` | `hotcueA2` (script) |
| SHIFT + Hot Cue 2 A | `NOTE 95` | `hotcueA2Clear` (script) |
| SAMPLER mode Hot Cue 2 A | `NOTE 32` | `samplerA2` (script) |
| SAMPLER mode, SHIFT + Hot Cue 2 A | `NOTE 96` | `samplerA2Eject` (script) |
| Hot Cue 3 A | `NOTE 35` | `hotcueA3` (script) |
| SHIFT + Hot Cue 3 A | `NOTE 99` | `hotcueA3Clear` (script) |
| SAMPLER mode Hot Cue 3 A | `NOTE 36` | `samplerA3` (script) |
| SAMPLER mode, SHIFT + Hot Cue 3 A | `NOTE 100` | `samplerA3Eject` (script) |
| Hot Cue 4 A | `NOTE 39` | `hotcueA4` (script) |
| SHIFT + Hot Cue 4 A | `NOTE 103` | `hotcueA4Clear` (script) |
| SAMPLER mode Hot Cue 4 A | `NOTE 40` | `samplerA4` (script) |
| SAMPLER mode, SHIFT + Hot Cue 4 A | `NOTE 104` | `samplerA4Eject` (script) |
| LOAD A | `NOTE 1` | `loadA` (script) |
| SHIFT + LOAD A | `NOTE 65` | `cloneFromB` (script) |
| Play A | `NOTE 3` | `[Channel1]` `play` |
| SHIFT + Play A | `NOTE 67` | `relativeA` (script) |
| SYNC A | `NOTE 5` | `[Channel1]` `sync_enabled` |
| SHIFT + SYNC A | `NOTE 69` | `[Channel1]` `sync_leader` |

### Deck B

| Control | MIDI | Mixxx |
|---|---|---|
| ACTIVE B | `NOTE 45` | `bankB` (script) |
| SAMPLER mode ACTIVE B | `NOTE 46` | `samplerHoldB` (script) |
| SAMPLER mode, SHIFT + ACTIVE B | `NOTE 110` | `samplerRepeatB` (script) |
| AUTO LOOP B | `CC 11` | `[Channel2]` `beatloop_size` |
| SHIFT + AUTO LOOP B | `CC 75` | `[Channel2]` `loop_move` |
| SAMPLER mode, SHIFT + AUTO LOOP B | `CC 76` | `samplerGainB` (script) |
| AUTO LOOP B Push | `NOTE 23` | `loopB` (script) |
| SAMPLER mode, SHIFT + AUTO LOOP B Push | `NOTE 88` | `samplerGainResetB` (script) |
| CUE B | `NOTE 12` | `[Channel2]` `cue_default` |
| SHIFT + CUE B | `NOTE 76` | `absoluteB` (script) |
| FX1 Assign B | `NOTE 8` | `fx2Select1` (script) |
| SHIFT + FX1 Assign B | `NOTE 72` | `[Channel2]` `rate_temp_down` |
| FX2 Assign B | `NOTE 10` | `fx2Select2` (script) |
| SHIFT + FX2 Assign B | `NOTE 74` | `[Channel2]` `rate_temp_up` |
| Hot Cue 1 B | `NOTE 29` | `hotcueB1` (script) |
| SHIFT + Hot Cue 1 B | `NOTE 93` | `hotcueB1Clear` (script) |
| SAMPLER mode Hot Cue 1 B | `NOTE 30` | `samplerB1` (script) |
| SAMPLER mode, SHIFT + Hot Cue 1 B | `NOTE 94` | `samplerB1Eject` (script) |
| Hot Cue 2 B | `NOTE 33` | `hotcueB2` (script) |
| SHIFT + Hot Cue 2 B | `NOTE 97` | `hotcueB2Clear` (script) |
| SAMPLER mode Hot Cue 2 B | `NOTE 34` | `samplerB2` (script) |
| SAMPLER mode, SHIFT + Hot Cue 2 B | `NOTE 98` | `samplerB2Eject` (script) |
| Hot Cue 3 B | `NOTE 37` | `hotcueB3` (script) |
| SHIFT + Hot Cue 3 B | `NOTE 101` | `hotcueB3Clear` (script) |
| SAMPLER mode Hot Cue 3 B | `NOTE 38` | `samplerB3` (script) |
| SAMPLER mode, SHIFT + Hot Cue 3 B | `NOTE 102` | `samplerB3Eject` (script) |
| Hot Cue 4 B | `NOTE 41` | `hotcueB4` (script) |
| SHIFT + Hot Cue 4 B | `NOTE 105` | `hotcueB4Clear` (script) |
| SAMPLER mode Hot Cue 4 B | `NOTE 42` | `samplerB4` (script) |
| SAMPLER mode, SHIFT + Hot Cue 4 B | `NOTE 106` | `samplerB4Eject` (script) |
| LOAD B | `NOTE 2` | `loadB` (script) |
| SHIFT + LOAD B | `NOTE 66` | `cloneFromA` (script) |
| Play B | `NOTE 4` | `[Channel2]` `play` |
| SHIFT + Play B | `NOTE 68` | `relativeB` (script) |
| SYNC B | `NOTE 6` | `[Channel2]` `sync_enabled` |
| SHIFT + SYNC B | `NOTE 70` | `[Channel2]` `sync_leader` |

### FX1

| Control | MIDI | Mixxx |
|---|---|---|
| FX1_1 Level | `CC 3` | `fx1Level1` (script) |
| FX1_1 On | `NOTE 15` | `fx1Slot1` (script) |
| SHIFT + FX1_1 On | `NOTE 79` | `fx1NextEffect1` (script) |
| FX1_2 Level | `CC 5` | `fx1Level2` (script) |
| FX1_2 On | `NOTE 17` | `fx1Slot2` (script) |
| SHIFT + FX1_2 On | `NOTE 81` | `fx1NextEffect2` (script) |
| FX1_3 Level | `CC 7` | `fx1Level3` (script) |
| FX1_3 On | `NOTE 19` | `fx1Slot3` (script) |
| SHIFT + FX1_3 On | `NOTE 83` | `fx1NextEffect3` (script) |
| FX1 DRY/ WET | `CC 1` | `fx1Mix` (script) |
| FX1 ON | `NOTE 13` | `fx1On` (script) |
| SHIFT + FX1 ON | `NOTE 77` | `fx1NextChain` (script) |

### FX2

| Control | MIDI | Mixxx |
|---|---|---|
| FX2_1 Level | `CC 4` | `fx2Level1` (script) |
| FX2_1 On | `NOTE 16` | `fx2Slot1` (script) |
| SHIFT + FX2_1 On | `NOTE 80` | `fx2NextEffect1` (script) |
| FX2_2 Level | `CC 6` | `fx2Level2` (script) |
| FX2_2 On | `NOTE 18` | `fx2Slot2` (script) |
| SHIFT + FX2_2 On | `NOTE 82` | `fx2NextEffect2` (script) |
| FX2_3 Level | `CC 8` | `fx2Level3` (script) |
| FX2_3 On | `NOTE 20` | `fx2Slot3` (script) |
| SHIFT + FX2_3 On | `NOTE 84` | `fx2NextEffect3` (script) |
| FX2 DRY/ WET | `CC 2` | `fx2Mix` (script) |
| FX2 On | `NOTE 14` | `fx2On` (script) |
| SHIFT + FX2 On | `NOTE 78` | `fx2NextChain` (script) |

### Other

| Control | MIDI | Mixxx |
|---|---|---|
| SNAP | `NOTE 49` | `quantizeAll` (script) |
| SHIFT + SNAP | `NOTE 113` | `slipAll` (script) |

## Where this departs from the TRAKTOR mapping

The panel was designed around TRAKTOR, and a few of its
functions have no Mixxx counterpart. Each one below is a
deliberate substitution, not an oversight.

- Each FX section plays two effect units on one deck: FX1 units 1 and 2 on deck 1, FX2 units 3 and 4 on deck 2. The mapping sets that routing every time it starts. The ASSIGN buttons are grouped by deck, and each deck's pair picks which of its two units the FX section controls: under deck A, FX1 ASSIGN picks unit 1 and FX2 ASSIGN unit 2; under deck B, FX1 ASSIGN picks unit 3 and FX2 ASSIGN unit 4. The lit button says which. The section's ON, DRY/WET, level knobs and effect buttons all follow it. SHIFT + ASSIGN keeps the stock pitch bend.
- Picking a unit changes only what the section controls. Each unit keeps its own on/off state, so both of a deck's units can run at once and one left on keeps playing while the other is adjusted. After a switch the knobs pick up the new unit's settings by soft takeover: a knob does nothing until it passes the value the unit already has.
- The CH1/CH2 faders, TRIM, HI/MID/LOW and the crossfader are captured but not mapped, since the analog mixer already does them and mapping them would apply them twice. Mixer-section MIDI (the CH1/CH2 buttons) can stay off.
- FX ON switches the selected effect unit on and off through its master enable, and its light shows that enable. SHIFT+FX ON steps that unit's chain preset, which nothing else on this panel reaches.
- SNAP is TRAKTOR's snap-to-grid and SHIFT+SNAP its quantize. Mixxx has only quantize, so SNAP drives quantize on both decks and SHIFT+SNAP drives slip.
- SHIFT + an effect knob switches effect type in TRAKTOR. These are absolute knobs, so that would make effect choice depend on knob position; SHIFT + the effect button steps the type instead, which is what the manual specifies for Generic Controller Mode anyway.
- ACTIVE A/B, which switches that deck's four cue buttons between hot cues 1-4 and 5-8, also publishes the deck's bank as [TerminalWide],hotcue_bank_1 and _2 (0 = cues 1-4, 1 = 5-8). The Terminal-wide skin's four-cue row follows it, so the screen shows the four cues the buttons address. With a skin that has no such control the bank stays private to the mapping, as before.
- SELECT (hot cue / sampler) and its CROSS FADER CONTROL shift function are not mapped. The firmware re-addresses the section, so both modes are bound at once and Mixxx never needs to know which is showing.
- BROWSE PUSH moves between the Terminal-wide skin's pages: off the library page it opens the library, and in the library's track list it goes back to the decks. In the tree it still expands a folder or opens a crate. SHIFT + BROWSE PUSH opens the library on the tree, or swaps focus between the tree and the track list. LOAD A/B go back to the decks once the deck has actually taken the track; a rejected load stays put. With a skin that has no [Tab] pages, all of these behave as before.

## Set at every start

State the mapping depends on, asserted each time it loads. If a
required value does not take, nothing below it is applied.

| Mixxx | Value | |
|---|---|---|
| `[EffectRack1_EffectUnit1]` `group_[Channel1]_enable` | 1 |  |
| `[EffectRack1_EffectUnit1]` `group_[Channel2]_enable` | 0 |  |
| `[EffectRack1_EffectUnit2]` `group_[Channel1]_enable` | 1 |  |
| `[EffectRack1_EffectUnit2]` `group_[Channel2]_enable` | 0 |  |
| `[EffectRack1_EffectUnit3]` `group_[Channel1]_enable` | 0 |  |
| `[EffectRack1_EffectUnit3]` `group_[Channel2]_enable` | 1 |  |
| `[EffectRack1_EffectUnit4]` `group_[Channel1]_enable` | 0 |  |
| `[EffectRack1_EffectUnit4]` `group_[Channel2]_enable` | 1 |  |

## Sends MIDI, deliberately unmapped

Mostly addresses the hardware emits for a TRAKTOR function
that does not exist here, or that the manual lists as having
no function at all. They are left free on purpose.

- CH1 HI (`CC 15`)
- CH1 LOW (`CC 19`)
- CH1 MID (`CC 17`)
- CH1 TRIM (`CC 13`)
- CH1 VOLUME (`CC 21`)
- CH2 HI (`CC 16`)
- CH2 LOW (`CC 20`)
- CH2 MID (`CC 18`)
- CH2 TRIM (`CC 14`)
- CH2 VOLUME (`CC 22`)
- CROSSFADER (`CC 23`)
- Mode Select A (`NOTE 25`)
- Mode Select B (`NOTE 26`)
- SAMPLER mode AUTO LOOP A (`CC 10`)
- SAMPLER mode AUTO LOOP A Push (`NOTE 22`)
- SAMPLER mode AUTO LOOP B (`CC 12`)
- SAMPLER mode AUTO LOOP B Push (`NOTE 24`)
- SHIFT + ACTIVE A (`NOTE 107`)
- SHIFT + ACTIVE B (`NOTE 109`)
- SHIFT + AUTO LOOP A Push (`NOTE 85`)
- SHIFT + AUTO LOOP B Push (`NOTE 87`)
- SHIFT + CH1 HI (`CC 79`)
- SHIFT + CH1 LOW (`CC 83`)
- SHIFT + CH1 MID (`CC 81`)
- SHIFT + CH1 TRIM (`CC 77`)
- SHIFT + CH1 VOLUME (`CC 85`)
- SHIFT + CH2 HI (`CC 80`)
- SHIFT + CH2 LOW (`CC 84`)
- SHIFT + CH2 MID (`CC 82`)
- SHIFT + CH2 TRIM (`CC 78`)
- SHIFT + CH2 VOLUME (`CC 86`)
- SHIFT + CROSSFADER (`CC 87`)
- SHIFT + FX1 DRY/ WET (`CC 65`)
- SHIFT + FX1_1 Level (`CC 67`)
- SHIFT + FX1_2 Level (`CC 69`)
- SHIFT + FX1_3 Level (`CC 71`)
- SHIFT + FX2 DRY/ WET (`CC 66`)
- SHIFT + FX2_1 Level (`CC 68`)
- SHIFT + FX2_2 Level (`CC 70`)
- SHIFT + FX2_3 Level (`CC 72`)
- SHIFT + Mode Select A (`NOTE 89`)
- SHIFT + Mode Select B (`NOTE 90`)

## Analog, sends nothing

Verified silent during calibration, so correctly absent:

Booth, CF Curve, CF Reverse, CH1 Midi, CH2 Midi, HP Level, HP Mix, Master, Mic Aux High, Mic Aux Low, Mic Aux Select, Mic Aux Volume, SHIFT, UTILITY.
