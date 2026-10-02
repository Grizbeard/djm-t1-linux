// Runs a generated mapping script's hot cue banks against a mock of Mixxx's
// engine and checks that the bank is published to, and follows, the skin's
// bank control (banks.py, `bank_control`).
//
//   node tools/bank_harness.js path/to/Mapping-scripts.js [--no-skin | --late-skin]
//
// The mock keeps control values, fires connections when a value changes, runs
// repeating timers one round per tick(), and records every write and every
// MIDI message. With --no-skin the [TerminalWide] controls never exist, as
// under a skin that does not declare them: getValue reads 0 and
// makeConnection returns undefined, as Mixxx does. With --late-skin they
// appear only after the mapping has started, as in a QOpenGL build of Mixxx,
// where the skin loads once the window is on screen.
//
// Prints one line per check and exits non-zero on the first failure.

"use strict";
const fs = require("fs");

const path = process.argv[2];
const noSkin = process.argv.includes("--no-skin");
const lateSkin = process.argv.includes("--late-skin");
const SKIN = "[TerminalWide]";
let skinLoaded = !noSkin && !lateSkin;

const values = {};
const writes = [];
const connections = [];
const leds = {};

const key = (g, k) => g + "," + k;
const missing = (g) => !skinLoaded && g === SKIN;
let timers = [];
let nextTimer = 1;
function tick() {
    timers.slice().forEach((tm) => {
        tm.fn();
        if (tm.oneShot) {
            timers = timers.filter((x) => x !== tm);
        }
    });
}
const engine = {
    getValue(g, k) {
        return missing(g) ? 0 : values[key(g, k)] || 0;
    },
    setValue(g, k, v) {
        writes.push([g, k, v]);
        if (missing(g)) {
            return;
        }
        const changed = (values[key(g, k)] || 0) !== v;
        values[key(g, k)] = v;
        if (changed) {
            connections.filter((c) => c.g === g && c.k === k)
                .forEach((c) => c.fn(v, g, k));
        }
    },
    makeConnection(g, k, fn) {
        if (missing(g)) {
            return undefined;
        }
        connections.push({ g, k, fn });
        return { disconnect() {} };
    },
    beginTimer(ms, fn, oneShot) {
        const id = nextTimer++;
        timers.push({ id, fn, oneShot: !!oneShot });
        return id;
    },
    stopTimer(id) { timers = timers.filter((tm) => tm.id !== id); },
    trigger() {},
    connectControl() {},
};
const midi = {
    sendShortMsg(status, note, value) { leds[note] = value; },
    sendSysexMsg() {},
};
const console_ = { log() {}, warn() {} };

const src = fs.readFileSync(path, "utf8");
const DJMT1 = new Function("engine", "midi", "console", src + "\nreturn DJMT1;")(
    engine, midi, console_);

let checks = 0;
function check(what, ok) {
    checks++;
    console.log((ok ? "ok   " : "FAIL ") + what);
    if (!ok) {
        process.exit(1);
    }
}
function wrote(g, k) {
    return writes.filter((w) => w[0] === g && w[1] === k);
}
function lastActivated(group) {
    const w = writes.filter((x) => x[0] === group && /^hotcue_\d+_activate$/.test(x[1]));
    return w.length ? w[w.length - 1][1] : null;
}

const A = DJMT1.BANKS[0];
const B = DJMT1.BANKS[1];
check("the profile names a bank control per deck",
    A.bankControl && A.bankControl[1] === "hotcue_bank_1"
    && B.bankControl && B.bankControl[1] === "hotcue_bank_2");

DJMT1.initBanks();

if (noSkin) {
    check("no skin control: nothing written to it at init",
        writes.every((w) => w[0] !== SKIN));
    DJMT1.toggleBank(0, 127);
    check("no skin control: ACTIVE still switches the pads to 5-8",
        (DJMT1.hotcuePress(0, 0, 127), lastActivated(A.group) === "hotcue_5_activate"));
    check("no skin control: nothing written on the toggle either",
        writes.every((w) => w[0] !== SKIN));
    check("no skin control: bank light on", leds[A.bankLed] === 0x7F);
    for (let n = 0; n < 40; n++) {
        tick();
    }
    check("no skin control: the retries give up", timers.length === 0);
    console.log(checks + " checks passed (no skin)");
    process.exit(0);
}

