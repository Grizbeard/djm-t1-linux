# Pioneer DJM-T1 (USB 08e4:015e) — Device Interface Specification

**Status:** draft 1, 2026-09-14
**Purpose:** a vendor-neutral specification of the DJM-T1's USB interfaces, sufficient
to implement a Linux driver without reference to any vendor source code.

---

## 0. Provenance and licensing

This document is a **specification written from facts**, assembled from two independent
sources. It contains no vendor source code, no vendor identifiers, and no transcribed
expression. Implementations should be written against **this document only**.

| Ref | Source | Nature |
|---|---|---|
| **[U]** | `usbmon` captures of the Windows driver over KVM passthrough, documented in this repository (see [WHITEPAPER.md](WHITEPAPER.md) and [reverse-engineering.md](reverse-engineering.md)) | Observed bus traffic |
| **[A]** | AlphaTheta/Pioneer macOS driver sources published under the Apple Public Source License 2.0 ("DJM-T1 USBAudio 1.0.0", © Pioneer Corporation 2011) | Published source, read for interface facts only |
| **[A2]** | The sibling APSL package for the DJM-900nexus, used only to distinguish shared framework code from model-specific values | Cross-model corroboration |

**Licensing constraint.** APSL 2.0 is OSI-approved but **GPL-incompatible**. Source
covered by [A] must not be copied into a Linux kernel driver (GPL-2.0), into Mixxx
(GPL-2.0-or-later), or into an MIT-licensed project. Facts about a hardware interface —
register numbers, packet sizes, channel counts, operation ordering — are not protected
expression, and this document records only those. Implementers should cite this
specification, not [A], in commit messages and headers.

Every claim below is tagged with its source. Claims tagged **[interp]** are engineering
interpretation, not observed fact, and should be validated.

---

## 1. Device identity

| Property | Value | Src |
|---|---|---|
| USB Vendor ID | `0x08e4` (Pioneer Corporation) | [U] |
| Product ID | `0x015e` | [U] |
| Speed | High-speed (USB 2.0) | [U] |
| Configurations | 1 | [U] |
| Interfaces | 4 | [U] |
| Product string | `PIONEER DJM-T1` | [U][A] |

### 1.1 Interface layout

| # | Class | Alt settings | Endpoints | Role |
|---|---|---|---|---|
| 0 | Vendor-specific (`0xFF`) | 0 (idle), **1 (streaming)** | iso OUT `0x01`, iso IN `0x82` | Built-in soundcard |
| 1 | Audio Control | — | none | Control interface; exposes no controls |
| 2 | Audio / MIDI Streaming | single | bulk OUT `0x04`, bulk IN `0x85` | USB-MIDI control surface |
| 3 | HID | single | int OUT `0x06`, int IN `0x87` | Control surface mirror; transmission interlock |

Interface 0 is vendor-class, **not** USB Audio Class. It carries no standard AS
descriptors, so no class driver binds it and no format can be negotiated from
descriptors. The vendor driver therefore hardcodes the entire stream description;
Section 2 records those hardcoded values. [A]

---

## 2. Audio interface (interface 0)

### 2.1 Stream format — fixed, non-negotiable

| Property | Value | Src |
|---|---|---|
| Encoding | Linear PCM, signed, little-endian | [A] |
| Sample rate | **48 000 Hz — the only supported rate** | [A] |
| Bit resolution | **24 bits** | [A] |
| Subframe (container) size | **3 bytes** — packed, not padded to 4 | [A] |
| Channels, capture (device→host) | **6** | [A] |
| Channels, playback (host→device) | **6** | [A] |
| Frame layout | 6 channels interleaved, 3 bytes each = **18 bytes per frame** | [A][U] |
| ALSA equivalent | `SNDRV_PCM_FMTBIT_S24_3LE`, 6 ch, 48 kHz | [interp] |

The format is identical in both directions. The vendor driver advertises exactly one
sample rate and one bit depth, and selects alternate setting **1** unconditionally
without consulting descriptors. [A]

Cross-model note: the sibling DJM-900nexus driver defaults to 44 100 Hz; the DJM-T1
driver defaults to 48 000 Hz. The rate is genuinely model-specific, not a framework
default. [A2]

### 2.2 Framing

At high speed, endpoint `bInterval = 4`, which is `2^(4-1) = 8` microframes = **1 ms**,
giving **one isochronous transaction per 1 ms USB frame**. [U][A]

