// Runs a generated mapping script's FX sections (fxsections.py) against a mock
// of Mixxx's engine and checks the behaviour the module promises.
//
//   node tools/fx_harness.js path/to/Mapping-scripts.js
//
// The mock keeps control values (effect units start enabled, as in Mixxx),
// fires connections when a value changes, and records parameter writes, soft
// takeover registrations and the last value sent to every LED. The whole
// mapping is initialised, not just the FX part, so the check also covers the
// startup routing and the order init runs things in.
//
// Prints one line per check and exits non-zero on the first failure.

"use strict";
const fs = require("fs");

const values = {};
const params = {};
const takeover = new Set();
const connections = [];
const leds = {};
const key = (g, k) => g + "," + k;

function get(g, k) {
    const v = values[key(g, k)];
    if (v !== undefined) {
        return v;
    }
    // Mixxx creates effect units switched on.
    return /^\[EffectRack1_EffectUnit\d\]$/.test(g) && k === "enabled" ? 1 : 0;
}
const engine = {
    getValue: get,
    setValue(g, k, v) {
        const changed = get(g, k) !== v;
        values[key(g, k)] = v;
        if (changed) {
            connections.filter((c) => c.g === g && c.k === k)
                .forEach((c) => c.fn(v, g, k));
        }
    },
    getParameter(g, k) { return params[key(g, k)] || 0; },
    setParameter(g, k, v) { params[key(g, k)] = v; },
    softTakeover(g, k, on) { if (on) { takeover.add(key(g, k)); } },
    makeConnection(g, k, fn) {
        connections.push({ g, k, fn });
        return { disconnect() {}, trigger() {} };
    },
    beginTimer() { return 1; },
    stopTimer() {},
    trigger() {},
    connectControl() {},
};
const midi = {
    sendShortMsg(status, note, value) {
        if ((status & 0xF0) === 0x90) {
            leds[note] = value;
        }
    },
    sendSysexMsg() {},
};
const console_ = { log() {}, warn() {} };

const src = fs.readFileSync(process.argv[2], "utf8");
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
const U = (n) => "[EffectRack1_EffectUnit" + n + "]";
const S = (n, j) => "[EffectRack1_EffectUnit" + n + "_Effect" + j + "]";
const on = (g) => get(g, "enabled") > 0;
const press = (fn) => { DJMT1[fn](0, 0, 127); DJMT1[fn](0, 0, 0); };
// LEDs, from the profile's table rather than hard-coded note numbers.
const F1 = DJMT1.FX_SECTIONS[0];
const F2 = DJMT1.FX_SECTIONS[1];
const lit = (led) => leds[led.midino] === led.on;

DJMT1.init("DJM-T1", false);

check("routing: units 1 and 2 on deck 1 only",
    get(U(1), "group_[Channel1]_enable") === 1 && get(U(1), "group_[Channel2]_enable") === 0
    && get(U(2), "group_[Channel1]_enable") === 1 && get(U(2), "group_[Channel2]_enable") === 0);
check("routing: units 3 and 4 on deck 2 only",
    get(U(3), "group_[Channel2]_enable") === 1 && get(U(3), "group_[Channel1]_enable") === 0
    && get(U(4), "group_[Channel2]_enable") === 1 && get(U(4), "group_[Channel1]_enable") === 0);
check("start: every unit keeps the on state Mixxx gave it",
    on(U(1)) && on(U(2)) && on(U(3)) && on(U(4)));
check("start: each deck's first ASSIGN lit, its second dark",
    lit(F1.selectLeds[0]) && !lit(F1.selectLeds[1])
    && lit(F2.selectLeds[0]) && !lit(F2.selectLeds[1]));
check("start: FX ON lights show the selected units on", lit(F1.onLed) && lit(F2.onLed));
const K = F1.knobKey;   // the unit control the DRY/WET knob turns
check("soft takeover on every unit's " + K + " and every slot's meta",
    [1, 2, 3, 4].every((n) => takeover.has(key(U(n), K))
        && [1, 2, 3].every((j) => takeover.has(key(S(n, j), "meta")))));

press("fx1On");
check("FX1 ON switches unit 1 off, and its light", !on(U(1)) && !lit(F1.onLed));
check("... and leaves unit 2 alone", on(U(2)));

DJMT1.fx1Mix(0, 0, 64);
DJMT1.fx1Level1(0, 0, 127);
check("knobs on unit 1: DRY/WET 64 is the middle, a level knob at 127 the top",
    params[key(U(1), K)] === 0.5 && params[key(S(1, 1), "meta")] === 1);

press("fx1Select2");
check("deck A's second ASSIGN: the section is on unit 2, both on states kept",
    DJMT1.fxSel[0] === 1 && on(U(2)) && !on(U(1)));
