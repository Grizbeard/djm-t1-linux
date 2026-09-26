// Runs a generated mapping script's page navigation against a mock of Mixxx's
// engine and checks every case of the behaviour table in pagenav.py.
//
//   node tools/pagenav_harness.js path/to/Mapping-scripts.js [--no-tabs]
//
// The mock models what the functions rely on: the skin's [Tab] triggers (one
// page at a time; setting a trigger clears the others), [Library]
// focused_widget, one-shot timers (run by flush()), and connections, which
// fire when a test "loads" a track. With --no-tabs the [Tab] controls do not
// exist, as with a skin that does not define them.
//
// Prints one line per check and exits non-zero on the first failure.

"use strict";
const fs = require("fs");

const path = process.argv[2];
const noTabs = process.argv.includes("--no-tabs");
const PAGES = ["decks", "library", "fx", "options"];

const values = {};
const writes = [];
const connections = [];
let timers = [];
let nextTimer = 1;

const key = (g, k) => g + "," + k;
const engine = {
    getValue(g, k) {
        if (g === "[Tab]" && noTabs) {
            return 0; // Mixxx logs a warning and returns 0 for a missing control
        }
        return values[key(g, k)] || 0;
    },
    setValue(g, k, v) {
        writes.push([g, k, v]);
        if (g === "[Tab]") {
            if (noTabs) {
                return;
            }
            if (v > 0) {
                PAGES.forEach((p) => { values[key(g, p)] = p === k ? 1 : 0; });
            }
            return;
        }
        values[key(g, k)] = v;
    },
    beginTimer(ms, fn, oneShot) {
        const id = nextTimer++;
        timers.push({ id, fn });
        return id;
    },
    stopTimer(id) { timers = timers.filter((t) => t.id !== id); },
    makeConnection(g, k, fn) {
        connections.push({ g, k, fn });
        return { disconnect() {} };
    },
    trigger() {},
    connectControl() {},
};
const midi = { sendShortMsg() {} };
const console_ = { log() {}, warn() {} };

const src = fs.readFileSync(path, "utf8");
const DJMT1 = new Function("engine", "midi", "console", src + "\nreturn DJMT1;")(
    engine, midi, console_);

function flush() {
    const due = timers;
    timers = [];
    due.forEach((t) => t.fn());
}
function loaded(group) {
    connections.filter((c) => c.g === group && c.k === "track_loaded")
        .forEach((c) => c.fn(1, group, "track_loaded"));
}
function page() {
    return PAGES.find((p) => values[key("[Tab]", p)] === 1) || "none";
}
function setPage(p) { engine.setValue("[Tab]", p, 1); }
function focus() { return engine.getValue("[Library]", "focused_widget"); }
function setFocus(f) { values[key("[Library]", "focused_widget")] = f; }
function wrote(g, k) { return writes.some((w) => w[0] === g && w[1] === k && w[2] > 0); }
function press(fn) { writes.length = 0; fn(0, 0, 0x7f, 0x90); }
function release(fn) { writes.length = 0; fn(0, 0, 0, 0x90); fn(0, 0, 0x40, 0x80); }

let n = 0;
function check(name, ok) {
    n++;
    console.log((ok ? "ok   " : "FAIL ") + name);
    if (!ok) {
        process.exit(1);
    }
}

DJMT1.initNav();
check("initNav watches both decks' track_loaded",
    connections.filter((c) => c.k === "track_loaded").length === 2);

if (noTabs) {
    press(DJMT1.browsePush);
    check("no tabs: push is GoToItem", wrote("[Library]", "GoToItem"));
    setFocus(3);
    press(DJMT1.browseShiftPush);
    check("no tabs: SHIFT+push toggles tracks -> tree", focus() === 2);
    press(DJMT1.browseShiftPush);
    check("no tabs: SHIFT+push toggles tree -> tracks", focus() === 3);
    press(DJMT1.loadA);
    check("no tabs: LOAD loads", wrote("[Channel1]", "LoadSelectedTrack"));
    writes.length = 0;
    loaded("[Channel1]");
    check("no tabs: a load changes no page", !writes.some((w) => w[0] === "[Tab]"));
    console.log(`${n} checks passed (no tabs)`);
    process.exit(0);
}

setPage("decks");
release(DJMT1.browsePush);
check("a release (note-on 0 or note-off) does nothing", page() === "decks" && writes.length === 0);

press(DJMT1.browsePush);
check("decks: push opens the library", page() === "library");
flush();
check("... on the track list", focus() === 3);

press(DJMT1.browsePush);
check("library, track list: push goes back to decks", page() === "decks");

setPage("library");
setFocus(2);
press(DJMT1.browsePush);
check("library, tree: push is GoToItem and stays", wrote("[Library]", "GoToItem") && page() === "library");

setFocus(5); // a dialog
press(DJMT1.browsePush);
check("library, dialog: push is GoToItem", wrote("[Library]", "GoToItem") && page() === "library");

setFocus(0);
press(DJMT1.browsePush);
check("library, nothing focused: push goes back to decks", page() === "decks");

setPage("fx");
press(DJMT1.browsePush);
check("fx page: push opens the library", page() === "library");
flush();

setPage("decks");
press(DJMT1.browseShiftPush);
check("decks: SHIFT+push opens the library", page() === "library");
flush();
check("... on the tree", focus() === 2);

press(DJMT1.browseShiftPush);
check("library: SHIFT+push swaps tree -> tracks", focus() === 3 && page() === "library");
press(DJMT1.browseShiftPush);
check("library: SHIFT+push swaps tracks -> tree", focus() === 2);

setFocus(3);
press(DJMT1.loadA);
check("library: LOAD A loads deck 1", wrote("[Channel1]", "LoadSelectedTrack"));
check("... and waits for the deck", page() === "library");
loaded("[Channel1]");
check("... then goes back to decks once it loaded", page() === "decks");

setPage("library");
press(DJMT1.loadB);
flush(); // the load window runs out: rejected, e.g. deck playing
check("rejected load: stays in the library", page() === "library");
loaded("[Channel2]"); // a later load from elsewhere
check("... and a later, unrelated load does not navigate", page() === "library");

setPage("library");
setFocus(2);
press(DJMT1.loadB);
loaded("[Channel2]");
check("load from the tree goes back to decks", page() === "decks");
press(DJMT1.browsePush);
flush();
check("... and push returns to the tree it left", page() === "library" && focus() === 2);

setPage("decks");
press(DJMT1.loadA);
loaded("[Channel1]");
check("decks: LOAD loads and stays on decks", page() === "decks");

console.log(`${n} checks passed`);
