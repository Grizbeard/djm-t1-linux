"""Tests for mapping-studio.  Run: python3 -m unittest discover tools/mapping-studio

Stdlib only, like the tool itself. The cases here are the ones that actually
went wrong during development or that encode a hardware lesson from
docs/midi-map.md, not a uniform sweep of the API.

SPDX-License-Identifier: MIT
"""

import os
import re
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mapping_studio import autodetect, colour, export_mixxx, midi, svgpath  # noqa: E402
from mapping_studio.profile import Profile, ProfileError            # noqa: E402
from mapping_studio.session import analyse                          # noqa: E402


def svg(body, w=100, h=100):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}mm" '
            f'height="{h}mm" viewBox="0 0 {w} {h}">{body}</svg>')


class TestSvgGeometry(unittest.TestCase):
    def test_circle_from_four_cubics_measures_true_diameter(self):
        # A circle drawn as four cubics has its knots on the cardinal points, so
        # the endpoint hull is the real bbox. Control points would inflate it.
        d = ("M50,42 C54.4,42 58,45.6 58,50 C58,54.4 54.4,58 50,58 "
             "C45.6,58 42,54.4 42,50 C42,45.6 45.6,42 50,42 Z")
        doc = svgpath.loads(svg(f'<path d="{d}"/>'))
        sp = doc.subpaths[0]
        self.assertEqual(sp.curves, 4)
        w, h = sp.size
        self.assertAlmostEqual(w, 16.0, places=2)
        self.assertAlmostEqual(h, 16.0, places=2)
        self.assertAlmostEqual(sp.center[0], 50.0, places=2)

    def test_primitive_elements_are_read(self):
        doc = svgpath.loads(svg(
            '<rect x="10" y="20" width="15" height="9"/>'
            '<circle cx="60" cy="30" r="8"/>'))
        self.assertEqual(len(doc.subpaths), 2)
        self.assertAlmostEqual(doc.subpaths[0].size[0], 15.0)
        self.assertAlmostEqual(doc.subpaths[1].size[0], 16.0)

    def test_group_transform_is_applied(self):
        doc = svgpath.loads(svg(
            '<g transform="translate(10,5)"><rect x="0" y="0" '
            'width="10" height="10"/></g>'))
        self.assertAlmostEqual(doc.subpaths[0].center[0], 15.0)
        self.assertAlmostEqual(doc.subpaths[0].center[1], 10.0)

    def test_relative_and_shorthand_commands(self):
        doc = svgpath.loads(svg('<path d="M10,10 h20 v10 h-20 z"/>'))
        sp = doc.subpaths[0]
        self.assertAlmostEqual(sp.size[0], 20.0)
        self.assertAlmostEqual(sp.size[1], 10.0)

    def test_text_is_returned_with_position(self):
        doc = svgpath.loads(svg('<text x="30" y="40">TRIM</text>'))
        self.assertEqual(doc.texts[0]["text"], "TRIM")
        self.assertAlmostEqual(doc.texts[0]["x"], 30.0)


class TestAutodetect(unittest.TestCase):
    """The detector's job is separating ~90 controls from ~3600 subpaths."""

    @staticmethod
    def knob(cx, cy, d):
        r = d / 2
        return (f'<path d="M{cx},{cy-r} C{cx+r*.55},{cy-r} {cx+r},{cy-r*.55} '
                f'{cx+r},{cy} C{cx+r},{cy+r*.55} {cx+r*.55},{cy+r} {cx},{cy+r} '
                f'C{cx-r*.55},{cy+r} {cx-r},{cy+r*.55} {cx-r},{cy} '
                f'C{cx-r},{cy-r*.55} {cx-r*.55},{cy-r} {cx},{cy-r} Z"/>')

    def test_concentric_outlines_collapse_to_one_control(self):
        # Panel art draws a knob as a cap plus a skirt; three rings is one knob.
        body = (self.knob(50, 50, 16.5) + self.knob(50, 50, 13.5)
                + self.knob(50, 50, 11.0))
        _panel, controls = autodetect.detect_from_string(svg(body))
        self.assertEqual(len(controls), 1)
        self.assertEqual(controls[0]["kind"], "knob")
        self.assertAlmostEqual(controls[0]["shape"]["d"], 16.5, places=1)

    def test_hairlines_and_glyph_sized_shapes_are_rejected(self):
        body = (self.knob(50, 50, 16.5)
                + '<path d="M5,5 L95,5 L95,5.3 L5,5.3 Z"/>'      # rule
                + '<path d="M20,80 L23,80 L23,83 L20,83 Z"/>')   # glyph-sized
        _panel, controls = autodetect.detect_from_string(svg(body))
        self.assertEqual(len(controls), 1)

    def test_a_label_names_the_control_beneath_it(self):
        body = self.knob(50, 50, 16.5) + '<text x="50" y="61">TRIM</text>'
        _panel, controls = autodetect.detect_from_string(svg(body))
        self.assertEqual(controls[0]["label"], "TRIM")
        self.assertEqual(controls[0]["id"], "trim")

    def test_declared_callout_boxes_are_removed(self):
        # A manual that numbers its diagram draws each number in a small box.
        # Those are the right size to look like buttons, and the number sits
        # dead centre in one, so naive matching names the box instead of the
        # control it points at.
        body = "".join(self.knob(30 + 40 * i, 50, 16.5) for i in range(6))
        body += "".join(f'<rect x="{25 + 40 * i}" y="{62}" width="8" height="7"/>'
                        for i in range(6))
        labels = [{"text": f"Control {i}", "x": 29 + 40 * i, "y": 65.5,
                   "number": i + 1} for i in range(6)]
        _p, controls = autodetect.detect_from_string(
            svg(body, w=280, h=100), labels=labels)
        self.assertEqual(len(controls), 6)
        self.assertTrue(all(c["kind"] == "knob" for c in controls), controls)

    def test_a_button_with_text_on_it_is_not_treated_as_a_callout(self):
        # The regression this guards: panel labels printed inside button
        # apertures made the detector delete 46 real controls.
        body = "".join(
            f'<path d="M{20 + 30 * i},45 h15 v9 h-15 z"/>' for i in range(6))
        labels = [{"text": "SYNC", "x": 27.5 + 30 * i, "y": 49.5}
                  for i in range(6)]
        _p, controls = autodetect.detect_from_string(
            svg(body, w=220, h=100), labels=labels)
        self.assertEqual(len(controls), 6)

    def test_everything_detected_is_marked_provisional(self):
        _panel, controls = autodetect.detect_from_string(
            svg(self.knob(50, 50, 16.5)))
        self.assertTrue(controls[0]["provisional"])
        self.assertLess(controls[0]["confidence"], 1.0)