| Quantity | Value | Derivation | Src |
|---|---|---|---|
| Frames per packet | 48 | 48 000 Hz ÷ 1000 packets/s, exact — no fractional accumulator needed | [A] |
| Nominal packet size | **864 bytes** | 48 frames × 18 bytes | [U][A] |
| Allocation size per packet | 882 bytes | (48 + 1) frames × 18 bytes — one frame of headroom | [A] |
| **Requested IN packet size** | **918 bytes** | (48 + 3) frames × 18 bytes — three frames of headroom | [A] |
| Endpoint `wMaxPacketSize` | 1024 bytes | descriptor | [U] |

Observed traffic shows every packet, both directions, at exactly 864 bytes with no
variation. [U] The vendor driver nonetheless requests **918** bytes per IN transaction
and sets its pipe policy accordingly, deliberately over-allocating so a device that
briefly delivers more than nominal is not truncated. [A]

**Implementation guidance:** submit IN packets sized at least 918 bytes (`wMaxPacketSize`
= 1024 is also safe and simpler); submit OUT packets at exactly 864 bytes. Never assume
`actual_length == 864` on IN; always use the per-packet actual length. [interp]

### 2.3 Clocking and synchronisation — **key section**

| Fact | Src |
|---|---|
| Neither endpoint has an explicit synchronisation type; the vendor driver reports "no sync type" for both | [A] |
| There is **no feedback (explicit sync) endpoint**. The vendor driver's feedback-endpoint discovery is disabled outright | [A] |
| No pitch control, no adaptive rate control | [A] |
| The device free-runs at its own 48 kHz. The host does not rate-control it | [U][A] |
| The vendor driver designates the **playback (OUT) stream** as the engine's timing reference, overriding the framework's default selection logic | [A] |
| Both host/device sample-rate compensation paths are explicitly left disabled | [A] |
| The sibling DJM-900nexus driver makes the identical choice, annotated to the effect that playback will not start until input arrives | [A2] |

**Interpretation.** This is a "device is clock master, host trusts the nominal rate"
design. There is no rate negotiation and no drift-correction mechanism in the vendor's
own driver: it derives its audio timeline from the outbound stream's transmission
cadence and assumes 48 frames per millisecond holds. Because both directions run off
the same device clock and the same USB SOF cadence, IN and OUT stay mutually
synchronous by construction. [interp]

**Consequence for a Linux implementation.** A kernel ALSA driver inherits this for free:
both substreams advance on URB completion against the same host controller SOF clock,
which is exactly the model the vendor driver assumes. Deriving the stream position from
OUT completions matches the vendor's choice; deriving it from IN is a deviation that
should be justified if taken. [interp]

**Consequence for a userspace implementation.** Any design that hands audio from the
device's free-running clock to a *separately clocked* consumer (a sound-server graph
running on another device's clock or on a system timer) reintroduces a drift problem
that the vendor driver does not have, because there is no feedback endpoint to correct
with. Such a design needs either adaptive resampling or explicit rate matching. This is
the single strongest argument for the kernel-driver path over a sound-server bridge,
and it is now supported by the vendor's own design rather than inferred. [interp]

### 2.4 Stream startup sequence

1. Claim interface 0. No kernel driver binds it, so no detach is required. [U]
2. Select **alternate setting 0** first, to bring the interface to a known idle state. [A]
3. Select **alternate setting 1**. This alone enables streaming — there is no
   vendor-specific "start streaming" command. [U][A]
4. Issue a USB Audio Class `SET_CUR` for `SAMPLING_FREQ_CONTROL`:
   `bmRequestType = 0x22` (class, host→device, endpoint recipient), `bRequest = SET_CUR`,
   `wValue = 0x0100`, `wIndex = 0x82`, `wLength = 3`, payload = 48000 as 24-bit
   little-endian (`80 BB 00`). [U][A]
5. Submit isochronous transfers on `0x82` (IN) and `0x01` (OUT). [U]

Note on step 4: the vendor driver unconditionally believes the endpoint has sample-
frequency control and unconditionally addresses the request to `0x82` for **both**
directions, because its endpoint-address accessor is hardcoded to that value. This
explains why bus captures show the request only on `0x82`. [A]

This request is **not** required for streaming, and is **not** part of the MIDI
transmission interlock (Section 4.2) — confirmed by isolating it. [U] Issue it anyway to
mirror the vendor driver; it is harmless.

