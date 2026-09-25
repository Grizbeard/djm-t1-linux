# DJM-T1 kernel ALSA driver

A standalone in-kernel ALSA driver for the Pioneer DJM-T1's built-in soundcard,
the upstream-track alternative to the userspace PipeWire driver in [`../audio/`](../audio/).
The mixer's audio interface (iface 0) is vendor-specific isochronous, not
USB-Audio-Class, so the generic `snd-usb-audio` never binds it; this module does,
and registers a real 6-in/6-out, 48 kHz, 24-bit ALSA card.

The device's frame layout (18 bytes/frame, S24_3LE 6-channel interleaved; 864-byte
OUT packets, IN packets up to 1024 bytes) is exactly ALSA's `S24_3LE` 6-channel
interleaved, so URB payloads are copied to/from the PCM ring with no format
conversion.

## Status

**Validated on hardware at the ALSA level** (Raspberry Pi 5, kernel 6.18,
aarch64, gcc; zero compiler warnings). The card registers as **`hw:DJMT1Audio`**.

| Test | Result |
|---|---|
| Capture | exact 48 kHz frame rate, live data on in 1–4 |
| Playback, by ear | out 1/2 → CH1 L/R, 3/4 → CH2, 5/6 → master L/R (bypasses the channel faders); no clicks |
| Full duplex | 60 s soak: exact byte counts, 0 xHCI errors, capture and playback clocks within 2 ppm |
| Stop / restart | repeated starts are clean |
| Hot-unplug mid-duplex | userspace gets `-ENODEV`, no kernel warnings; rebinds on replug, `rmmod` afterwards |
| Timecode | a Serato Control CD on CH1 arrives on in 1/2 as a clean 1 kHz quadrature pair (90.0°, no dropouts). Forward play shows R leading L; if L leads, the RCAs are swapped. |
| Alongside the MIDI bridge | `djm_midi --no-audio` runs next to this module with Mixxx holding the card open: the full Mixxx mapping responds and its LEDs light, with audio streaming both ways. The bridge re-arms about 4 s after a re-enumeration. See [With the MIDI bridge](#with-the-midi-bridge). |

Not yet done: running under Mixxx vinyl control. Whether the MIDI gate stays open
with *no* PCM open on this card is untested; in practice Mixxx always has it open.
`checkpatch.pl` has not been rerun since the hardware fixes.

The capture tap is **before the channel trim**, so the trim does not change the
timecode level.

## Build

Match the kernel's toolchain. On a clang-built kernel (Arch, CachyOS, many others):

```sh
make LLVM=1        # this repo's dev kernel was clang-built
```

On a gcc-built kernel:

```sh
make
```

Needs the running kernel's build tree (`linux-headers` / `/lib/modules/$(uname -r)/build`).

## Try it

```sh
sudo insmod djmt1_audio.ko
dmesg | tail                     # expect "Pioneer DJM-T1 ALSA card registered"
arecord -D hw:DJMT1Audio -f S24_3LE -c 6 -r 48000 -t raw -d 5 cap.raw
aplay   -D hw:DJMT1Audio -f S24_3LE -c 6 -r 48000 -t raw -d 5 /dev/zero
sudo rmmod djmt1_audio
```

`snd-usb-audio` does not bind iface 0 (vendor class 0xFF), so this module owns it
directly. It does bind the MIDI interfaces as its own card, and that card is also
named from "DJM-T1". This module therefore sets an explicit card id
(`DJMT1Audio`); otherwise `hw:DJMT1` and `hw:DJMT1_1` would swap with probe order.

**Do not run the libusb audio tools at the same time** (`djmt1-pipewire`,
`djmt1-capture`, `djmt1-playback`, or `djm_midi` without `--no-audio`). They
auto-detach whatever kernel driver holds iface 0, so they would silently take
the soundcard from this module.

## With the MIDI bridge

The mixer sends no MIDI until it is armed and its HID pipe is polled, and this
module does neither. Without the bridge, `snd-usb-audio`'s MIDI port (`PIONEER
DJM-T1 MIDI 1`) shows up in Mixxx but never delivers anything: the kernel's
`/proc/asound/card*/midi0` reports `Rx bytes : 0`. Run `djm_midi --no-audio`
next to this module. The flag matters, because without it the bridge claims
iface 0 for its own audio session and takes the card from this module.

`midi/systemd/djm-midi-kernel.service` is the user service for this setup. Use
it *instead of* the `djmt1-audio` + `djm-midi` pair that `install.sh` installs:

```sh
make -C midi
sudo install -m755 midi/djm_midi /usr/local/bin/djm_midi
install -Dm644 midi/systemd/djm-midi-kernel.service ~/.config/systemd/user/djm-midi-kernel.service
systemctl --user daemon-reload
systemctl --user enable --now djm-midi-kernel.service
```

In Mixxx, enable **`DJM-T1 MIDI 1`**, which is the bridge's port, and leave
`PIONEER DJM-T1 MIDI 1` disabled. Two limits:

- After a replug the service re-arms the mixer by itself, but Mixxx does not
  reopen a MIDI port that disappeared. Restart Mixxx, or disable and re-enable
  the controller.
- The bridge logs to the system journal
  (`sudo journalctl _SYSTEMD_USER_UNIT=djm-midi-kernel.service`), not to
  `journalctl --user`, on systems without a persistent per-user journal.

## Scope

This driver covers **audio only**. MIDI on the DJM-T1 needs the arm plus the HID
gate (see the white paper) and is handled by the userspace bridge `../midi/djm_midi`;
folding that into the kernel is a separate, larger effort.