class TestAnalyse(unittest.TestCase):
    """Each case here is a documented DJM-T1 behaviour."""

    @staticmethod
    def ev(status, number, value, channel=1):
        return {"t": 0.0, "status": status, "channel": channel,
                "number": number, "value": value, "raw": ""}

    def test_relative_encoder_is_not_mistaken_for_a_knob(self):
        # Browse encoder: CC 0x00, 0x01 = +1 and 0x7F = -1, never a sweep.
        events = [self.ev("cc", 0, 1) for _ in range(9)] + \
                 [self.ev("cc", 0, 127) for _ in range(5)]
        binding, _g, _m, notes = analyse(events)
        self.assertEqual(binding["mode"], "relative")
        self.assertEqual(binding["number"], 0)
        self.assertTrue(any("relative" in n for n in notes))

    def test_absolute_knob_records_span_and_resting_value(self):
        events = [self.ev("cc", 13, v) for v in range(0, 128, 4)]
        events.append(self.ev("cc", 13, 67))
        binding, _g, _m, _n = analyse(events, kind="knob")
        self.assertEqual(binding["mode"], "absolute")
        self.assertEqual(binding["min"], 0)
        self.assertEqual(binding["max"], 124)
        self.assertEqual(binding["resting"], 67)   # detent is not MIDI 64

    def test_crossfader_mirror_is_flagged_not_bound(self):
        # The real bug this prevents: CC 0x18 is the crossfader's mirror, and
        # binding it made the crossfader drag Mixxx's headphone mix.
        events = []
        for v in range(0, 128, 4):
            events.append(self.ev("cc", 0x17, v))
            events.append(self.ev("cc", 0x18, v))
        binding, _g, mirrors, notes = analyse(events)
        self.assertEqual(binding["number"], 0x17)
        self.assertEqual([m["number"] for m in mirrors], [0x18])
        self.assertTrue(any("mirror" in n for n in notes))

    def test_button_press_and_release_pair_is_recognised(self):
        events = [self.ev("note_on", 0x2F, 127), self.ev("note_off", 0x2F, 0)]
        binding, _g, _m, notes = analyse(events)
        self.assertEqual(binding["mode"], "button")
        self.assertEqual(binding["press_value"], 127)
        self.assertTrue(any("press edge" in n for n in notes))

    def test_nothing_captured_is_reported_rather_than_guessed(self):
        binding, _g, _m, notes = analyse([])
        self.assertIsNone(binding)
        self.assertTrue(notes)

    def test_partial_sweep_is_called_out(self):
        events = [self.ev("cc", 13, v) for v in range(60, 70)]
        _b, _g, _m, notes = analyse(events, kind="knob")
        self.assertTrue(any("sweep the full" in n for n in notes))


class TestProfile(unittest.TestCase):
    def make(self):
        p = Profile.new("t", "Test", {"w": 100, "h": 100})
        p.add_control({"id": "a", "label": "A", "kind": "knob",
                       "shape": {"type": "circle", "cx": 10, "cy": 10, "d": 16}})
        p.add_control({"id": "b", "label": "B", "kind": "button",
                       "shape": {"type": "rect", "cx": 30, "cy": 10,
                                 "w": 15, "h": 9}})
        return p

    def test_duplicate_ids_get_suffixed_not_silently_merged(self):
        p = self.make()
        c = p.add_control({"id": "a", "kind": "knob",
                           "shape": {"type": "circle", "cx": 1, "cy": 1, "d": 5}})
        self.assertEqual(c["id"], "a_2")

    def test_collision_between_two_controls_is_reported(self):
        p = self.make()
        b = {"status": "cc", "channel": 1, "number": 13}
        p.set_binding("a", "base", "input", dict(b))
        p.set_binding("b", "base", "input", dict(b))
        self.assertEqual(len(p.collisions()), 1)

    def test_same_number_on_different_status_is_not_a_collision(self):
        # The mixer reuses low numbers across types: CC 0x0D and note 0x0D are
        # different controls.
        p = self.make()
        p.set_binding("a", "base", "input",
                      {"status": "cc", "channel": 1, "number": 13})
        p.set_binding("b", "base", "input",
                      {"status": "note", "channel": 1, "number": 13})
        self.assertEqual(p.collisions(), {})

    def test_findings_are_not_addresses_and_cannot_collide(self):
        # 'silent' and 'local' record that there is no address, so any number
        # of controls can carry them. Treating them as addresses reported every
        # analogue knob on a mixer as clashing with every other one.
        p = self.make()
        p.set_binding("a", "base", "input", {"status": "silent"})
        p.set_binding("b", "base", "input", {"status": "silent"})
        p.set_binding("a", "base", "output", {"status": "local"})
        p.set_binding("b", "base", "output", {"status": "local"})
        self.assertEqual(p.collisions(), {})
        self.assertEqual(p.output_collisions(), {})

    def test_editing_a_control_clears_its_provisional_flag(self):
        p = self.make()
        p.update_control("a", {"provisional": True, "confidence": 0.5})
        p.update_control("a", {"label": "Renamed"})
        self.assertNotIn("provisional", p.get("a"))

    def test_rename_rejects_an_id_already_in_use(self):
        p = self.make()
        with self.assertRaises(ProfileError):
            p.rename_control("a", "b")

    def test_validate_rejects_an_unknown_kind(self):
        p = self.make()
        p.get("a")["kind"] = "nonsense"
        with self.assertRaises(ProfileError):
            p.validate()


