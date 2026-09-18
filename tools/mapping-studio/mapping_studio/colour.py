"""RGB pad LEDs: how a colour becomes a MIDI value.

Plenty of controllers drive colour pads by packing the components into the
velocity byte of an ordinary note-on. There is no standard for it, but the
shape recurs: a few bits per channel, sometimes a brightness bit, all in the
seven bits a velocity has to spend.

The Reloop Ready turned out to be

    velocity = bright<<6 | R<<4 | G<<2 | B          R, G, B each 0..3

which was recovered by lighting pads and asking a human what colour they were.
Four levels per channel is 64 colours, and because it is arithmetic rather than
a lookup, any colour can be computed instead of discovered.

Storing the *encoding* rather than a scanned palette is the point: a table
would describe one controller, while an encoding describes a family. A device
using 3 bits per channel, or a different component order, is the same code with
different numbers.

SPDX-License-Identifier: MIT
"""

DEFAULT = {
    "encoding": "packed_rgb",
    "levels": 4,                 # values per channel: 0..levels-1
    "shift": {"r": 4, "g": 2, "b": 0},
    "bright_bit": 6,
}

# Named colours as fractions of full scale, so they survive a change of depth.
NAMED = {
    "off":     (0.0, 0.0, 0.0),
    "red":     (1.0, 0.0, 0.0),
    "orange":  (1.0, 1 / 3, 0.0),
    "amber":   (1.0, 2 / 3, 0.0),
    "yellow":  (1.0, 1.0, 0.0),
    "lime":    (2 / 3, 1.0, 0.0),
    "green":   (0.0, 1.0, 0.0),
    "mint":    (0.0, 1.0, 2 / 3),
    "cyan":    (0.0, 1.0, 1.0),
    "azure":   (0.0, 2 / 3, 1.0),
    "blue":    (0.0, 0.0, 1.0),
    "violet":  (1 / 3, 0.0, 1.0),
    "magenta": (1.0, 0.0, 1.0),
    "pink":    (1.0, 1 / 3, 2 / 3),
    "white":   (1.0, 1.0, 1.0),
}


class ColourError(ValueError):
    pass


def spec(profile_data=None):
    """The encoding for a profile, falling back to the common packing."""
    s = dict(DEFAULT)
    s.update((profile_data or {}).get("led") or {})
    return s


def quantise(value, levels):
    """Map 0.0-1.0 (or 0-255) onto the device's per-channel levels."""
    v = float(value)
    if v > 1.0:
        v = v / 255.0
    v = max(0.0, min(1.0, v))
    return int(round(v * (levels - 1)))


def encode(r, g, b, bright=True, led=None):
    """Components (0..1, or 0..255) -> the velocity byte to send."""
    s = spec_from(led)
    levels = int(s.get("levels", 4))
    sh = s.get("shift") or DEFAULT["shift"]
    val = (quantise(r, levels) << int(sh["r"])
           | quantise(g, levels) << int(sh["g"])
           | quantise(b, levels) << int(sh["b"]))
    bit = s.get("bright_bit")
    if bright and bit is not None:
        val |= 1 << int(bit)
    if not 0 <= val <= 127:
        raise ColourError(f"encoding produced {val}, which is not a velocity")
    return val


def decode(velocity, led=None):
    """The inverse: velocity -> (r, g, b, bright) with components 0..1."""
    s = spec_from(led)
    levels = int(s.get("levels", 4))
    sh = s.get("shift") or DEFAULT["shift"]
    mask = levels - 1
    v = int(velocity)
    bit = s.get("bright_bit")
    bright = bool(bit is not None and v & (1 << int(bit)))
    comp = {}
    for k in ("r", "g", "b"):
        comp[k] = ((v >> int(sh[k])) & mask) / float(mask)
    return comp["r"], comp["g"], comp["b"], bright


def named(name, bright=True, led=None):
    """Velocity for a named colour."""
    key = str(name).strip().lower()
    if key not in NAMED:
        raise ColourError(f"unknown colour {name!r}; have {sorted(NAMED)}")
    r, g, b = NAMED[key]
    return encode(r, g, b, bright=bright, led=led)


def hex_of(r, g, b):
    """A CSS colour for the UI, so a swatch matches roughly what the pad shows."""
    to = lambda v: max(0, min(255, int(round(float(v) * 255))))  # noqa: E731
    return f"#{to(r):02x}{to(g):02x}{to(b):02x}"


def palette(led=None, bright=True):
    """Every colour the device can show, as [{velocity, r, g, b, hex}]."""
    s = spec_from(led)
    levels = int(s.get("levels", 4))
    out = []
    span = levels - 1
    for r in range(levels):
        for g in range(levels):
            for b in range(levels):
                rr, gg, bb = r / span, g / span, b / span
                out.append({
                    "velocity": encode(rr, gg, bb, bright=bright, led=s),
                    "r": r, "g": g, "b": b,
                    "hex": hex_of(rr, gg, bb),
                })
    return out


def spec_from(led):
    if led is None:
        return dict(DEFAULT)
    if "led" in led:                      # a whole profile dict was passed
        return spec(led)
    s = dict(DEFAULT)
    s.update(led)
    return s


def describe(led=None):
    s = spec_from(led)
    sh = s.get("shift") or DEFAULT["shift"]
    bit = s.get("bright_bit")
    parts = [f"R<<{sh['r']}", f"G<<{sh['g']}", f"B<<{sh['b']}"]
    if bit is not None:
        parts.insert(0, f"bright<<{bit}")
    return (f"velocity = {' | '.join(parts)}, "
            f"each component 0..{int(s.get('levels', 4)) - 1}")
