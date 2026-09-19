"""MIDI transport, with three interchangeable backends.

The studio needs two things from MIDI and nothing else: a stream of incoming
messages with timestamps, and the ability to send a message so an LED lights.

  alsa     Linux, no Python dependencies. Reads through `aseqdump`, writes
           through `aplaymidi` or `amidi`. This is the one that talks to the
           djm_midi bridge, and it is deliberately the same mechanism
           tools/calibrate.py already proved out: one long-lived reader process
           that is re-established if it dies, never a re-subscribe per control.

  rtmidi   Anywhere python-rtmidi is installed, including Windows and macOS.
           Optional; imported lazily so its absence costs nothing.

  offline  No hardware at all. Messages can be injected programmatically. The
           entire UI, the mapping flow and the exporters work against this, so
           a profile can be built, reviewed and exported away from the rig.

All three normalise to one event shape:

    {"t": float, "status": "note_on"|"note_off"|"cc"|"pitch"|"other",
     "channel": int (1-based), "number": int, "value": int, "raw": str}

SPDX-License-Identifier: MIT
"""

import os
import queue
import re
import shutil
import struct
import subprocess
import tempfile
import threading
import time

# aseqdump prints a fixed-width table; these cover the message types a control
# surface actually emits. Channels are printed 0-based and normalised to 1-based.
_RE_NOTE = re.compile(
    r"Note\s+(on|off)\s+(\d+),\s*note\s+(\d+),\s*velocity\s+(\d+)", re.I)
_RE_CC = re.compile(
    r"Control\s+change\s+(\d+),\s*controller\s+(\d+),\s*value\s+(\d+)", re.I)
_RE_PITCH = re.compile(r"Pitch\s+bend\s+(\d+),\s*value\s+(-?\d+)", re.I)
_RE_PORT = re.compile(r"^\s*(\d+):(\d+)\s+(.*)$")


class MidiError(RuntimeError):
    pass


class Backend:
    name = "base"

    def __init__(self):
        self._q = queue.Queue()
        self._running = False
        self.status = "stopped"
        self.port = None

    # -- lifecycle -------------------------------------------------------

    def start(self):
        self._running = True
        self.status = "running"

    def stop(self):
        self._running = False
        self.status = "stopped"

    @property
    def running(self):
        return self._running

    # -- io --------------------------------------------------------------

    def emit(self, ev):
        self._q.put(ev)

    def drain(self, limit=512):
        out = []
        while len(out) < limit:
            try:
                out.append(self._q.get_nowait())
            except queue.Empty:
                break
        return out

    def send(self, status, channel, number, value):
        raise NotImplementedError

    @property
    def out_status(self):
        """Whether output is actually usable, reported separately from input.

        A controller can be perfectly readable while nothing you send reaches
        it, and conflating the two hides exactly the failure that matters
        during an LED pass.
        """
        return "output not described by this backend"

    # -- helpers ---------------------------------------------------------

    @staticmethod
    def event(status, channel, number, value, raw="", status_byte=None):
        """status_byte is the byte as it arrived.

        Worth keeping separately from the normalised status: a release sent as
        note-off (0x8n) and one sent as note-on with velocity zero (0x9n) mean
        the same thing to a human and completely different things to a mapping,
        which binds on the byte.
        """
        return {"t": time.time(), "status": status, "channel": channel,
                "number": number, "value": value, "raw": raw,
                "status_byte": status_byte}


# ---------------------------------------------------------------- offline

class OfflineBackend(Backend):
    """No hardware. Accepts injected messages and records what was sent."""

    name = "offline"

    def __init__(self):
        super().__init__()
        self.sent = []

    def start(self):
        super().start()
        self.status = "offline (no hardware)"

    def send(self, status, channel, number, value):
        self.sent.append(self.event(status, channel, number, value, raw="sent"))
        return True

    @property
    def out_status(self):
        return "offline: sends are recorded, not transmitted"

    def inject(self, status, channel, number, value):
        self.emit(self.event(status, channel, number, value, raw="injected"))


# ------------------------------------------------------------------- alsa