class TestExport(unittest.TestCase):
    def make(self):
        p = Profile.new("t", "Test Device", {"w": 100, "h": 100})
        p.add_control({"id": "fader", "label": "CH1 VOLUME", "kind": "fader",
                       "shape": {"type": "rect", "cx": 10, "cy": 10,
                                 "w": 6, "h": 50},
                       "target": {"group": "[Channel1]", "key": "volume"}})
        p.set_binding("fader", "base", "input",
                      {"status": "cc", "channel": 1, "number": 0x15,
                       "mode": "absolute", "min": 0, "max": 127, "resting": 0})
        return p

    def test_output_is_well_formed_and_carries_the_binding(self):
        p = self.make()
        xml, _js, _fn = export_mixxx.export(p)
        root = ET.fromstring(xml)
        ctl = root.find(".//controls/control")
        self.assertEqual(ctl.findtext("group"), "[Channel1]")
        self.assertEqual(ctl.findtext("key"), "volume")
        self.assertEqual(ctl.findtext("status"), "0xB0")
        self.assertEqual(ctl.findtext("midino"), "0x15")

    def test_prose_notes_cannot_break_the_xml_comment_block(self):
        # A capture note reading '... -- likely a mirror' is illegal inside an
        # XML comment and made Mixxx refuse the whole file.
        p = self.make()
        p.add_control({"id": "x", "label": "Odd -- control--", "kind": "button",
                       "shape": {"type": "rect", "cx": 5, "cy": 5, "w": 9, "h": 9}})
        p.set_binding("x", "base", "input",
                      {"status": "note", "channel": 1, "number": 9})
        xml, _js, _fn = export_mixxx.export(p)
        ET.fromstring(xml)
        self.assertNotIn("--&", xml)

    def test_relative_binding_exports_as_selectknob(self):
        p = self.make()
        p.set_binding("fader", "base", "input",
                      {"status": "cc", "channel": 1, "number": 0,
                       "mode": "relative"})
        xml, _js, _fn = export_mixxx.export(p)
        self.assertIn("<selectknob/>", xml)

    def test_a_silent_control_is_recorded_not_dropped(self):
        p = self.make()
        p.add_control({"id": "analog", "label": "MASTER LEVEL", "kind": "knob",
                       "shape": {"type": "circle", "cx": 5, "cy": 5, "d": 16}})
        p.set_binding("analog", "base", "input", {"status": "silent"})
        xml, _js, _fn = export_mixxx.export(p)
        self.assertIn("MASTER LEVEL", xml)
        self.assertIn("sends no MIDI", xml)

    def test_firmware_driven_led_is_recorded_not_exported(self):
        # The Reloop Ready's MODE buttons are lit permanently by the device and
        # brighten on press; no note will ever drive them. Saying so has to
        # survive into the mapping, or the absence looks like unfinished work.
        p = self.make()
        p.add_control({"id": "mode", "label": "MODE A", "kind": "button",
                       "shape": {"type": "rect", "cx": 5, "cy": 5, "w": 9, "h": 9},
                       "target": {"group": "[Channel1]", "key": "pfl"}})
        p.set_binding("mode", "base", "output", {"status": "local"})
        xml, _js, _fn = export_mixxx.export(p)
        ET.fromstring(xml)
        self.assertIn("firmware", xml)
        self.assertEqual(len(ET.fromstring(xml).findall(".//outputs/output")), 0)

    def test_two_controls_claiming_one_led_note_is_reported(self):
        p = self.make()
        p.add_control({"id": "a2", "label": "A2", "kind": "button",
                       "shape": {"type": "rect", "cx": 5, "cy": 5, "w": 9, "h": 9}})
        out = {"status": "note", "channel": 2, "number": 13}
        p.set_binding("fader", "base", "output", dict(out))
        p.set_binding("a2", "base", "output", dict(out))
        self.assertEqual(len(p.output_collisions()), 1)
        self.assertEqual(p.collisions(), {})   # inputs are unaffected

    def test_captured_but_unassigned_control_is_noted(self):
        p = self.make()
        p.add_control({"id": "u", "label": "UNASSIGNED", "kind": "button",
                       "shape": {"type": "rect", "cx": 5, "cy": 5, "w": 9, "h": 9}})
        p.set_binding("u", "base", "input",
                      {"status": "note", "channel": 1, "number": 42})
        xml, _js, _fn = export_mixxx.export(p)
        self.assertIn("no Mixxx control chosen yet", xml)

    def test_toggle_button_generates_a_script_binding(self):
        p = self.make()
        p.add_control({"id": "cue", "label": "CH1 CUE", "kind": "button",
                       "shape": {"type": "rect", "cx": 5, "cy": 5, "w": 9, "h": 9},
                       "target": {"group": "[Channel1]", "key": "pfl",
                                  "toggle": True}})
        p.set_binding("cue", "base", "input",
                      {"status": "note", "channel": 1, "number": 0x2F,
                       "mode": "button", "press_value": 127})
        xml, js, _fn = export_mixxx.export(p)
        self.assertIn("<script-binding/>", xml)
        self.assertIn("engine.getValue(\"[Channel1]\", \"pfl\") ? 0 : 1", js)