Stopping and restarting playback produces no control transfers. There is no
format/rate handshake to reproduce. [U]

### 2.5 Buffer sizing observed in the vendor driver

Recorded for calibration only; not requirements. [A]

- The sample buffer is allocated at **twice** the framework's computed size.
- IN read buffers are sized from a forced ceiling of 3072 bytes rather than the
  descriptor's `wMaxPacketSize`.
- Minimum frame offset (scheduling lead) is 6 USB frames.

---

## 3. MIDI interface (interface 2)

Standard USB-MIDI class, single alternate setting, 4-byte USB-MIDI event packets whose
code-index number selects the number of MIDI bytes that follow. [U]

| Direction | Endpoint | Type |
|---|---|---|
| Device → host | `0x85` | bulk IN |
| Host → device (LEDs) | `0x04` | bulk OUT |

All control-surface messages are on MIDI channel 1. Continuous controls are 7-bit
absolute Control Change; buttons emit Note-On velocity `0x7F` immediately followed by
velocity `0x00` on a single press. The full control-number map is in [midi-map.md](midi-map.md) and is not repeated
here. [U]

The MIDI interface transmits **only** while the interlock in Section 4.2 is satisfied.

---

## 4. Control transfers and the transmission interlock

### 4.1 The arm sequence

Issued once by the vendor driver on bind. Vendor control writes, device recipient:
`bmRequestType = 0x40`, `bRequest = 0x03`, `wLength = 0`. [U]

| Order | `wValue` | `wIndex` | Read-back |
|---|---|---|---|
| 1 | `0x1100` | `0x8002` | yes |
| 2 | `0x2200` | `0x8002` | yes |
| 3 | `0x030A` | `0x8002` | yes |
| 4 | `0x0000` | `0x8003` | — |
| 5 | `0x0000` | `0x8004` | — |

Read-backs use `bmRequestType = 0xC0`, `bRequest = 0x00`, same `wIndex`, 3-byte
response, and return `00 01 00` as a status acknowledgement. Because the requests
target the device rather than an interface, no interface claim is needed to issue them. [U]

`wIndex` values `0x8002` / `0x8003` / `0x8004` behave as device registers; `wValue`
carries the value written. [interp]

> **Not present in [A].** The arm sequence does not appear anywhere in the published
> macOS sources. On macOS it is issued by a separate closed vendor component loaded
> through the audio framework's plugin mechanism, which carries no APSL obligation.
> The arm is therefore known **only** from bus observation [U], and this document is
> its only specification.

### 4.2 The transmission interlock

The device does not transmit its control surface merely because it has been armed. It
transmits only while a **complete multi-pipe session** is live: [U]

- isochronous audio streaming on interface 0 (both directions), **and**
- the HID interrupt endpoint `0x87` being **actively polled**.

The device mirrors control-surface data to the MIDI endpoint `0x85` and the HID
endpoint `0x87` in lockstep. Verified by changing one variable at a time:

| Session state | Control surface transmits? |
|---|---|
| Armed, MIDI IN read pending | No |
| Armed, MIDI IN read pending, live audio session | No |
| Armed, MIDI IN read pending, live audio session, `0x87` polled | **Yes** |

Stock Linux satisfies neither condition: nothing opens the HID interface, and no PCM
stream exists for a vendor-class interface. [U]

The armed and un-gated state is **volatile**. Any USB re-enumeration — unplug, hub
reset, cable drop, power cycle — clears it, and the sequence must be reissued. [U]

**Open question.** Whether the interlock is a deliberate design or an emergent property
of the device's firmware state machine is unknown. Nothing in [A] describes it, which is
consistent with it being enforced below the level the published audio driver operates
at. Whether re-arming is required when an audio session stops and restarts — as opposed
to transmission simply resuming — has **not** been tested and matters for any design
where the PCM is opened and closed by an application. [interp]

---

## 5. HID interface (interface 3)

| Direction | Endpoint | Type |
|---|---|---|
| Device → host | `0x87` | interrupt IN |
| Host → device | `0x06` | interrupt OUT |

Polling `0x87` is one half of the interlock in Section 4.2. Beyond that, the pipe
carries the same control surface at **higher resolution than MIDI**: [U]

- Each continuous control is backed by a **10-bit ADC** (range 0–1023).
- The MIDI stream publishes the top 7 bits: `MIDI = HID >> 3`.
- Reports are 16 bytes, beginning with a report ID, packing several 10-bit
  little-endian fields. Report IDs `0x01`, `0x02`, `0x03`, `0x05`, `0x06`, `0x09` have
  been observed carrying control data.

