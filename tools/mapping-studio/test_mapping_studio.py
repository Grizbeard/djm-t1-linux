"""Tests for mapping-studio.  Run: python3 -m unittest discover tools/mapping-studio

Stdlib only, like the tool itself. The cases here are the ones that actually
went wrong during development or that encode a hardware lesson from
docs/midi-map.md, not a uniform sweep of the API.

SPDX-License-Identifier: MIT
"""

import os
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mapping_studio import autodetect, export_mixxx, midi, svgpath  # noqa: E402
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