class TestColour(unittest.TestCase):
    """Pinned against colours actually observed on a Reloop Ready."""

    # Velocity -> what the panel showed, read off the hardware.
    OBSERVED = [
        (64, 0, 0, 0, "off"),
        (68, 0, 1, 0, "dim green"),
        (76, 0, 3, 0, "green"),
        (80, 1, 0, 0, "dim red"),
        (88, 1, 2, 0, "lime"),
        (100, 2, 1, 0, "yellow-orange"),
        (104, 2, 2, 0, "yellow"),
        (112, 3, 0, 0, "bright red"),
        (124, 3, 3, 0, "yellow"),
        (127, 3, 3, 3, "white"),
    ]

    def test_encoding_reproduces_observed_velocities(self):
        for vel, r, g, b, seen in self.OBSERVED:
            got = colour.encode(r / 3, g / 3, b / 3, bright=True)
            self.assertEqual(got, vel, f"{seen}: expected {vel}, got {got}")

    def test_decode_round_trips(self):
        for vel, r, g, b, _seen in self.OBSERVED:
            dr, dg, db, bright = colour.decode(vel)
            self.assertTrue(bright)
            self.assertEqual(
                [round(dr * 3), round(dg * 3), round(db * 3)], [r, g, b])

    def test_low_range_explains_the_early_readings(self):
        # Before the encoding was understood these looked like an unordered
        # palette. They are just the same packing with the brightness bit clear.
        self.assertEqual(colour.named("blue", bright=False), 3)
        self.assertEqual(colour.named("pink", bright=False), 54)   # seen as pink
        self.assertEqual(colour.named("white", bright=False), 63)

    def test_brightness_bit_does_not_change_hue(self):
        for name in ("red", "green", "blue", "magenta"):
            hi = colour.named(name, bright=True)
            lo = colour.named(name, bright=False)
            self.assertEqual(hi - lo, 64)
            self.assertEqual(colour.decode(hi)[:3], colour.decode(lo)[:3])

    def test_palette_covers_every_colour_exactly_once(self):
        p = colour.palette()
        self.assertEqual(len(p), 4 ** 3)
        self.assertEqual(len({x["velocity"] for x in p}), 64)

    def test_encoding_is_not_hardcoded_to_this_device(self):
        # A device with the components in a different order, and no brightness
        # bit, is the same code with different numbers. That is the point of
        # storing the encoding rather than a scanned table.
        led = {"levels": 4, "shift": {"r": 0, "g": 2, "b": 4}, "bright_bit": None}
        self.assertEqual(colour.encode(1.0, 0, 0, led=led), 3)
        self.assertEqual(colour.encode(0, 1.0, 0, led=led), 3 << 2)
        self.assertEqual(colour.encode(0, 0, 1.0, led=led), 3 << 4)
        self.assertEqual(len(colour.palette(led)), 4 ** 3)

    def test_an_encoding_too_wide_for_a_velocity_is_refused(self):
        # Three bits per channel is nine bits and cannot fit in the seven a
        # velocity has. Better to fail loudly than to emit a truncated colour.
        led = {"levels": 8, "shift": {"r": 0, "g": 3, "b": 6}, "bright_bit": None}
        with self.assertRaises(colour.ColourError):
            colour.encode(0, 0, 1.0, led=led)

    def test_unknown_colour_name_is_refused(self):
        with self.assertRaises(colour.ColourError):
            colour.named("burnt sienna")


class TestColourExport(unittest.TestCase):
    def make(self):
        p = Profile.new("t", "Pad Device", {"w": 100, "h": 100})
        p.data["led"] = dict(colour.DEFAULT)
        p.add_control({"id": "pad_1", "label": "PAD 1", "kind": "pad",
                       "shape": {"type": "rect", "cx": 10, "cy": 10,
                                 "w": 20, "h": 20}})
        p.set_binding("pad_1", "base", "output",
                      {"status": "note", "channel": 5, "number": 20})
        return p

    def test_colour_helper_is_emitted_and_declared(self):
        p = self.make()
        xml, js, _fn = export_mixxx.export(p)
        self.assertIn("setPadColour", js)
        self.assertIn("midi.sendShortMsg", js)
        # Mixxx will not load the script unless the mapping declares it, even
        # though nothing here is script-bound.
        self.assertIn("<scriptfiles>", xml)

    def test_helper_matches_the_profile_encoding(self):
        p = self.make()
        p.data["led"] = {"levels": 4, "shift": {"r": 0, "g": 2, "b": 4},
                         "bright_bit": None}
        _xml, js, _fn = export_mixxx.export(p)
        self.assertIn("(r << 0) | (g << 2) | (b << 4)", js)
        self.assertNotIn("1 << 6", js)

    def test_fixed_colour_control_gets_no_picker_or_helper_entry(self):
        p = self.make()
        p.add_control({"id": "play", "label": "PLAY", "kind": "button",
                       "rgb": False, "fixed_colour": "green",
                       "shape": {"type": "rect", "cx": 5, "cy": 5, "w": 9, "h": 9}})
        p.set_binding("play", "base", "output",
                      {"status": "note", "channel": 1, "number": 0})
        _xml, js, _fn = export_mixxx.export(p)
        self.assertNotIn("play:", js)


