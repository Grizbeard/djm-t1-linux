"""Move between a skin's pages from the controller: browse knob and LOAD buttons.

A touchscreen appliance with the library on its own page needs a way there and
back that does not mean reaching for the screen. The profile's `page_nav` key
turns the browse push into that:

  * Off the library page, push opens it; SHIFT + push opens it on the tree.
  * On the library page, push goes back to the home page while the track list
    has focus. Anywhere else there - the tree, a dialog - push is GoToItem as
    before, so a folder still expands and a crate still opens.
  * SHIFT + push on the library page swaps focus between the tree and the track
    list, the old libraryFocus toggle.
  * A LOAD button loads, and once the deck has actually taken the track, goes
    back to the home page. A rejected load (by default Mixxx refuses one onto a
    playing deck) leaves you where you were, so it does not look like it worked.
  * Entering the library puts focus back where it was when you left.

Pages are selected through the skin's own trigger controls ([Tab],decks,
[Tab],library, ...), so this only does anything with a skin that defines them.
With any other skin none of them is set, and every function falls back to what
the controls did before: GoToItem, the focus toggle, a plain load.

"Actually taken" comes from `track_loaded`, which EngineBuffer force-sets to 1
on every successful load and never on a rejected one. A LOAD press opens a
window of `load_window_ms`; a load that lands inside it counts.

Profile keys (all but `loads` have defaults):

    "page_nav": {
      "tab_group": "[Tab]",
      "home": "decks",
      "library": "library",
      "pages": ["decks", "library", "fx", "options"],
      "push": "browsePush",
      "shift_push": "browseShiftPush",
      "loads": {"loadA": "[Channel1]", "loadB": "[Channel2]"},
      "focus_delay_ms": 60,
      "load_window_ms": 5000
    }

Bind the browse push, SHIFT + push and each LOAD button to these functions as
external script targets.

SPDX-License-Identifier: MIT
"""

import json

# [Library],focused_widget values (library_decl.h, FocusWidget).
FOCUS_NONE = 0
FOCUS_SIDEBAR = 2
FOCUS_TRACKS = 3


def spec(profile):
    s = profile.data.get("page_nav")
    if not s:
        return None
    return {
        "tab_group": s.get("tab_group", "[Tab]"),
        "home": s.get("home", "decks"),
        "library": s.get("library", "library"),
        "pages": s.get("pages", ["decks", "library", "fx", "options"]),
        "push": s.get("push", "browsePush"),
        "shift_push": s.get("shift_push", "browseShiftPush"),
        "loads": s.get("loads") or {},
        "focus_delay_ms": int(s.get("focus_delay_ms", 60)),
        "load_window_ms": int(s.get("load_window_ms", 5000)),
    }


def init_calls(profile, prefix):
    return [f"    {prefix}.initNav();"] if spec(profile) else []