The complete field-to-control assignment is **not determined** (Section 7).

---

## 6. Channel assignment — **NOT DETERMINED**

This is the single most important unresolved item, and the reason a bench session is
still required.

**What is known:** six channels in each direction, three stereo pairs each way. [A]

**What is not known:** which physical signal each channel carries.

The published macOS sources do **not** answer this. The vendor driver bypasses the
entire USB Audio terminal and connection-graph machinery — it short-circuits terminal
enumeration and path building, exposes no mixer controls, and populates no channel-name
dictionary. It presents six anonymous channels in each direction and lets the
application layer assign meaning. There are no channel names, no terminal types, and no
input/output selectors to read. [A]

Partial observations from bus capture, with one turntable connected: [U]

- Capture channels 0/1 and 4/5 carried signal.
- Capture channels 2/3 read near-silent with nothing connected.
- Host playback appeared to loop back onto capture channels 4/5.

**Working hypothesis [interp]:** capture 0/1 = channel 1 phono/line input, capture 2/3 =
channel 2 phono/line input (silent because nothing was connected to deck 2 during the
capture), capture 4/5 = a master or monitor return fed from the analogue mix. This is
consistent with both observations and with the layout of a two-deck DVS mixer, but it
is **unverified**.

### 6.1 Bench procedure to resolve it

Required equipment: both turntables connected, a signal source for each mixer channel.

1. Stream capture with per-channel level metering.
2. Play a record on deck 1 only. Record which channel pair moves.
3. Stop; play a record on deck 2 only. Record which channel pair moves.
4. With both decks silent, raise the mixer's channel faders and observe whether any
   capture pair follows the analogue mix — that identifies the master/monitor return.
5. For outputs: emit a distinct test tone on one host playback pair at a time, set each
   mixer channel's source selector to USB, and record which mixer channel reproduces it.
6. Record the result as a table in this section and delete this procedure.

Until step 6 is complete, no DVS configuration can be finalised, because the timecode
input pairs and the deck return pairs are both unknown.

---

## 7. Other undetermined items

| Item | Status |
|---|---|
| HID report field → physical control map | Undetermined. Requires a per-control capture: move one control at a time and record which report ID and byte offset changes. |
| SHIFT layer button codes | Partially determined. Holding SHIFT changes the codes the performance pads emit; the shifted set is only partly discovered. |
| Device configuration (MIDI channel, fader/crossfader curves) | Undetermined. Configured on Windows/macOS by a vendor utility via vendor control writes of the same class as the arm. Not present in [A]. Would require capturing that utility. |
| Centre detent values for detented controls | Undetermined. The crossfader and EQ knobs need a calibration pass ending at the physical centre so the true midpoint can be recorded. |
| LED output map beyond the cue buttons | Partially determined. The host→device MIDI path is verified at the USB level; the note-to-LED mapping is confirmed only for the two cue buttons. |

---

## 8. Implementation summary for a Linux ALSA driver

Matching only interface 0 by number keeps the driver disjoint from the MIDI and HID
interfaces, which a separate userspace component must own in order to satisfy the
interlock.

1. Match on vendor `0x08e4`, product `0x015e`, **interface number 0**.
2. Register one card with one PCM device: 6-in / 6-out, `S24_3LE`, 48 kHz fixed, both
   rate and format non-negotiable.
3. On trigger-start: select alt 0, then alt 1; optionally issue the `SET_CUR` sampling-
   frequency request per Section 2.4; submit isochronous URBs.
4. Per-packet sizes: OUT exactly 864 bytes; IN at least 918 (1024 is safe). One packet
   per 1 ms frame.
5. The device frame layout is byte-identical to interleaved 6-channel `S24_3LE`, so the
   URB payload maps to the PCM ring with no conversion.
6. Advance the stream position from URB completion. Following the vendor driver, derive
   engine timing from the playback direction (Section 2.3).
7. Expect no feedback endpoint and implement no rate control.
8. The MIDI/HID interlock component must be running for the control surface to work;
   the audio driver itself is unaffected by it.

---

## 9. Revision history

| Rev | Date | Change |
|---|---|---|
| draft 1 | 2026-09-14 | Initial. Format, framing, clocking, startup sequence and negative results established from [A]; arm sequence, interlock, HID resolution and partial channel observations from [U]. |