class TestMidi(unittest.TestCase):
    def test_aseqdump_note_and_cc_lines_are_parsed(self):
        ev = midi.AlsaBackend._parse(
            "128:0   Note on                 0, note 47, velocity 127")
        self.assertEqual((ev["status"], ev["number"], ev["value"]),
                         ("note_on", 47, 127))
        self.assertEqual(ev["channel"], 1)       # aseqdump prints 0-based
        ev = midi.AlsaBackend._parse(
            "128:0   Control change          0, controller 13, value 64")
        self.assertEqual((ev["status"], ev["number"], ev["value"]),
                         ("cc", 13, 64))

    def test_note_on_with_zero_velocity_is_a_release(self):
        ev = midi.AlsaBackend._parse(
            "128:0   Note on                 0, note 47, velocity 0")
        self.assertEqual(ev["status"], "note_off")

    def test_noise_lines_are_ignored(self):
        self.assertIsNone(midi.AlsaBackend._parse("Waiting for data."))
        self.assertIsNone(midi.AlsaBackend._parse(""))

    def test_generated_smf_has_a_valid_header_and_end_of_track(self):
        blob = midi._smf([(0, [0x90, 0x2F, 0x7F])])
        self.assertTrue(blob.startswith(b"MThd"))
        self.assertIn(b"MTrk", blob)
        self.assertTrue(blob.endswith(b"\xff\x2f\x00"))

    def test_offline_backend_round_trips(self):
        b = midi.OfflineBackend()
        b.start()
        b.inject("cc", 1, 13, 64)
        events = b.drain()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["number"], 13)
        b.send("note_on", 1, 47, 127)
        self.assertEqual(b.sent[0]["number"], 47)


class TestShippedProfile(unittest.TestCase):
    """The DJM-T1 profile is committed, so it should stay loadable and sane."""

    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "profiles", "pioneer-djm-t1.json")

    @unittest.skipUnless(os.path.exists(path), "profile not present")
    def test_profile_loads_validates_and_exports(self):
        p = Profile.load(self.path)
        self.assertTrue(p.validate())
        self.assertEqual(p.collisions(), {})
        xml, _js, _fn = export_mixxx.export(p)
        ET.fromstring(xml)

    @unittest.skipUnless(os.path.exists(path), "profile not present")
    def test_seeded_bindings_are_marked_unverified(self):
        # They came from a document, not from this tool watching the hardware.
        p = Profile.load(self.path)
        seeded = [c for c in p.controls
                  if (c.get("bindings", {}).get("base", {}) or {}).get("input")]
        self.assertTrue(seeded)
        for c in seeded:
            inp = c["bindings"]["base"]["input"]
            self.assertFalse(inp.get("verified", False), c["id"])


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestDetentGuard(unittest.TestCase):
    """A partial sweep must not become a centre-remap script."""

    def make(self, lo, hi, rest):
        p = Profile.new("t", "T", {"w": 10, "h": 10})
        p.add_control({"id": "pitch", "label": "PITCH", "kind": "fader",
                       "detent": True,
                       "shape": {"type": "rect", "cx": 5, "cy": 5, "w": 4, "h": 8},
                       "target": {"group": "[Channel1]", "key": "rate"}})
        p.set_binding("pitch", "base", "input",
                      {"status": "cc", "channel": 1, "number": 9,
                       "mode": "absolute", "min": lo, "max": hi, "resting": rest})
        return p

    def test_full_sweep_with_offset_centre_is_remapped(self):
        xml, js, _ = export_mixxx.export(self.make(0, 127, 62))
        self.assertIn("<script-binding/>", xml)
        self.assertIn("var centre = 62;", js)

    def test_partial_sweep_is_not_remapped_and_says_why(self):
        # The real case: a pitch fader captured over 0..7 would have produced a
        # curve that was wrong across its whole travel.
        xml, js, _ = export_mixxx.export(self.make(0, 7, 0))
        self.assertNotIn("var centre", js)
        self.assertIn("too partial", xml)
        self.assertIn("<normal/>", xml)

    def test_centre_at_an_extreme_is_rejected(self):
        xml, _js, _ = export_mixxx.export(self.make(0, 127, 127))
        self.assertIn("too partial", xml)