if (lateSkin) {
    check("skin not loaded yet: nothing published at init",
        writes.every((w) => w[0] !== SKIN) && timers.length === 2);
    DJMT1.toggleBank(0, 127);
    check("skin not loaded yet: ACTIVE A still moves the pads to 5-8",
        (DJMT1.hotcuePress(0, 0, 127), lastActivated(A.group) === "hotcue_5_activate"));
    tick();
    check("a retry before the skin loads changes nothing",
        writes.every((w) => w[0] !== SKIN) && timers.length === 2);
    skinLoaded = true;
    tick();
    check("once the skin loads, the next retry publishes the bank each deck is on",
        values[key(SKIN, "hotcue_bank_1")] === 1 && wrote(SKIN, "hotcue_bank_2").length === 1
        && values[key(SKIN, "hotcue_bank_2")] === 0);
    check("... and the retries stop", timers.length === 0);
    DJMT1.toggleBank(0, 127);
    check("... and ACTIVE A publishes from then on", values[key(SKIN, "hotcue_bank_1")] === 0);
    engine.setValue(SKIN, "hotcue_bank_2", 1);
    check("... and the mapping follows the control", DJMT1.bank[1] === 1);
    console.log(checks + " checks passed (late skin)");
    process.exit(0);
}

check("init publishes bank 0 for both decks",
    wrote(SKIN, "hotcue_bank_1").length === 1 && values[key(SKIN, "hotcue_bank_1")] === 0
    && wrote(SKIN, "hotcue_bank_2").length === 1 && values[key(SKIN, "hotcue_bank_2")] === 0);

DJMT1.toggleBank(0, 127);
check("ACTIVE A publishes cues 5-8", values[key(SKIN, "hotcue_bank_1")] === 1);
check("... and leaves deck B's alone", values[key(SKIN, "hotcue_bank_2")] === 0);
DJMT1.hotcuePress(0, 0, 127);
check("... and pad 1 fires hot cue 5", lastActivated(A.group) === "hotcue_5_activate");
check("... and the bank light is on", leds[A.bankLed] === 0x7F);

const before = writes.length;
DJMT1.toggleBank(0, 0);
check("the release does nothing", writes.length === before
    && values[key(SKIN, "hotcue_bank_1")] === 1);

DJMT1.toggleBank(0, 127);
check("a second press publishes cues 1-4 again", values[key(SKIN, "hotcue_bank_1")] === 0);
DJMT1.hotcuePress(0, 0, 127);
check("... and pad 1 fires hot cue 1", lastActivated(A.group) === "hotcue_1_activate");
check("... and the bank light is off", leds[A.bankLed] === 0x00);

engine.setValue(SKIN, "hotcue_bank_2", 1);
check("something else setting deck B's control moves its bank", DJMT1.bank[1] === 1);
DJMT1.hotcuePress(1, 0, 127);
check("... so pad 1 on B fires hot cue 5", lastActivated(B.group) === "hotcue_5_activate");
check("... and B's bank light follows", leds[B.bankLed] === 0x7F);

engine.setValue(SKIN, "hotcue_bank_2", 7);
check("an out-of-range value is ignored", DJMT1.bank[1] === 1);

// The pad's release reaches Mixxx (a paused deck plays the cue only while it
// is held), and goes to the cue the press started.
const G = A.group;
const activations = (n) => wrote(G, "hotcue_" + n + "_activate").map((w) => w[2]);
check("deck A is on cues 1-4", DJMT1.bank[0] === 0);
DJMT1.hotcueA2(0, 0x1F, 0x7F, 0x90);
check("pad 2 holds hot cue 2 down", activations(2).join() === "1");
DJMT1.toggleBank(0, 127);
DJMT1.hotcueA2(0, 0x1F, 0x00, 0x90);
check("the release lets go of hot cue 2, though the bank moved to 5-8",
    activations(2).join() === "1,0" && activations(6).length === 0);
DJMT1.hotcueA2(0, 0x1F, 0x7F, 0x90);
check("in bank 5-8 pad 2 holds hot cue 6", activations(6).join() === "1");
DJMT1.hotcueA2(0, 0x1F, 0x40, 0x80);
check("a note-off releases it, whatever its velocity",
    activations(6).join() === "1,0");
DJMT1.hotcueA2(0, 0x1F, 0x00, 0x90);
check("a second release sends nothing", activations(6).join() === "1,0");

console.log(checks + " checks passed");
