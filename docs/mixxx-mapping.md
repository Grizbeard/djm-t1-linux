# Pioneer DJM-T1 - Mixxx mapping

> Pioneer DJM-T1 Operating Instructions (DRB1610), MIDI assignment map, pages 28-29. Note names read with C-1 = 0, which reproduced 114 of the 116 captured bindings exactly. Bindings marked source: manual come from that table and have not been confirmed on the wire.

## What each control does

### Browse

| Control | MIDI | Mixxx |
|---|---|---|
| BROWSE | `CC 0` | `[Library]` `MoveVertical` |
| SHIFT + BROWSE | `CC 64` | `[Playlist]` `SelectPlaylist` |
| BROWSE PUSH | `NOTE 0` | `[Library]` `GoToItem` |
| SHIFT + BROWSE PUSH | `NOTE 64` | `libraryFocus` (script) |

### CH1

| Control | MIDI | Mixxx |
|---|---|---|
| CH1 CUE | `NOTE 47` | `[Channel1]` `pfl` |
| SHIFT + CH1 CUE | `NOTE 111` | `[Channel1]` `bpm_tap` |
| CH1 HI | `CC 15` | `[EqualizerRack1_[Channel1]_Effect1]` `parameter3` |
| CH1 LOW | `CC 19` | `[EqualizerRack1_[Channel1]_Effect1]` `parameter1` |
| CH1 MID | `CC 17` | `[EqualizerRack1_[Channel1]_Effect1]` `parameter2` |
| CH1 TRIM | `CC 13` | `[Channel1]` `pregain` |
| CH1 VOLUME | `CC 21` | `[Channel1]` `volume` |

### CH2

| Control | MIDI | Mixxx |
|---|---|---|
| CH2 CUE | `NOTE 48` | `[Channel2]` `pfl` |
| SHIFT + CH2 CUE | `NOTE 112` | `[Channel2]` `bpm_tap` |
| CH2 HI | `CC 16` | `[EqualizerRack1_[Channel2]_Effect1]` `parameter3` |
| CH2 LOW | `CC 20` | `[EqualizerRack1_[Channel2]_Effect1]` `parameter1` |
| CH2 MID | `CC 18` | `[EqualizerRack1_[Channel2]_Effect1]` `parameter2` |
| CH2 TRIM | `CC 14` | `[Channel2]` `pregain` |
| CH2 VOLUME | `CC 22` | `[Channel2]` `volume` |

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
| FX1 Assign A | `NOTE 7` | `[EffectRack1_EffectUnit1]` `group_[Channel1]_enable` |
| SHIFT + FX1 Assign A | `NOTE 71` | `[Channel1]` `rate_temp_down` |
| FX2 Assign A | `NOTE 9` | `[EffectRack1_EffectUnit2]` `group_[Channel1]_enable` |
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
| LOAD A | `NOTE 1` | `[Channel1]` `LoadSelectedTrack` |
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
| FX1 Assign B | `NOTE 8` | `[EffectRack1_EffectUnit1]` `group_[Channel2]_enable` |
| SHIFT + FX1 Assign B | `NOTE 72` | `[Channel2]` `rate_temp_down` |
| FX2 Assign B | `NOTE 10` | `[EffectRack1_EffectUnit2]` `group_[Channel2]_enable` |
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
| LOAD B | `NOTE 2` | `[Channel2]` `LoadSelectedTrack` |
| SHIFT + LOAD B | `NOTE 66` | `cloneFromA` (script) |
| Play B | `NOTE 4` | `[Channel2]` `play` |
| SHIFT + Play B | `NOTE 68` | `relativeB` (script) |
| SYNC B | `NOTE 6` | `[Channel2]` `sync_enabled` |
| SHIFT + SYNC B | `NOTE 70` | `[Channel2]` `sync_leader` |

### FX1