class TestFourteenBit(unittest.TestCase):
    """A high-resolution fader sends two CCs; binding one is not enough."""

    @staticmethod
    def sweep():
        # Exactly what a Reloop Ready pitch fader emits: coarse on CC 9, fine on
        # CC 63, interleaved, the fine byte wrapping as the coarse one steps.
        events = []
        for value in range(0, 1024, 3):
            msb, lsb = divmod(value, 128)
            events.append({"t": 0.0, "status": "cc", "channel": 1,
                           "number": 9, "value": msb, "raw": ""})
            events.append({"t": 0.0, "status": "cc", "channel": 1,
                           "number": 63, "value": lsb, "raw": ""})
        return events

    def test_pair_is_recognised_not_called_a_mirror(self):
        binding, _g, mirrors, notes = analyse(self.sweep(), kind="fader")
        self.assertEqual(binding["mode"], "14bit")
        self.assertEqual(binding["number"], 9)      # coarse
        self.assertEqual(binding["lsb"], 63)        # fine
        self.assertEqual(mirrors, [])
        self.assertTrue(any("14-bit" in n for n in notes))

    def test_span_is_reported_in_14_bit_terms(self):
        binding, _g, _m, _n = analyse(self.sweep(), kind="fader")
        self.assertGreater(binding["max"], 1000)

    def test_lsb_is_not_assumed_to_be_msb_plus_32(self):
        # The conventional pairing is CC n with CC n+32. This device uses 9/63,
        # so the detector has to work from behaviour.
        binding, _g, _m, _n = analyse(self.sweep())
        self.assertNotEqual(binding["lsb"], binding["number"] + 32)

    @staticmethod
    def profile_with(span, invert=False):
        p = Profile.new("t", "T", {"w": 10, "h": 10})
        target = {"group": "[Channel1]", "key": "rate"}
        if invert:
            target["invert"] = True
        p.add_control({"id": "pitch", "label": "PITCH", "kind": "fader",
                       "shape": {"type": "rect", "cx": 5, "cy": 5, "w": 4, "h": 8},
                       "target": target})
        p.set_binding("pitch", "base", "input",
                      {"status": "cc", "channel": 1, "number": 9, "lsb": 63,
                       "mode": "14bit", "min": 0, "max": span,
                       "resting": span // 2})
        return p

    def test_full_range_pair_uses_mixxx_native_pairing(self):
        xml, _js, _fn = export_mixxx.export(self.profile_with(16383))
        entries = ET.fromstring(xml).findall(".//controls/control")
        self.assertEqual(len(entries), 2)
        self.assertEqual({e.findtext("midino") for e in entries}, {"0x09", "0x3F"})
        self.assertIn("<fourteen-bit-msb/>", xml)
        self.assertIn("<fourteen-bit-lsb/>", xml)
        self.assertEqual({e.findtext("key") for e in entries}, {"rate"})

    def test_partial_range_pair_is_scaled_in_script(self):
        # Mixxx's pairing assumes the whole 0..16383 range. A fader that only
        # travels 1024 steps would otherwise land in a sliver at one end --
        # which is exactly how a pitch fader ended up covering +8.75 to +10.
        xml, js, _fn = export_mixxx.export(self.profile_with(1023))
        self.assertNotIn("fourteen-bit", xml)
        self.assertIn("T.pitch_msb", xml)
        self.assertIn("T.pitch_lsb", xml)
        self.assertIn("(s.msb << 7) | s.lsb", js)
        self.assertIn("raw / 1023", js)

    def test_inverted_fader_is_flipped_in_script(self):
        _xml, js, _fn = export_mixxx.export(self.profile_with(1023, invert=True))
        self.assertIn("pos = 1 - pos", js)


class TestSaveGuard(unittest.TestCase):
    """A studio must not silently discard an edit made to the file underneath it."""

    def setUp(self):
        import tempfile
        from mapping_studio import server as srv
        from mapping_studio.session import MappingSession
        self.srv = srv
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "p.json")
        p = Profile.new("t", "T", {"w": 10, "h": 10})
        p.add_control({"id": "a", "kind": "knob",
                       "shape": {"type": "circle", "cx": 5, "cy": 5, "d": 4}})
        p.save(self.path)
        self.studio = srv.Studio(Profile.load(self.path), self.path,
                                 MappingSession(p, midi.OfflineBackend()))

    def test_normal_save_works(self):
        self.assertEqual(self.studio.save(), self.path)

    def test_save_refuses_after_the_file_changed_underneath(self):
        import json as _json, time as _time
        _time.sleep(1.1)                       # move past the mtime tolerance
        d = _json.load(open(self.path, encoding="utf-8"))
        d["added_by_hand"] = True
        with open(self.path, "w", encoding="utf-8") as fh:
            _json.dump(d, fh)
        with self.assertRaises(ProfileError):
            self.studio.save()
        # the hand edit is still there
        self.assertIn("added_by_hand",
                      _json.load(open(self.path, encoding="utf-8")))

    def test_reload_takes_the_file_version(self):
        import json as _json, time as _time
        _time.sleep(1.1)
        d = _json.load(open(self.path, encoding="utf-8"))
        d["name"] = "Renamed On Disk"
        with open(self.path, "w", encoding="utf-8") as fh:
            _json.dump(d, fh)
        self.studio.reload()
        self.assertEqual(self.studio.profile.data["name"], "Renamed On Disk")
        self.assertEqual(self.studio.save(), self.path)   # no longer stale


class TestScriptIntegrity(unittest.TestCase):
    """Every script-binding in the XML must resolve to a function in the JS.

    This caught a real failure: pads were routed to a dispatcher that was not
    being emitted, so Mixxx would have loaded the mapping and then done nothing
    when a pad was pressed, with no error anywhere obvious.
    """

    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "profiles", "reloop-ready.json")

    @unittest.skipUnless(os.path.exists(path), "profile not present")
    def test_no_script_binding_dangles(self):
        p = Profile.load(self.path)
        xml, js, _fn = export_mixxx.export(p)
        root = ET.fromstring(xml)
        dangling = sorted({
            c.findtext("key") for c in root.findall(".//controls/control")
            if c.find("options/script-binding") is not None
            and (c.findtext("key") + " = function") not in js})
        self.assertEqual(dangling, [])

    @unittest.skipUnless(os.path.exists(path), "profile not present")
    def test_generated_script_is_balanced(self):
        # Not a parser, but an unbalanced brace means the file will not load at
        # all, and that is worth failing a build over.
        _xml, js, _fn = export_mixxx.export(Profile.load(self.path))
        code = re.sub(r"//.*", "", js)
        for open_ch, close_ch in (("{", "}"), ("(", ")"), ("[", "]")):
            self.assertEqual(code.count(open_ch), code.count(close_ch),
                             f"unbalanced {open_ch}{close_ch}")

    @unittest.skipUnless(os.path.exists(path), "profile not present")
    def test_pad_modes_reach_the_script(self):
        _xml, js, _fn = export_mixxx.export(Profile.load(self.path))
        for needed in ("MODE_SELECT", "PAD_ACTION", "paintPads", "connectPads"):
            self.assertIn(needed, js)