check("... lights: second lit, first dark, FX ON shows unit 2 (on)",
    lit(F1.selectLeds[1]) && !lit(F1.selectLeds[0]) && lit(F1.onLed));
check("... deck B untouched", DJMT1.fxSel[1] === 0 && lit(F2.selectLeds[0]));

DJMT1.fx1Mix(0, 0, 0);
DJMT1.fx1Level2(0, 0, 32);
check("knobs now drive unit 2", params[key(U(2), K)] === 0
    && params[key(S(2, 2), "meta")] === 0.25 && params[key(U(1), K)] === 0.5);

press("fx1Slot2");
check("an effect button toggles the slot on unit 2, with its light",
    on(S(2, 2)) && !on(S(1, 2)) && lit(F1.slotLeds[1]));
press("fx1NextEffect3");
press("fx1NextChain");
check("SHIFT functions act on unit 2", get(S(2, 3), "next_effect") === 1
    && get(U(2), "next_chain_preset") === 1 && get(U(1), "next_chain_preset") === 0);

press("fx1Select2");
check("pressing the lit ASSIGN again changes nothing",
    DJMT1.fxSel[0] === 1 && on(U(2)) && !on(U(1)));

press("fx1Select1");
check("deck A's first ASSIGN: back on unit 1, still off, unit 2 still on",
    DJMT1.fxSel[0] === 0 && !on(U(1)) && on(U(2)) && !lit(F1.onLed));
check("... and the effect lights follow unit 1's slots", !lit(F1.slotLeds[1]));

press("fx1On");
check("both of deck A's units can be on at once", on(U(1)) && on(U(2)) && lit(F1.onLed));

engine.setValue(U(2), "enabled", 0);
check("the other unit switched off from the screen: no change of selection",
    DJMT1.fxSel[0] === 0 && on(U(1)) && lit(F1.onLed) && lit(F1.selectLeds[0]));
engine.setValue(U(1), "enabled", 0);
check("the selected unit switched off from the screen: its light follows",
    !lit(F1.onLed));

press("fx2Select2");
check("deck B's second ASSIGN puts FX2 on unit 4, unit 3 untouched",
    DJMT1.fxSel[1] === 1 && on(U(3)) && on(U(4)) && lit(F2.selectLeds[1]));
DJMT1.fx2Level1(0, 0, 127);
check("... and its knobs drive unit 4", params[key(S(4, 1), "meta")] === 1);

// Each unit's knob_choice control picks what DRY/WET turns: 0 the super knob
// (the default), 1 dry/wet.
const C = (n) => ["[TerminalWide]", "fx" + n + "_knob_drywet"];
check("every unit has a knob choice, super then dry/wet",
    [F1, F2].every((d) => d.knobChoice && d.knobChoice.keys.join() === "super1,mix"
        && d.knobChoice.controls.length === 2)
    && F2.knobChoice.controls[1].join() === C(4).join());
check("soft takeover covers both of a unit's knob targets",
    [1, 2, 3, 4].every((n) => takeover.has(key(U(n), "super1")) && takeover.has(key(U(n), "mix"))));
DJMT1.fx2Mix(0, 0, 0);
check("by default DRY/WET turns unit 4's super knob",
    params[key(U(4), "super1")] === 0 && params[key(U(4), "mix")] === undefined);
engine.setValue(...C(4), 1);
DJMT1.fx2Mix(0, 0, 127);
check("unit 4's button on d/w: the knob turns unit 4's dry/wet instead",
    params[key(U(4), "mix")] === 1 && params[key(U(4), "super1")] === 0);
press("fx2Select1");
DJMT1.fx2Mix(0, 0, 127);
check("... while unit 3, still on super, gets its super knob turned",
    params[key(U(3), "super1")] === 1 && params[key(U(3), "mix")] === undefined);
engine.setValue(...C(4), 0);
press("fx2Select2");
DJMT1.fx2Mix(0, 0, 64);
check("unit 4 back on super: the knob turns its super knob again",
    params[key(U(4), "super1")] === 0.5 && params[key(U(4), "mix")] === 1);
engine.setValue(...C(4), 1);
DJMT1.fxChoice[1][1] = undefined;   // as if the skin had never made the control
DJMT1.fx2Mix(0, 0, 0);
check("with no choice control the knob turns knob_key",
    params[key(U(4), F2.knobKey)] === 0);

DJMT1.fxLedsOff();
check("shutdown: every FX light off",
    [F1, F2].every((d) => d.selectLeds.concat([d.onLed], d.slotLeds)
        .every((l) => leds[l.midino] === l.off)));

console.log(checks + " checks passed");