| Control | MIDI | Mixxx |
|---|---|---|
| FX1_1 Level | `CC 3` | `[EffectRack1_EffectUnit1_Effect1]` `meta` |
| FX1_1 On | `NOTE 15` | `[EffectRack1_EffectUnit1_Effect1]` `enabled` |
| SHIFT + FX1_1 On | `NOTE 79` | `[EffectRack1_EffectUnit1_Effect1]` `next_effect` |
| FX1_2 Level | `CC 5` | `[EffectRack1_EffectUnit1_Effect2]` `meta` |
| FX1_2 On | `NOTE 17` | `[EffectRack1_EffectUnit1_Effect2]` `enabled` |
| SHIFT + FX1_2 On | `NOTE 81` | `[EffectRack1_EffectUnit1_Effect2]` `next_effect` |
| FX1_3 Level | `CC 7` | `[EffectRack1_EffectUnit1_Effect3]` `meta` |
| FX1_3 On | `NOTE 19` | `[EffectRack1_EffectUnit1_Effect3]` `enabled` |
| SHIFT + FX1_3 On | `NOTE 83` | `[EffectRack1_EffectUnit1_Effect3]` `next_effect` |
| FX1 DRY/ WET | `CC 1` | `[EffectRack1_EffectUnit1]` `mix` |
| FX1 ON | `NOTE 13` | `[EffectRack1_EffectUnit1]` `enabled` |
| SHIFT + FX1 ON | `NOTE 77` | `[EffectRack1_EffectUnit1]` `next_chain_preset` |

### FX2

| Control | MIDI | Mixxx |
|---|---|---|
| FX2_1 Level | `CC 4` | `[EffectRack1_EffectUnit2_Effect1]` `meta` |
| FX2_1 On | `NOTE 16` | `[EffectRack1_EffectUnit2_Effect1]` `enabled` |
| SHIFT + FX2_1 On | `NOTE 80` | `[EffectRack1_EffectUnit2_Effect1]` `next_effect` |
| FX2_2 Level | `CC 6` | `[EffectRack1_EffectUnit2_Effect2]` `meta` |
| FX2_2 On | `NOTE 18` | `[EffectRack1_EffectUnit2_Effect2]` `enabled` |
| SHIFT + FX2_2 On | `NOTE 82` | `[EffectRack1_EffectUnit2_Effect2]` `next_effect` |
| FX2_3 Level | `CC 8` | `[EffectRack1_EffectUnit2_Effect3]` `meta` |
| FX2_3 On | `NOTE 20` | `[EffectRack1_EffectUnit2_Effect3]` `enabled` |
| SHIFT + FX2_3 On | `NOTE 84` | `[EffectRack1_EffectUnit2_Effect3]` `next_effect` |
| FX2 DRY/ WET | `CC 2` | `[EffectRack1_EffectUnit2]` `mix` |
| FX2 On | `NOTE 14` | `[EffectRack1_EffectUnit2]` `enabled` |
| SHIFT + FX2 On | `NOTE 78` | `[EffectRack1_EffectUnit2]` `next_chain_preset` |

### Master

| Control | MIDI | Mixxx |
|---|---|---|
| CROSSFADER | `CC 23` | `[Master]` `crossfader` |

### Other

| Control | MIDI | Mixxx |
|---|---|---|
| SNAP | `NOTE 49` | `quantizeAll` (script) |
| SHIFT + SNAP | `NOTE 113` | `slipAll` (script) |

## Where this departs from the TRAKTOR mapping

The panel was designed around TRAKTOR, and a few of its
functions have no Mixxx counterpart. Each one below is a
deliberate substitution, not an oversight.

- FX ON steps the effect unit's chain preset, which nothing else on this panel reaches. Its light shows the unit's own master enable, which SHIFT+FX ON toggles -- so the lamp reports something the button actually controls.
- SNAP is TRAKTOR's snap-to-grid and SHIFT+SNAP its quantize. Mixxx has only quantize, so SNAP drives quantize on both decks and SHIFT+SNAP drives slip.
- SHIFT + an effect knob switches effect type in TRAKTOR. These are absolute knobs, so that would make effect choice depend on knob position; SHIFT + the effect button steps the type instead, which is what the manual specifies for Generic Controller Mode anyway.
- SELECT (hot cue / sampler) and its CROSS FADER CONTROL shift function are not mapped. The firmware re-addresses the section, so both modes are bound at once and Mixxx never needs to know which is showing.

## Sends MIDI, deliberately unmapped

Mostly addresses the hardware emits for a TRAKTOR function
that does not exist here, or that the manual lists as having
no function at all. They are left free on purpose.

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