class TestPadRelease(unittest.TestCase):
    """Which pad actions must follow the release, and which must not."""

    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "profiles", "reloop-ready.json")

    def script(self):
        return export_mixxx.export(Profile.load(self.path))[1]

    @unittest.skipUnless(os.path.exists(path), "profile not present")
    def test_the_release_edge_reaches_the_dispatcher(self):
        # The bug this guards: the dispatcher returned early on value 0, so a
        # hot cue became a one-shot jump and a loop roll never ended.
        js = self.script()
        i = js.index("padPress = function")
        body = js[i:i + 500]
        self.assertNotIn("if (value === 0)", body)
        self.assertIn("value > 0", body)

    @unittest.skipUnless(os.path.exists(path), "profile not present")
    def test_hot_cue_and_loop_roll_are_gated(self):
        js = self.script()
        for mode in ("hotcue", "looproll"):
            m = re.search(mode + r": function \(group, pad, down, shifted\) \{"
                          r"(.*?)\n    \},", js, re.S)
            self.assertIsNotNone(m, mode)
            self.assertIn(".gate(", m.group(1), f"{mode} must follow the release")

    @unittest.skipUnless(os.path.exists(path), "profile not present")
    def test_latching_and_one_shot_modes_ignore_the_release(self):
        js = self.script()
        for mode in ("autoloop", "manualloop", "beatgrid"):
            m = re.search(mode + r": function \(group, pad, down, shifted\) \{"
                          r"(.*?)\n    \},", js, re.S)
            self.assertIsNotNone(m, mode)
            self.assertNotIn(".gate(", m.group(1),
                             f"{mode} latches; gating it would undo it instantly")


class TestJogs(unittest.TestCase):
    """A jog wheel is rim + platter + VINYL, and only works as a unit."""

    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "profiles", "reloop-ready.json")

    def script(self):
        return export_mixxx.export(Profile.load(self.path))[1]

    @unittest.skipUnless(os.path.exists(path), "profile not present")
    def test_rim_scratches_when_armed_and_nudges_otherwise(self):
        js = self.script()
        m = re.search(r"jogTurn_a = function.*?\n\};", js, re.S)
        self.assertIsNotNone(m)
        body = m.group(0)
        self.assertIn("engine.scratchTick(1,", body)
        self.assertIn('"jog"', body)

    @unittest.skipUnless(os.path.exists(path), "profile not present")
    def test_platter_does_nothing_until_vinyl_arms_it(self):
        js = self.script()
        m = re.search(r"jogTouch_a = function.*?\n\};", js, re.S)
        self.assertIn("vinylMode", m.group(0))
        self.assertIn("engine.scratchEnable(1,", m.group(0))
        self.assertIn("engine.scratchDisable(1,", m.group(0))

    @unittest.skipUnless(os.path.exists(path), "profile not present")
    def test_vinyl_drives_its_own_led(self):
        # Mixxx has no value for "the platter is armed", so the LED has to be
        # driven from the mapping's own state.
        js = self.script()
        m = re.search(r"setVinyl_a = function.*?\n\};", js, re.S)
        self.assertIn("midi.sendShortMsg", m.group(0))

    @unittest.skipUnless(os.path.exists(path), "profile not present")
    def test_relative_rim_is_decoded_as_signed(self):
        js = self.script()
        self.assertIn("(value < 64) ? value : value - 128", js)


class TestNoteRelease(unittest.TestCase):
    """A release can arrive as 0x8n or as 0x9n velocity 0; bind both."""

    def make(self):
        p = Profile.new("t", "T", {"w": 10, "h": 10})
        p.add_control({"id": "pad", "label": "PAD", "kind": "pad",
                       "shape": {"type": "rect", "cx": 5, "cy": 5, "w": 9, "h": 9},
                       "target": {"group": "[Channel1]", "key": "hotcue_1_activate"}})
        p.set_binding("pad", "base", "input",
                      {"status": "note", "channel": 1, "number": 20,
                       "mode": "button", "press_value": 127})
        return p

    def test_note_off_is_bound_alongside_note_on(self):
        # The bug: a mapping bound only to 0x9n never sees a real note-off, so
        # a held hot cue never returns and a touched platter never lets go.
        xml, _js, _fn = export_mixxx.export(self.make())
        entries = ET.fromstring(xml).findall(".//controls/control")
        statuses = {e.findtext("status") for e in entries}
        self.assertEqual(statuses, {"0x90", "0x80"})
        self.assertEqual({e.findtext("key") for e in entries},
                         {"hotcue_1_activate"})

    def test_cc_bindings_are_untouched(self):
        p = self.make()
        p.set_binding("pad", "base", "input",
                      {"status": "cc", "channel": 1, "number": 20,
                       "mode": "absolute", "min": 0, "max": 127, "resting": 0})
        xml, _js, _fn = export_mixxx.export(p)
        entries = ET.fromstring(xml).findall(".//controls/control")
        self.assertEqual(len(entries), 1)

    def test_a_profile_can_opt_out(self):
        p = self.make()
        p.data["midi"] = {"note_release": "single"}
        xml, _js, _fn = export_mixxx.export(p)
        self.assertEqual(len(ET.fromstring(xml).findall(".//controls/control")), 1)