def generate(profile, prefix):
    s = spec(profile)
    if not s:
        return []
    p = prefix
    nav = {
        "tabs": s["tab_group"],
        "home": s["home"],
        "library": s["library"],
        "pages": s["pages"],
        "focusDelay": s["focus_delay_ms"],
        "loadWindow": s["load_window_ms"],
    }
    out = [
        "// ---------------------------------------------------------------",
        "// Page navigation (profile \"page_nav\").",
        "//",
        "// Browse push opens the library page and takes you back; a LOAD that",
        "// the deck actually takes returns you to the home page. Pages are the",
        "// skin's [Tab] triggers; a skin without them gets the old behaviour.",
        "",
        f"{p}.NAV = {json.dumps(nav)};",
        f"{p}.navFocus = {FOCUS_TRACKS};   // library focus to restore on the way in",
        f"{p}.navPending = {{}};   // deck group -> timer, while its load is awaited",
        "",
        "// A press is a note-on with a non-zero value. A release is either a",
        "// note-on at zero or a real note-off, whose velocity can be anything.",
        f"{p}.navPressed = function (value, status) {{",
        "    return value > 0 && (status & 0xF0) !== 0x80;",
        "};",
        "",
        f"{p}.navHasTabs = function () {{",
        f"    for (var i = 0; i < {p}.NAV.pages.length; i++) {{",
        f"        if (engine.getValue({p}.NAV.tabs, {p}.NAV.pages[i]) > 0) {{",
        "            return true;",
        "        }",
        "    }",
        "    return false;",
        "};",
        "",
        f"{p}.navOnLibrary = function () {{",
        f"    return engine.getValue({p}.NAV.tabs, {p}.NAV.library) > 0;",
        "};",
        "",
        f"{p}.navShowHome = function () {{",
        f"    if ({p}.navOnLibrary()) {{",
        '        var f = engine.getValue("[Library]", "focused_widget");',
        f"        if (f === {FOCUS_SIDEBAR} || f === {FOCUS_TRACKS}) {{",
        f"            {p}.navFocus = f;",
        "        }",
        "    }",
        f"    engine.setValue({p}.NAV.tabs, {p}.NAV.home, 1);",
        "};",
        "",
        "// The page has to be showing before its widgets can take focus, and the",
        "// switch reaches the GUI thread asynchronously, so focus follows a beat",
        "// later.",
        f"{p}.navShowLibrary = function (focus) {{",
        f"    engine.setValue({p}.NAV.tabs, {p}.NAV.library, 1);",
        f"    engine.beginTimer({p}.NAV.focusDelay, function () {{",
        '        engine.setValue("[Library]", "focused_widget", focus);',
        "    }, true);",
        "};",
        "",
        f"{p}.{s['push']} = function (ch, ctrl, value, status) {{",
        f"    if (!{p}.navPressed(value, status)) {{",
        "        return;",
        "    }",
        f"    if (!{p}.navHasTabs()) {{",
        '        engine.setValue("[Library]", "GoToItem", 1);',
        "        return;",
        "    }",
        f"    if (!{p}.navOnLibrary()) {{",
        f"        {p}.navShowLibrary({p}.navFocus);",
        "        return;",
        "    }",
        "    // In the track list (or with nothing in the library focused, e.g.",
        "    // after a tap on the screen) push means done here. In the tree or a",
        "    // dialog it keeps meaning GoToItem: expand, open, confirm.",
        '    var f = engine.getValue("[Library]", "focused_widget");',
        f"    if (f === {FOCUS_TRACKS} || f === {FOCUS_NONE}) {{",
        f"        {p}.navShowHome();",
        "    } else {",
        '        engine.setValue("[Library]", "GoToItem", 1);',
        "    }",
        "};",
        "",
        f"{p}.{s['shift_push']} = function (ch, ctrl, value, status) {{",
        f"    if (!{p}.navPressed(value, status)) {{",
        "        return;",
        "    }",
        f"    if ({p}.navHasTabs() && !{p}.navOnLibrary()) {{",
        f"        {p}.navShowLibrary({FOCUS_SIDEBAR});",
        "        return;",
        "    }",
        '    var f = engine.getValue("[Library]", "focused_widget");',
        '    engine.setValue("[Library]", "focused_widget",',
        f"        f === {FOCUS_SIDEBAR} ? {FOCUS_TRACKS} : {FOCUS_SIDEBAR});",
        "};",
        "",
        f"{p}.navLoad = function (group, value, status) {{",
        f"    if (!{p}.navPressed(value, status)) {{",
        "        return;",
        "    }",
        f"    if ({p}.navPending[group] !== undefined) {{",
        f"        engine.stopTimer({p}.navPending[group]);",
        "    }",
        f"    {p}.navPending[group] = engine.beginTimer({p}.NAV.loadWindow, function () {{",
        f"        delete {p}.navPending[group];",
        "    }, true);",
        '    engine.setValue(group, "LoadSelectedTrack", 1);',
        "};",
        "",
        "// track_loaded is force-set to 1 on every successful load, the same",
        "// track again included, and never on a rejected one.",
        f"{p}.navTrackLoaded = function (value, group) {{",
        f"    if (value !== 1 || {p}.navPending[group] === undefined) {{",
        "        return;",
        "    }",
        f"    engine.stopTimer({p}.navPending[group]);",
        f"    delete {p}.navPending[group];",
        f"    if ({p}.navHasTabs() && {p}.navOnLibrary()) {{",
        f"        {p}.navShowHome();",
        "    }",
        "};",
        "",
    ]
    for fn, group in s["loads"].items():
        out += [
            f"{p}.{fn} = function (ch, ctrl, value, status) {{",
            f'    {p}.navLoad("{group}", value, status);',
            "};",
            "",
        ]
    out += [
        f"{p}.initNav = function () {{",
    ]
    for group in s["loads"].values():
        out.append(f'    engine.makeConnection("{group}", "track_loaded", {p}.navTrackLoaded);')
    out += [
        "};",
        "",
    ]
    return out