class AlsaBackend(Backend):
    """Linux ALSA sequencer via the aseqdump / aplaymidi / amidi trio."""

    name = "alsa"

    def __init__(self, port, sender="aplaymidi", rawmidi=None):
        super().__init__()
        self.port = port
        self.sender = sender
        self.rawmidi = rawmidi
        self._proc = None
        self._thread = None
        self._lock = threading.Lock()
        self.reconnects = 0

    # -- discovery -------------------------------------------------------

    @staticmethod
    def available():
        return shutil.which("aseqdump") is not None

    @staticmethod
    def ports():
        """List readable sequencer ports as [{'port': '128:0', 'name': ...}]."""
        if not shutil.which("aseqdump"):
            return []
        try:
            out = subprocess.run(["aseqdump", "-l"], capture_output=True,
                                 text=True, timeout=5).stdout
        except (OSError, subprocess.SubprocessError):
            return []
        ports = []
        for line in out.splitlines():
            m = _RE_PORT.match(line)
            if not m:
                continue
            name = m.group(3).strip()
            if not name or name.lower().startswith("port"):
                continue
            ports.append({"port": f"{m.group(1)}:{m.group(2)}", "name": name})
        return ports

    @classmethod
    def resolve(cls, hint):
        """Turn a name fragment into a concrete client:port, if it is present."""
        if not hint:
            return None
        if re.fullmatch(r"\d+:\d+", hint):
            return hint
        low = hint.lower()
        for p in cls.ports():
            if low in p["name"].lower():
                return p["port"]
        return None

    # -- reader ----------------------------------------------------------

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._read_loop, daemon=True,
                                        name="aseqdump-reader")
        self._thread.start()

    def stop(self):
        self._running = False
        with self._lock:
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
            self._proc = None
        self.status = "stopped"

    def _read_loop(self):
        """One long-lived aseqdump, re-established if the bridge restarts.

        The djm_midi service can restart and come back with a different ALSA
        client number, so a port resolved at startup goes stale. Re-resolving on
        every reconnect is what keeps a mapping session alive across that.
        """
        backoff = 0.5
        while self._running:
            port = self.resolve(self.port) or self.port
            try:
                with self._lock:
                    self._proc = subprocess.Popen(
                        ["aseqdump", "-p", str(port)],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, bufsize=1)
                self.status = f"connected to {port}"
                backoff = 0.5
                for line in self._proc.stdout:
                    if not self._running:
                        break
                    ev = self._parse(line)
                    if ev:
                        self.emit(ev)
            except (OSError, subprocess.SubprocessError) as exc:
                self.status = f"reader failed: {exc}"
            if not self._running:
                break
            self.reconnects += 1
            self.status = f"waiting for {self.port} (retry {self.reconnects})"
            time.sleep(backoff)
            backoff = min(backoff * 2, 5.0)

    @staticmethod
    def _parse(line):
        line = (line or "").rstrip()
        if not line:
            return None
        m = _RE_NOTE.search(line)
        if m:
            kind = "note_on" if m.group(1).lower() == "on" else "note_off"
            vel = int(m.group(4))
            if kind == "note_on" and vel == 0:
                kind = "note_off"
            return Backend.event(kind, int(m.group(2)) + 1, int(m.group(3)), vel, line)
        m = _RE_CC.search(line)
        if m:
            return Backend.event("cc", int(m.group(1)) + 1, int(m.group(2)),
                                 int(m.group(3)), line)
        m = _RE_PITCH.search(line)
        if m:
            return Backend.event("pitch", int(m.group(1)) + 1, 0, int(m.group(2)), line)
        return None

    # -- writer ----------------------------------------------------------

    @property
    def out_status(self):
        if self.sender == "amidi" and self.rawmidi:
            return f"out: amidi {self.rawmidi}"
        return f"out: aplaymidi {self.resolve(self.port) or self.port}"

    def send(self, status, channel, number, value):
        ch = max(0, min(15, int(channel) - 1))
        if status in ("note_on", "note_off"):
            sb = (0x90 if status == "note_on" else 0x80) | ch
        elif status == "cc":
            sb = 0xB0 | ch
        else:
            raise MidiError(f"cannot send status {status!r}")
        data = [sb, int(number) & 0x7F, int(value) & 0x7F]
        if self.sender == "amidi" and self.rawmidi:
            return self._send_amidi(data)
        return self._send_aplaymidi(data)

    def _send_amidi(self, data):
        hexs = " ".join(f"{b:02X}" for b in data)
        try:
            subprocess.run(["amidi", "-p", self.rawmidi, "-S", hexs],
                           capture_output=True, timeout=5, check=False)
            return True
        except (OSError, subprocess.SubprocessError) as exc:
            self.status = f"send failed: {exc}"
            return False

    def _send_aplaymidi(self, data):
        """Send one message by handing aplaymidi a one-event standard MIDI file.

        aplaymidi is file-driven, which looks like a poor fit for sending a
        single byte triple, but it is the only sequencer writer guaranteed
        present alongside aseqdump, and LED probing sends about one message a
        second. Correctness beats cleverness here.
        """
        port = self.resolve(self.port) or self.port
        blob = _smf([(0, data)])
        fd, path = tempfile.mkstemp(suffix=".mid", prefix="ms-")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(blob)
            subprocess.run(["aplaymidi", "-p", str(port), path],
                           capture_output=True, timeout=5, check=False)
            return True
        except (OSError, subprocess.SubprocessError) as exc:
            self.status = f"send failed: {exc}"
            return False
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass


def _varlen(n):
    out = bytearray([n & 0x7F])
    n >>= 7
    while n:
        out.insert(0, (n & 0x7F) | 0x80)
        n >>= 7
    return bytes(out)


def _smf(events, division=480):
    """Build a minimal type-0 SMF from [(delta_ticks, [status, d1, d2]), ...]."""
    track = bytearray()
    for delta, data in events:
        track += _varlen(delta) + bytes(data)
    track += _varlen(0) + b"\xff\x2f\x00"
    head = b"MThd" + struct.pack(">IHHH", 6, 0, 1, division)
    return head + b"MTrk" + struct.pack(">I", len(track)) + bytes(track)


# ----------------------------------------------------------------- rtmidi

class RtMidiBackend(Backend):
    """Cross-platform backend for hosts with python-rtmidi installed."""

    name = "rtmidi"

    def __init__(self, port):
        super().__init__()
        self.port = port
        self._in = None
        self._out = None
        self.in_name = None
        self.out_name = None
        self.out_error = None

    @staticmethod
    def _mod():
        try:
            import rtmidi  # noqa: F401  (optional dependency)
            return rtmidi
        except ImportError:
            return None

    @classmethod
    def available(cls):
        return cls._mod() is not None

    @classmethod
    def ports(cls):
        rtmidi = cls._mod()
        if rtmidi is None:
            return []
        try:
            names = rtmidi.MidiIn().get_ports()
        except Exception:
            return []
        return [{"port": str(i), "name": n} for i, n in enumerate(names)]

    def start(self):
        rtmidi = self._mod()
        if rtmidi is None:
            raise MidiError("python-rtmidi is not installed")
        self._in = rtmidi.MidiIn()
        names = self._in.get_ports()
        idx = self._match(names, self.port)
        if idx is None:
            raise MidiError(f"no input port matching {self.port!r}; have {names}")
        self._in.open_port(idx)
        self._in.set_callback(self._on_message)
        self.in_name = names[idx]

        # The output is resolved from the input port's NAME, never its index:
        # the two lists are numbered independently, so on Windows "Reloop Ready
        # In" is input 5 while output 5 is an unrelated virtual port.
        self._open_output()
        self._running = True
        self.status = f"connected to {names[idx]}"

    @staticmethod
    def _match(names, hint):
        hint = str(hint)
        if hint.isdigit() and int(hint) < len(names):
            return int(hint)
        low = hint.lower()
        for i, n in enumerate(names):
            if low in n.lower():
                return i
        return None

    @staticmethod
    def _core_name(name):
        """Strip a host's decoration from a port name.

        Windows gives '2- Reloop Ready In 5': a device-instance prefix, the
        direction, and the port index. What identifies the device is what is
        left after all three come off.
        """
        s = re.sub(r"^\s*\d+\s*-\s*", "", str(name))    # '2- ' instance prefix
        s = re.sub(r"\s+\d+\s*$", "", s)                # trailing port index
        s = re.sub(r"\b(in|out|input|output)\b", " ", s, flags=re.I)
        return re.sub(r"\s+", " ", s).strip()

    @classmethod
    def _match_output(cls, onames, in_name):
        core = cls._core_name(in_name)
        if core:
            for i, n in enumerate(onames):
                if core.lower() == cls._core_name(n).lower():
                    return i
            for i, n in enumerate(onames):
                if core.lower() in n.lower():
                    return i
        return None

    def stop(self):
        for p in (self._in, self._out):
            try:
                if p:
                    p.close_port()
            except Exception:
                pass
        self._in = self._out = None
        self._running = False
        self.status = "stopped"

    def _on_message(self, msg, _data=None):
        data, _dt = msg
        if len(data) < 2:
            return
        sb = data[0]
        kind, ch = sb & 0xF0, (sb & 0x0F) + 1
        if kind == 0x90:
            vel = data[2] if len(data) > 2 else 0
            self.emit(self.event("note_on" if vel else "note_off", ch, data[1],
                                 vel, status_byte=sb))
        elif kind == 0x80:
            self.emit(self.event("note_off", ch, data[1],
                                 data[2] if len(data) > 2 else 0, status_byte=sb))
        elif kind == 0xB0:
            self.emit(self.event("cc", ch, data[1],
                                 data[2] if len(data) > 2 else 0, status_byte=sb))
        elif kind == 0xE0:
            val = (data[2] << 7 | data[1]) if len(data) > 2 else 0
            self.emit(self.event("pitch", ch, 0, val))

    def send(self, status, channel, number, value):
        """Send, and only report success if the port was actually open.

        rtmidi will accept a message into a port that is no longer live and
        raise nothing, so returning True because send_message() did not throw
        says only that the call was made. That is how an entire LED session can
        report ok while nothing reaches the device.
        """
        ch = max(0, min(15, int(channel) - 1))
        sb = {"note_on": 0x90, "note_off": 0x80, "cc": 0xB0}.get(status)
        if sb is None:
            raise MidiError(f"cannot send status {status!r}")
        if not self._open_output():
            return False
        try:
            self._out.send_message([sb | ch, int(number) & 0x7F, int(value) & 0x7F])
        except Exception as exc:                      # noqa: BLE001
            self.out_error = f"send failed: {exc}"
            self._out = None
            return False
        self.out_error = None
        return True

    def _open_output(self):
        """Ensure an output port is open, re-opening if the device came back."""
        try:
            if self._out is not None and self._out.is_port_open():
                return True
        except Exception:                             # noqa: BLE001
            self._out = None
        rtmidi = self._mod()
        if rtmidi is None:
            self.out_error = "python-rtmidi is not installed"
            return False
        try:
            out = rtmidi.MidiOut()
            names = out.get_ports()
            idx = self._match_output(names, self.in_name or str(self.port))
            if idx is None:
                idx = self._match(names, self.port)
            if idx is None:
                self.out_error = f"no output port matching {self.port!r}"
                self._out = None
                return False
            out.open_port(idx)
            self._out = out
            self.out_name = names[idx]
            self.out_error = None
            return True
        except Exception as exc:                      # noqa: BLE001
            self.out_error = f"cannot open output: {exc}"
            self._out = None
            return False

    @property
    def out_status(self):
        if self.out_error:
            return self.out_error
        return f"out: {self.out_name}" if self.out_name else "no output port"


# ------------------------------------------------------------------ choose

def list_ports():
    out = []
    for cls in (AlsaBackend, RtMidiBackend):
        if cls.available():
            for p in cls.ports():
                out.append({"backend": cls.name, **p})
    return out


def open_backend(spec, port=None, rawmidi=None, sender="aplaymidi"):
    """spec is 'auto', 'alsa', 'rtmidi' or 'offline'."""
    if spec == "offline":
        return OfflineBackend()
    if spec in ("auto", "alsa") and AlsaBackend.available():
        if port or spec == "alsa":
            return AlsaBackend(port, sender=sender, rawmidi=rawmidi)
    if spec in ("auto", "rtmidi") and RtMidiBackend.available():
        if port or spec == "rtmidi":
            return RtMidiBackend(port)
    if spec == "auto":
        return OfflineBackend()
    raise MidiError(f"backend {spec!r} is not available on this host")