class TestOutputValidity(unittest.TestCase):
    """An <output> must name a real MixxxControl, never a script function."""

    def make(self):
        p = Profile.new("t", "T", {"w": 10, "h": 10})
        p.add_control({"id": "vinyl", "label": "VINYL", "kind": "button",
                       "shape": {"type": "rect", "cx": 5, "cy": 5, "w": 9, "h": 9},
                       "target": {"group": "[Channel1]", "key": "T.vinyl",
                                  "script": "T.vinyl", "external": True}})
        p.set_binding("vinyl", "base", "input",
                      {"status": "note", "channel": 1, "number": 15,
                       "mode": "button", "press_value": 127})
        p.set_binding("vinyl", "base", "output",
                      {"status": "note", "channel": 1, "number": 15,
                       "on": 127, "off": 0})
        return p

    def test_a_script_keyed_control_gets_no_output_block(self):
        # Mixxx rejects the whole outputs section over one bad control name:
        # "MIDI output message 0x90 0x0F has invalid MixxxControl".
        xml, _js, _fn = export_mixxx.export(self.make())
        outs = ET.fromstring(xml).findall(".//outputs/output")
        self.assertEqual(outs, [])
        self.assertIn("driven by the mapping's own script", xml)

    def test_the_input_side_still_binds_to_the_script(self):
        xml, _js, _fn = export_mixxx.export(self.make())
        keys = {c.findtext("key")
                for c in ET.fromstring(xml).findall(".//controls/control")}
        self.assertIn("T.vinyl", keys)

    def test_an_explicit_output_key_is_honoured(self):
        p = self.make()
        t = p.target(p.get("vinyl"), "base")
        t["output_key"] = "keylock"
        xml, _js, _fn = export_mixxx.export(p)
        outs = ET.fromstring(xml).findall(".//outputs/output")
        self.assertEqual([o.findtext("key") for o in outs], ["keylock"])


class TestPadColourScheme(unittest.TestCase):
    """Colour carries two things: what a pad does, and whether it is engaged."""

    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "profiles", "reloop-ready.json")

    def script(self):
        return export_mixxx.export(Profile.load(self.path))[1]

    @unittest.skipUnless(os.path.exists(path), "profile not present")
    def test_pads_within_a_mode_are_not_all_one_colour(self):
        js = self.script()
        m = re.search(r"autoloop: \{(.*?)\n    \},", js, re.S)
        rgbs = re.findall(r"rgb: \[(\d), (\d), (\d)\]", m.group(1))
        self.assertEqual(len(rgbs), 8)
        self.assertGreater(len(set(rgbs)), 3,
                           "a mode should differentiate its pads by colour")

    @unittest.skipUnless(os.path.exists(path), "profile not present")
    def test_outer_and_inner_pads_of_a_row_differ(self):
        # Row 2 of Auto Loop: the outer pair moves the loop, the inner pair
        # resizes it. Different job, different hue.
        js = self.script()
        m = re.search(r"autoloop: \{(.*?)\n    \},", js, re.S)
        rgbs = re.findall(r"rgb: \[(\d), (\d), (\d)\]", m.group(1))
        outer, inner = rgbs[4], rgbs[5]
        self.assertEqual(outer, rgbs[7])      # pads 5 and 8 match
        self.assertEqual(inner, rgbs[6])      # pads 6 and 7 match
        self.assertNotEqual(outer, inner)

    @unittest.skipUnless(os.path.exists(path), "profile not present")
    def test_toggling_pads_carry_a_state_control(self):
        js = self.script()
        m = re.search(r"autoloop: \{(.*?)\n    \},", js, re.S)
        self.assertIn('state: "beatloop_1_enabled"', m.group(1))
        m = re.search(r"manualloop: \{(.*?)\n    \},", js, re.S)
        self.assertIn('state: "loop_enabled"', m.group(1))

    @unittest.skipUnless(os.path.exists(path), "profile not present")
    def test_state_dims_the_pad_until_engaged(self):
        js = self.script()
        m = re.search(r"paintPads = function.*?\n\};", js, re.S)
        self.assertIn("lit = engine.getValue(g, pad.state) > 0", m.group(0))

    @unittest.skipUnless(os.path.exists(path), "profile not present")
    def test_state_controls_are_connected_so_the_panel_follows_mixxx(self):
        js = self.script()
        m = re.search(r"connectPads = function.*?\n\};", js, re.S)
        for key in ("beatloop_1_enabled", "loop_enabled"):
            self.assertIn(key, m.group(0))
        self.assertIn("[Sampler", m.group(0))
