// Runs a generated mapping script's library favorites (favorites.py) against a
// mock of Mixxx's engine, with a clock and timers the checks drive by hand.
//
//   node tools/favorites_harness.js path/to/Mapping-scripts.js
//
// The whole mapping is initialised. [Library] favorite controls are recorded
// rather than acted on; a test "recalls" by bumping favorite_recalls, as
// Mixxx does when it finds the item.
//
// Prints one line per check and exits non-zero on the first failure.

"use strict";
const fs = require("fs");

let clock = 1000;
const FakeDate = { now: () => clock };

const values = {};
const writes = [];
const connections = [];
const leds = {};
let timers = [];
let nextTimer = 1;
const key = (g, k) => g + "," + k;

function get(g, k) {
    const v = values[key(g, k)];
    if (v !== undefined) {
        return v;
    }
    return /^\[EffectRack1_EffectUnit\d\]$/.test(g) && k === "enabled" ? 1 : 0;
}
const engine = {
    getValue: get,
    setValue(g, k, v) {
        writes.push([g, k, v]);
        const changed = get(g, k) !== v;
        values[key(g, k)] = v;
        if (changed) {
            connections.filter((c) => c.g === g && c.k === k)
                .forEach((c) => c.fn(v, g, k));
        }
    },
    getParameter() { return 0; },
    setParameter() {},
    softTakeover() {},
    makeConnection(g, k, fn) {
        connections.push({ g, k, fn });
        return { disconnect() {}, trigger() {} };
    },
    beginTimer(ms, fn, oneShot) {
        const id = nextTimer++;
        timers.push({ id, ms, fn, oneShot: !!oneShot, due: clock + ms });
        return id;
    },
    stopTimer(id) { timers = timers.filter((t) => t.id !== id); },
    trigger() {},
    connectControl() {},
};
// Advance the clock, firing timers as they fall due.
function advance(ms) {
    const end = clock + ms;
    for (;;) {
        const due = timers.filter((t) => t.due <= end).sort((a, b) => a.due - b.due)[0];
        if (!due) {
            break;
        }
        clock = due.due;
        if (due.oneShot) {
            timers = timers.filter((t) => t !== due);
        } else {
            due.due += due.ms;
        }
        due.fn();
    }
    clock = end;
}
const ledLog = [];
const midi = {
    sendShortMsg(status, note, value) {
        if ((status & 0xF0) === 0x90) {
            leds[note] = value;
            ledLog.push([note, value]);
        }
    },
    sendSysexMsg() {},
};
const console_ = { log() {}, warn() {} };

const src = fs.readFileSync(process.argv[2], "utf8");
const DJMT1 = new Function("engine", "midi", "console", "Date", src + "\nreturn DJMT1;")(
    engine, midi, console_, FakeDate);

let checks = 0;
function check(what, ok) {
    checks++;
    console.log((ok ? "ok   " : "FAIL ") + what);
    if (!ok) {
        process.exit(1);
    }
}
const pulses = (k) => writes.filter((w) => w[0] === "[Library]" && w[1] === k && w[2] === 1).length;
const NOTE_ON = 0x90;
const NOTE_OFF = 0x80;
const press = (fn) => DJMT1[fn](0, 0, 127, NOTE_ON);
const release = (fn, status) => DJMT1[fn](0, 0, 0, status || NOTE_ON);

DJMT1.init("DJM-T1", false);
const F = DJMT1.FAVORITES;

check("six favorites, one second to store", F.slots.length === 6 && F.holdMs === 1000
    && F.slots.map((s) => s.slot).join() === "1,2,3,4,5,6");
check("every favorite has a lamp", F.slots.every((s) => s.led && s.led.midino > 0));

press("favorite1");
advance(200);
release("favorite1");
check("a tap recalls favorite 1", pulses("favorite_1_activate") === 1
    && pulses("favorite_1_store") === 0);
check("... and leaves no timer running", timers.length === 0);

press("favorite4");
advance(999);
release("favorite4");
check("just under a second is still a tap", pulses("favorite_4_activate") === 1
    && pulses("favorite_4_store") === 0);

const lamp = F.slots[1].led.midino;
const before = leds[lamp];
ledLog.length = 0;
press("favorite2");
advance(1000);
check("holding a second flashes the button's lamp",
    ledLog.some((l) => l[0] === lamp && l[1] === F.slots[1].led.on));
advance(1000);
check("... and gives the lamp back afterwards", leds[lamp] === before);
check("... and stores nothing while still held", pulses("favorite_2_store") === 0);
release("favorite2");
check("letting go after the hold stores favorite 2", pulses("favorite_2_store") === 1
    && pulses("favorite_2_activate") === 0);

press("favorite3");
advance(1500);
release("favorite3", NOTE_OFF);
check("a real note-off counts as the release too", pulses("favorite_3_store") === 1);

const n = writes.length;
release("favorite5");
check("a release with no press seen does nothing", writes.length === n);

press("favorite6");
advance(100);
press("favorite6");
advance(100);
release("favorite6");
check("a repeated press restarts the button, one recall", pulses("favorite_6_activate") === 1);

engine.setValue("[Tab]", "decks", 1);
engine.setValue("[Library]", "favorite_recalls", 1);
check("a recall that found its item shows the library page",
    get("[Tab]", "library") === 1);
advance(500);
check("... with the track list focused", get("[Library]", "focused_widget") === 3);

console.log(checks + " checks passed");
