/* Mapping Studio front end.
 *
 * One file, no build step, no framework. The whole app is a picture of a
 * control surface plus four things you can do to it, and that does not justify
 * a toolchain on a machine whose job is to run a DJ mixer.
 *
 * The panel is drawn from the profile's own geometry rather than from vendor
 * artwork: every control is a real SVG element with an id, so hit-testing is
 * free and there is no image to license. A local backdrop image can sit behind
 * it while you work.
 *
 * SPDX-License-Identifier: MIT
 */

'use strict';

/* ------------------------------------------------------------------ state */

const S = {
  profile: null,
  controls: [],
  byId: new Map(),
  mode: 'layout',
  layer: 'base',
  sel: null,
  learn: null,
  probe: null,
  lit: null,          // control the probe thinks might be lit
  zoom: 1,
  backdrop: false,
  showProv: true,
  showLabels: true,
  dragging: null,
};

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const SVGNS = 'http://www.w3.org/2000/svg';

/* -------------------------------------------------------------------- api */

async function api(path, body) {
  const opt = body === undefined
    ? {}
    : { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body) };
  const r = await fetch(path, opt);
  let data;
  try { data = await r.json(); } catch (e) { data = { error: 'bad response' }; }
  if (!r.ok || data.error) { toast(data.error || `HTTP ${r.status}`, true); throw data; }
  return data;
}

let toastTimer;
function toast(msg, bad) {
  const el = $('#toast');
  el.textContent = msg;
  el.classList.toggle('bad', !!bad);
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), 2600);
}

/* ------------------------------------------------------------ panel draw */

function shapeEl(c) {
  const sh = c.shape || {};
  if (sh.type === 'circle') {
    const e = document.createElementNS(SVGNS, 'circle');
    e.setAttribute('cx', sh.cx); e.setAttribute('cy', sh.cy);
    e.setAttribute('r', (sh.d || 8) / 2);
    return e;
  }
  const e = document.createElementNS(SVGNS, 'rect');
  const w = sh.w || 10, h = sh.h || 8;
  e.setAttribute('x', (sh.cx || 0) - w / 2);
  e.setAttribute('y', (sh.cy || 0) - h / 2);
  e.setAttribute('width', w); e.setAttribute('height', h);
  if (sh.round !== false) { e.setAttribute('rx', Math.min(w, h) * 0.22); }
  return e;
}

function bindingOf(c, dir) {
  const b = (c.bindings || {})[S.layer] || {};
  return b[dir] || null;
}

function classesFor(c) {
  const cls = ['r'];
  const inp = bindingOf(c, 'input');
  if (c.provisional) cls.push('prov');
  if (inp && inp.status === 'silent') cls.push('silent');
  else if (inp) cls.push('mapped');
  if (bindingOf(c, 'output')) cls.push('out');
  if (S.sel === c.id) cls.push('sel');
  if (S.learn && S.learn.control_id === c.id) cls.push('learning');
  if (S.lit === c.id) cls.push('lit');
  return cls.join(' ');
}

/* The panel is drawn at 2.2 px/mm before zoom, which puts a 16 mm knob at a
   comfortable click target on a normal display. */
const PX_PER_MM = 2.2;

function zoomToFit() {
  const stage = $('#stage').getBoundingClientRect();
  const p = S.profile && S.profile.panel;
  if (!p) return;
  // Called before first layout the stage can measure zero; fall back rather
  // than computing a negative scale and rendering a zero-sized panel.
  const fitW = stage.width > 40 ? stage.width / (p.w * PX_PER_MM) : 1;
  const fitH = stage.height > 80 ? (stage.height - 40) / (p.h * PX_PER_MM) : 1;
  S.zoom = clampZoom(Math.min(fitW, fitH));
  drawPanel();
}

const clampZoom = z =>
  (Number.isFinite(z) && z > 0) ? Math.min(4, Math.max(0.15, z)) : 1;

function drawPanel() {
  const svg = $('#panel');
  const p = S.profile;
  if (!p) return;
  S.zoom = clampZoom(S.zoom);
  const W = p.panel.w, H = p.panel.h;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.setAttribute('width', W * PX_PER_MM * S.zoom);
  svg.setAttribute('height', H * PX_PER_MM * S.zoom);
  svg.textContent = '';

  if (S.backdrop) {
    const img = document.createElementNS(SVGNS, 'image');
    img.setAttribute('href', '/backdrop');
    img.setAttribute('x', 0); img.setAttribute('y', 0);
    img.setAttribute('width', W); img.setAttribute('height', H);
    img.setAttribute('opacity', '.55');
    svg.appendChild(img);
  } else {
    const body = document.createElementNS(SVGNS, 'rect');
    body.setAttribute('class', 'body');
    body.setAttribute('x', 0); body.setAttribute('y', 0);
    body.setAttribute('width', W); body.setAttribute('height', H);
    body.setAttribute('rx', 3);
    svg.appendChild(body);
  }

  // Concentric controls are a real pattern -- a push encoder is a knob and a
  // button at the same spot -- so their readouts would print on top of each
  // other. Stack them instead.
  const atCentre = new Map();
  for (const c of S.controls) {
    const sh = c.shape || {};
    const k = `${Math.round(sh.cx)}:${Math.round(sh.cy)}`;
    atCentre.set(k, (atCentre.get(k) || 0) + 1);
  }
  const seenCentre = new Map();

  for (const c of S.controls) {
    if (c.provisional && !S.showProv) continue;
    const g = document.createElementNS(SVGNS, 'g');
    g.setAttribute('class', classesFor(c));
    g.dataset.id = c.id;

    const hit = shapeEl(c);
    hit.setAttribute('class', 'hit');
    g.appendChild(hit);

    const sh = c.shape || {};
    const half = sh.type === 'circle' ? (sh.d || 8) / 2 : (sh.h || 8) / 2;

    if (S.showLabels) {
      const t = document.createElementNS(SVGNS, 'text');
      t.setAttribute('class', 'lab');
      t.setAttribute('x', sh.cx); t.setAttribute('y', sh.cy + half + 3.1);
      t.textContent = (c.label || c.id).slice(0, 18);
      g.appendChild(t);
    }
    const inp = bindingOf(c, 'input');
    if (inp && inp.status !== 'silent') {
      const key = `${Math.round(sh.cx)}:${Math.round(sh.cy)}`;
      const nth = seenCentre.get(key) || 0;
      seenCentre.set(key, nth + 1);
      const stack = atCentre.get(key) > 1 ? (nth - (atCentre.get(key) - 1) / 2) * 3.2 : 0;
      const n = document.createElementNS(SVGNS, 'text');
      n.setAttribute('class', 'num');
      n.setAttribute('x', sh.cx); n.setAttribute('y', sh.cy + 0.8 + stack);
      n.textContent = (inp.status === 'cc' ? 'CC' : 'N') + inp.number;
      g.appendChild(n);
    }

    if (S.sel === c.id && S.mode === 'layout') {
      const hw = sh.type === 'circle' ? (sh.d || 8) / 2 : (sh.w || 10) / 2;
      const hd = document.createElementNS(SVGNS, 'circle');
      hd.setAttribute('class', 'handle');
      hd.setAttribute('cx', sh.cx + hw); hd.setAttribute('cy', sh.cy + half);
      hd.setAttribute('r', 1.5);
      hd.dataset.role = 'resize';
      g.appendChild(hd);
    }
    svg.appendChild(g);
  }
}

/* --------------------------------------------------------- panel gestures */

function svgPoint(evt) {
  const svg = $('#panel');
  const r = svg.getBoundingClientRect();
  const p = S.profile.panel;
  return {
    x: (evt.clientX - r.left) / r.width * p.w,
    y: (evt.clientY - r.top) / r.height * p.h,
  };
}

function onPanelDown(evt) {
  const g = evt.target.closest('g.r');
  if (!g) { if (S.mode === 'layout') select(null); return; }
  const id = g.dataset.id;

  if (S.mode === 'learn') { startLearn(id); return; }
  if (S.mode === 'probe' && S.probe && S.probe.active) { answerProbe(id); return; }

  select(id);
  if (S.mode !== 'layout') return;

  const c = S.byId.get(id);
  const role = evt.target.dataset.role;
  S.dragging = {
    id, role: role || 'move', start: svgPoint(evt),
    orig: JSON.parse(JSON.stringify(c.shape)), moved: false,
  };
  $('#panel').setPointerCapture(evt.pointerId);
}

function onPanelMove(evt) {
  if (!S.dragging) return;
  const d = S.dragging;
  const p = svgPoint(evt);
  const dx = p.x - d.start.x, dy = p.y - d.start.y;
  if (Math.abs(dx) > 0.3 || Math.abs(dy) > 0.3) d.moved = true;
  const c = S.byId.get(d.id);
  const sh = c.shape;
  if (d.role === 'move') {
    sh.cx = +(d.orig.cx + dx).toFixed(2);
    sh.cy = +(d.orig.cy + dy).toFixed(2);
  } else if (sh.type === 'circle') {
    sh.d = Math.max(2, +(d.orig.d + 2 * Math.max(dx, dy)).toFixed(2));
  } else {
    sh.w = Math.max(2, +(d.orig.w + 2 * dx).toFixed(2));
    sh.h = Math.max(2, +(d.orig.h + 2 * dy).toFixed(2));
  }
  drawPanel();
}

async function onPanelUp(evt) {
  if (!S.dragging) return;
  const d = S.dragging;
  S.dragging = null;
  try { $('#panel').releasePointerCapture(evt.pointerId); } catch (e) { /* ignore */ }
  if (!d.moved) return;
  const c = S.byId.get(d.id);
  await api('/api/control/update', { id: d.id, patch: { shape: c.shape } });
  await refreshProfile();
  select(d.id);
}

/* ---------------------------------------------------------------- select */

function select(id) {
  S.sel = id;
  drawPanel();
  renderEditor();
  renderAssign();
  const c = id && S.byId.get(id);
  if (S.mode === 'layout') {
    hint(c ? `<b>${c.label}</b> — drag to move, corner dot to resize`
           : 'Click a region to select it, or press <b>N</b> to add one.');
  }
}

function hint(html) { $('#hint').innerHTML = html; }

/* ------------------------------------------------------------ layout pane */

const KINDS = ['knob', 'encoder', 'fader', 'jog', 'button', 'pad', 'switch',
               'led', 'meter'];

function renderEditor() {
  const box = $('#editor');
  const c = S.sel && S.byId.get(S.sel);
  if (!c) { box.className = 'empty'; box.textContent = 'Select a region.'; return; }
  box.className = '';
  const sh = c.shape || {};
  box.innerHTML = `
    <div class="field"><label>Label</label>
      <input type="text" id="e-label" value="${esc(c.label || '')}"></div>
    <div class="field"><label>Id</label>
      <input type="text" id="e-id" value="${esc(c.id)}"></div>
    <div class="row">
      <div class="field" style="flex:1"><label>Kind</label>
        <select id="e-kind">${KINDS.map(k =>
          `<option${k === c.kind ? ' selected' : ''}>${k}</option>`).join('')}</select>
      </div>
      <div class="field" style="flex:1"><label>Section</label>
        <input type="text" id="e-section" value="${esc(c.section || '')}"></div>
    </div>
    <label class="chk"><input type="checkbox" id="e-detent"
      ${c.detent ? 'checked' : ''}> has a centre detent</label>
    <div class="row" style="margin-top:12px">
      <div class="field" style="flex:1;margin-bottom:0"><label>Shape</label>
        <select id="e-shape">
          <option value="rect"${sh.type !== 'circle' ? ' selected' : ''}>rectangle</option>
          <option value="circle"${sh.type === 'circle' ? ' selected' : ''}>circle</option>
        </select>
      </div>
    </div>
    <div class="field" style="margin-top:10px">
      <label>Geometry (mm)</label>
      <div class="row" id="e-geom">${geomFields(sh)}</div>
    </div>
    ${c.provisional ? `<div class="note">Guessed by the first pass
      (confidence ${(c.confidence || 0).toFixed(2)}).
      ${(c.evidence || []).join('; ')}</div>` : ''}
    ${describeBindings(c)}
    ${colourPicker(c)}
    <div class="row" style="margin-top:14px">
      <button id="e-save" class="primary">Apply</button>
      <button id="e-led-local" class="ghost">LED is firmware-driven</button>
      <button id="e-del" class="ghost danger">Delete</button>
    </div>`;

  // Swapping shape re-renders just the geometry row, carrying the size over.
  $('#e-shape').onchange = () => {
    const next = readShape(c.shape || {});
    $('#e-geom').innerHTML = geomFields(next);
  };

  $('#e-save').onclick = async () => {
    const newId = $('#e-id').value.trim();
    const patch = {
      label: $('#e-label').value,
      kind: $('#e-kind').value,
      section: $('#e-section').value || null,
      detent: $('#e-detent').checked || null,
      shape: readShape(c.shape || {}),
    };
    await api('/api/control/update', { id: c.id, patch });
    let finalId = c.id;
    if (newId && newId !== c.id) {
      const r = await api('/api/control/rename', { id: c.id, new_id: newId });
      finalId = r.control.id;
    }
    await refreshProfile();
    select(finalId);
    toast('Updated');
  };
  $('#e-del').onclick = async () => {
    await api('/api/control/delete', { id: c.id });
    await refreshProfile();
    select(null);
    toast('Deleted');
  };
  $('#e-led-local').onclick = async () => {
    await api('/api/led/local', { control_id: c.id });
    await refreshProfile();
    select(c.id);
    toast('Recorded: LED is firmware-driven');
  };
  wireClearButtons(c.id);
  wireColourPicker(c);
}

function describeBindings(c) {
  const out = [];
  const clear = (layer, dir) =>
    `<button class="clearbind sm ghost" data-layer="${esc(layer)}"
       data-dir="${dir}" title="clear this binding">clear</button>`;
  for (const [layer, b] of Object.entries(c.bindings || {})) {
    const i = b.input, o = b.output;
    if (i) {
      out.push(`<div class="bindline mono" style="color:${
        i.status === 'silent' ? 'var(--text-faint)' : 'var(--ok)'}">${
        i.status === 'silent'
          ? `${layer}: sends no MIDI`
          : `${layer} in: ${i.status} ${i.number} ch${i.channel}${
              i.mode ? ' · ' + i.mode : ''}`}${clear(layer, 'input')}</div>`);
    }
    if (o && o.status === 'local') {
      out.push(`<div class="bindline mono" style="color:var(--text-faint)">${
        layer} LED: firmware-driven${clear(layer, 'output')}</div>`);
    } else if (o) {
      out.push(`<div class="bindline mono" style="color:var(--led)">${
        layer} LED: note ${o.number} ch${o.channel || 1}${
        clear(layer, 'output')}</div>`);
    }
  }
  return out.length ? `<div class="field" style="margin-top:10px">${out.join('')}</div>` : '';
}

/* Colour is picked against the hardware, not guessed from a swatch: clicking
   one lights the real pad immediately. That is the same click-and-confirm loop
   as the rest of the tool, and the only way to be sure the encoding is right. */
function colourPicker(c) {
  if (c.rgb === false || !S.palette) return '';
  const out = bindingOf(c, 'output');
  if (!out || out.status === 'local') {
    return c.fixed_colour
      ? `<div class="field"><label>LED colour</label>
           <div class="mono" style="color:var(--text-faint)">fixed
           ${esc(c.fixed_colour)} — not addressable</div></div>`
      : '';
  }
  if (c.kind !== 'pad' && !c.colour) return '';
  const cur = c.colour || {};
  return `
    <div class="field" style="margin-top:12px">
      <label>LED colour${cur.velocity ? ` — velocity ${cur.velocity}` : ''}</label>
      <div class="swatches">${Object.keys(S.palette.named).map(n => {
        const hex = S.paletteHex[n] || '#000';
        return `<button class="sw" data-colour="${esc(n)}" title="${esc(n)}"
                  style="background:${hex}"></button>`;
      }).join('')}</div>
      <label class="chk" style="margin-top:8px"><input type="checkbox"
        id="c-bright" ${cur.bright === false ? '' : 'checked'}> bright</label>
      <div class="mono" style="color:var(--text-faint);margin-top:6px">
        ${esc(S.palette.describe || '')}</div>
    </div>`;
}

function wireColourPicker(c) {
  $$('#editor .sw').forEach(sw => {
    sw.onclick = async () => {
      await api('/api/colour', {
        control_id: c.id, name: sw.dataset.colour,
        bright: $('#c-bright') ? $('#c-bright').checked : true,
        remember: true });
      await refreshProfile();
      select(c.id);
      toast(`${sw.dataset.colour} — check the pad`);
    };
  });
}

function wireClearButtons(controlId) {
  $$('#editor .clearbind').forEach(btn => {
    btn.onclick = async () => {
      await api('/api/binding/clear', {
        id: controlId, layer: btn.dataset.layer, direction: btn.dataset.dir });
      await refreshProfile();
      select(controlId);
      toast('Binding cleared');
    };
  });
}

/* Geometry is typed, not just dragged. Dragging is fine for nudging a
   detected region, but placing a 90 mm jog wheel or a fader on a panel whose
   dimensions are known to a tenth of a millimetre wants numbers. */
function geomFields(sh) {
  const num = (id, label, v, step = 0.1) =>
    `<label>${label} <input type="number" id="${id}" step="${step}"
       value="${(+v || 0).toFixed(1)}"></label>`;
  const common = num('e-cx', 'x', sh.cx) + num('e-cy', 'y', sh.cy);
  return sh.type === 'circle'
    ? common + num('e-d', '⌀', sh.d != null ? sh.d : 16)
    : common + num('e-w', 'w', sh.w != null ? sh.w : 14)
             + num('e-h', 'h', sh.h != null ? sh.h : 9);
}

/* Converting between shapes keeps the area roughly, so a region does not jump
   in size when you change your mind about what it is. */
function readShape(prev) {
  const type = $('#e-shape').value;
  const cx = +$('#e-cx').value, cy = +$('#e-cy').value;
  if (type === 'circle') {
    const d = $('#e-d') ? +$('#e-d').value
      : Math.max(2, ((+prev.w || 14) + (+prev.h || 9)) / 2);
    return { type: 'circle', cx, cy, d: Math.max(1, d) };
  }
  const w = $('#e-w') ? +$('#e-w').value : Math.max(2, +prev.d || 16);
  const h = $('#e-h') ? +$('#e-h').value : Math.max(2, +prev.d || 16);
  return { type: 'rect', cx, cy, w: Math.max(1, w), h: Math.max(1, h),
           round: prev.round !== false };
}

const fmt = n => (n === undefined || n === null) ? '?' : (+n).toFixed(1);
const esc = s => String(s == null ? '' : s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');

async function addControl(type = 'rect') {
  const p = S.profile.panel;
  const circle = type === 'circle';
  const c = await api('/api/control/add', {
    label: circle ? 'New knob' : 'New button',
    kind: circle ? 'knob' : 'button',
    shape: circle
      ? { type: 'circle', cx: p.w / 2, cy: p.h / 2, d: 16 }
      : { type: 'rect', cx: p.w / 2, cy: p.h / 2, w: 14, h: 9, round: true },
  });
  await refreshProfile();
  select(c.control.id);
  toast(`Added a ${circle ? 'circle' : 'rectangle'} — drag it into place`);
}

/* ------------------------------------------------------------- learn pane */

async function startLearn(id) {
  S.learn = await api('/api/learn/start', { control_id: id, layer: S.layer });
  select(id);
  drawPanel();
  renderLearn();
}

function renderLearn() {
  const box = $('#learnbox');
  if (!S.learn || !S.learn.active) {
    box.className = 'empty';
    box.innerHTML = S.mode === 'learn'
      ? 'Pick a region on the panel, then move that control.'
      : '';
    $('#learnlive').innerHTML = '';
    return;
  }
  box.className = '';
  const c = S.byId.get(S.learn.control_id) || {};
  box.innerHTML = `
    <div class="capture">
      <div class="what">${esc(c.label || S.learn.control_id)}</div>
      <div class="sub pulse">move it now — ${S.learn.event_count} messages</div>
      <div class="row" style="margin-top:14px">
        <button id="l-done" class="primary">Done</button>
        <button id="l-silent" class="ghost">Sends nothing</button>
        <button id="l-cancel" class="ghost">Cancel</button>
      </div>
    </div>`;
  $('#l-done').onclick = finishLearn;
  $('#l-cancel').onclick = async () => {
    await api('/api/learn/cancel', {});
    S.learn = null; drawPanel(); renderLearn();
  };
  $('#l-silent').onclick = async () => {
    const id = S.learn.control_id;
    await api('/api/learn/cancel', {});
    await api('/api/silent', { control_id: id, layer: S.layer });
    S.learn = null;
    await refreshProfile();
    renderLearn();
    toast('Recorded as silent');
  };
}

async function finishLearn() {
  const res = await api('/api/learn/finish', { commit: true });
  S.learn = null;
  await refreshProfile();
  renderLearn();
  showCapture(res);
}

function showCapture(res) {
  const b = res.binding;
  const el = $('#learnlive');
  const notes = (res.notes || []).map(n => {
    const bad = /already claimed|nothing arrived/.test(n);
    return `<div class="note${bad ? ' bad' : ''}">${esc(n)}</div>`;
  }).join('');
  el.innerHTML = `
    <div class="result">
      <div class="msg${b ? '' : ' none'}">${b
        ? `${b.status.toUpperCase()} ${b.number} · ch ${b.channel}` +
          (b.mode === 'absolute'
            ? ` · ${b.min}–${b.max}, resting ${b.resting}`
            : b.mode ? ` · ${b.mode}` : '')
        : 'nothing captured'}</div>
      ${notes}
    </div>`;
}

/* ------------------------------------------------------------- probe pane */

function probeChannels() {
  // "seen" means whatever channels this surface has actually used, which is
  // the right default: a controller that splits decks and pads across
  // channels hides its LEDs on those same channels.
  const raw = ($('#pch').value || 'seen').trim().toLowerCase();
  if (!raw || raw === 'seen' || raw === 'auto') return 'seen';
  const list = raw.split(/[,\s]+/).map(Number)
    .filter(n => Number.isInteger(n) && n >= 1 && n <= 16);
  return list.length ? list : 'seen';
}

async function startProbe() {
  S.probe = await api('/api/probe/start', {
    lo: +$('#plo').value, hi: +$('#phi').value,
    channels: probeChannels(),
    strategy: $('#pstrat').value,
  });
  $('#probesetup').hidden = true;
  $('#probebox').hidden = false;
  renderProbe();
}

async function answerProbe(controlId) {
  S.probe = await api('/api/probe/answer', { control_id: controlId || null });
  await refreshProfile();
  renderProbe();
}

async function undoProbe() {
  S.probe = await api('/api/probe/undo', {});
  await refreshProfile();
  renderProbe();
  toast('Undone — that note is lit again');
}

function renderProbe() {
  const box = $('#probebox');
  const p = S.probe;
  if (!p || (!p.active && !p.done)) { box.hidden = true; return; }
  if (p.done) {
    box.innerHTML = `<div class="capture">
      <div class="what">Probe finished</div>
      <div class="sub">${p.found} LEDs identified across ${p.answered} notes.</div>
      <button id="p-again" class="primary big">Run another pass</button></div>`;
    $('#p-again').onclick = () => {
      $('#probesetup').hidden = false; box.hidden = true; S.probe = null;
    };
    hint('');
    return;
  }
  const cur = p.current || {};
  box.innerHTML = `
    <div class="probing">
      <div class="counter">${p.index + 1} / ${p.total} · found ${p.found}</div>
      <div class="note-num">note ${cur.note}</div>
      <div class="prior">channel ${cur.channel} · 0x${
        Number(cur.note).toString(16).toUpperCase().padStart(2, '0')}</div>
      <div class="ask">Which region just lit up?</div>
      ${cur.prior ? '<div class="prior">a button already sends this note</div>' : ''}
      <div class="progress"><i style="width:${(p.index / p.total * 100).toFixed(1)}%"></i></div>
      <div class="acts">
        <button id="p-none" class="ghost">Nothing lit</button>
        <button id="p-undo" class="ghost"${p.answered ? '' : ' disabled'}>Undo last</button>
        <button id="p-stop" class="ghost danger">Stop</button>
      </div>
      ${p.last ? `<div class="prior" style="margin-top:9px">last: note ${
        p.last.note} ch${p.last.channel} &rarr; ${
        esc(p.last.control_label || 'nothing lit')}</div>` : ''}
    </div>`;
  $('#p-none').onclick = () => answerProbe(null);
  $('#p-undo').onclick = undoProbe;
  $('#p-stop').onclick = async () => {
    await api('/api/probe/stop', {});
    S.probe = null; box.hidden = true; $('#probesetup').hidden = false;
    hint('');
  };
  hint('<b>Click the region on the panel that lit up</b>, or “Nothing lit”.');
}

/* ------------------------------------------------------------ assign pane */

const TARGETS = [
  ['[ChannelN]', 'volume'], ['[ChannelN]', 'pregain'], ['[ChannelN]', 'pfl'],
  ['[ChannelN]', 'play'], ['[ChannelN]', 'cue_default'], ['[ChannelN]', 'sync_enabled'],
  ['[ChannelN]', 'LoadSelectedTrack'], ['[ChannelN]', 'rate'],
  ['[ChannelN]', 'beatloop_activate'], ['[ChannelN]', 'hotcue_1_activate'],
  ['[EqualizerRack1_[ChannelN]_Effect1]', 'parameter1'],
  ['[EqualizerRack1_[ChannelN]_Effect1]', 'parameter2'],
  ['[EqualizerRack1_[ChannelN]_Effect1]', 'parameter3'],
  ['[QuickEffectRack1_[ChannelN]]', 'super1'],
  ['[Master]', 'crossfader'], ['[Master]', 'gain'], ['[Master]', 'headMix'],
  ['[Library]', 'MoveVertical'], ['[Library]', 'GoToItem'],
];

function renderAssign() {
  const box = $('#assignbox');
  const c = S.sel && S.byId.get(S.sel);
  const inp = c && bindingOf(c, 'input');
  if (!c || !inp || inp.status === 'silent') {
    box.className = 'empty';
    box.textContent = c ? 'This control has no captured input yet.'
                        : 'Select a mapped region.';
    return;
  }
  box.className = '';
  const t = (c.targets || {})[S.layer] || (S.layer === 'base' ? (c.target || {}) : {});
  box.innerHTML = `
    <div class="capture">
      <div class="what">${esc(c.label)} <span class="prior">on ${esc(S.layer)}</span></div>
      <div class="sub mono">${inp.status} ${inp.number} · ch ${inp.channel}${
        inp.mode ? ' · ' + inp.mode : ''}</div>
    </div>
    <div class="field" style="margin-top:12px"><label>Group</label>
      <input type="text" id="t-group" list="tgroups" value="${esc(t.group || '')}"
             placeholder="[Channel1]"></div>
    <datalist id="tgroups">${
      [...new Set(TARGETS.map(x => x[0]))].map(g =>
        `<option value="${esc(g.replace('N', '1'))}">`).join('')}</datalist>
    <div class="field"><label>Key</label>
      <input type="text" id="t-key" list="tkeys" value="${esc(t.key || '')}"
             placeholder="volume"></div>
    <datalist id="tkeys">${
      [...new Set(TARGETS.map(x => x[1]))].map(k =>
        `<option value="${esc(k)}">`).join('')}</datalist>
    <label class="chk"><input type="checkbox" id="t-toggle" ${t.toggle ? 'checked' : ''}>
      toggle on press (needs a script binding)</label>
    <div class="row" style="margin-top:12px">
      <button id="t-save" class="primary">Assign</button>
      ${bindingOf(c, 'output')
        ? '<button id="t-blink" class="ghost">Blink its LED</button>' : ''}
    </div>`;
  $('#t-save').onclick = async () => {
    await api('/api/control/target', { id: c.id, layer: S.layer, target: {
      group: $('#t-group').value.trim(),
      key: $('#t-key').value.trim(),
      toggle: $('#t-toggle').checked || undefined,
    } });
    await refreshProfile(); select(c.id); toast('Assigned');
  };
  const bl = $('#t-blink');
  if (bl) bl.onclick = () => api('/api/blink', { control_id: c.id });
}

function renderUnassigned() {
  const ul = $('#unassigned');
  const items = S.controls.filter(c => {
    const i = bindingOf(c, 'input');
    const t = (c.targets || {})[S.layer]
      || (S.layer === 'base' ? c.target : null);
    return i && i.status !== 'silent' && !(t && t.group);
  });
  ul.innerHTML = items.length
    ? items.map(c => {
        const i = bindingOf(c, 'input');
        return `<li data-id="${esc(c.id)}">${esc(c.label)}
          <span class="tag">${i.status} ${i.number}</span></li>`;
      }).join('')
    : '<li style="color:var(--text-faint)">Everything captured has a target.</li>';
  $$('#unassigned li[data-id]').forEach(li => {
    li.onclick = () => select(li.dataset.id);
  });
}

/* ------------------------------------------------------------ export pane */

function renderStats(st) {
  if (!st) return;
  const ins = Object.entries(st.mapped_inputs || {})
    .map(([l, n]) => `<dt>inputs (${l})</dt><dd><b>${n}</b></dd>`).join('');
  $('#stats').innerHTML = `
    <dt>controls on panel</dt><dd><b>${st.controls}</b></dd>
    <dt>still provisional</dt><dd><b>${st.provisional}</b></dd>
    ${ins}
    <dt>LED outputs</dt><dd><b>${st.mapped_outputs}</b></dd>
    <dt>assigned to Mixxx</dt><dd><b>${st.targeted}</b></dd>
    ${st.collisions ? `<dt style="color:var(--bad)">collisions</dt>
      <dd><b style="color:var(--bad)">${st.collisions}</b></dd>` : ''}`;
}

/* ------------------------------------------------------------------- sync */

async function refreshProfile() {
  const d = await api('/api/profile');
  S.profile = d.profile;
  S.backdrop = d.backdrop;
  S.controls = d.profile.controls || [];
  S.byId = new Map(S.controls.map(c => [c.id, c]));
  $('#pname').textContent = d.profile.name || d.profile.id;
  const sel = $('#layer');
  const layers = d.profile.layers || ['base'];
  if (sel.options.length !== layers.length) {
    sel.innerHTML = layers.map(l =>
      `<option${l === S.layer ? ' selected' : ''}>${esc(l)}</option>`).join('');
  }
  drawPanel();
  renderUnassigned();
  return d;
}

async function poll() {
  try {
    const st = await api('/api/state');
    S.layer = st.layer;
    renderStats(st.stats);
    $('#link').textContent = st.backend_status || st.backend;
    $('#link').className = 'pill ' +
      (/connected/.test(st.backend_status) ? 'live'
        : /offline/.test(st.backend_status) ? 'idle' : 'dead');
    $('#save').disabled = !st.dirty;

    const os = $('#outstat');
    if (os && st.output_status) {
      os.textContent = st.output_status;
      os.className = 'pill ' + (/^out:/.test(st.output_status) ? 'live'
        : /offline/.test(st.output_status) ? 'idle' : 'dead');
    }

    if (st.learn && st.learn.active) { S.learn = st.learn; renderLearn(); }
    else if (S.learn && S.learn.active) { S.learn = null; renderLearn(); }

    // The probe lives on the server, so adopt its state rather than trusting
    // ours: this page may have been reloaded mid-pass, or the pass may have
    // been started from elsewhere. Without this the panel is clickable but
    // shows no prompt, which looks like the probe is broken.
    if (st.probe && st.probe.active) {
      const cur = S.probe && S.probe.current;
      const now = st.probe.current;
      const changed = !S.probe || !cur || !now || cur.note !== now.note
        || S.probe.index !== st.probe.index;
      S.probe = st.probe;
      if (changed) {
        $('#probesetup').hidden = true;
        $('#probebox').hidden = false;
        renderProbe();
      }
    } else if (S.probe && S.probe.active) {
      S.probe = null;
      $('#probebox').hidden = true;
      $('#probesetup').hidden = false;
      hint('');
    }

    $('#log').innerHTML = (st.log || []).slice(-24)
      .map(l => `<div>${esc(l.text)}</div>`).join('');
    $('#log').scrollTop = 1e6;

    const sh = $('#seenhint');
    if (sh) {
      const seen = st.seen || [];
      sh.textContent = seen.length
        ? 'seen so far: ' + seen.map(s =>
            `ch${s.channel} (${s.notes} notes${
              s.note_lo === null ? '' : ` ${s.note_lo}-${s.note_hi}`})`).join(', ')
        : 'nothing seen yet — press a few buttons and they will be listed here.';
    }

    if (S.mode === 'learn') {
      const m = await api('/api/monitor?limit=28');
      $('#monitor').innerHTML = m.events.slice().reverse().map(e =>
        `<li>${e.status} ch${e.channel} n${e.number} = ${e.value}</li>`).join('');
    }
  } catch (e) { /* the server may be restarting; the next tick retries */ }
}

/* ------------------------------------------------------------------ modes */

function setMode(m) {
  S.mode = m;
  $$('#modes button').forEach(b => b.classList.toggle('on', b.dataset.mode === m));
  $$('.pane').forEach(p => { p.hidden = p.dataset.pane !== m; });
  const tips = {
    layout: 'Click a region to select it, or press <b>N</b> to add one.',
    learn: 'Click a region, then <b>move that control on the hardware</b>.',
    probe: 'Start a pass, then click whichever region lights up.',
    assign: 'Pick a captured control and say what it should drive.',
    export: '',
  };
  hint(tips[m] || '');
  drawPanel();
  if (m === 'assign') renderUnassigned();
}

/* ------------------------------------------------------------------- boot */

function wire() {
  $$('#modes button').forEach(b => b.onclick = () => setMode(b.dataset.mode));

  const svg = $('#panel');
  svg.addEventListener('pointerdown', onPanelDown);
  svg.addEventListener('pointermove', onPanelMove);
  svg.addEventListener('pointerup', onPanelUp);

  $('#zoomin').onclick = () => { S.zoom = Math.min(4, S.zoom * 1.25); drawPanel(); };
  $('#zoomout').onclick = () => { S.zoom = Math.max(.25, S.zoom / 1.25); drawPanel(); };
  $('#zoomfit').onclick = zoomToFit;
  $('#showprov').onchange = e => { S.showProv = e.target.checked; drawPanel(); };
  $('#showlabels').onchange = e => { S.showLabels = e.target.checked; drawPanel(); };

  $('#save').onclick = async () => {
    const r = await api('/api/save', {});
    toast('Saved ' + r.saved.split(/[\\/]/).pop());
  };
  $('#layer').onchange = async e => {
    await api('/api/layer', { layer: e.target.value });
    S.layer = e.target.value;
    await refreshProfile();
  };

  $('#delprov').onclick = async () => {
    const prov = S.controls.filter(c => c.provisional);
    if (!prov.length) { toast('Nothing provisional left'); return; }
    if (!confirm(`Delete ${prov.length} provisional regions?`)) return;
    for (const c of prov) await api('/api/control/delete', { id: c.id });
    await refreshProfile(); select(null);
    toast(`Deleted ${prov.length}`);
  };
  $('#keepprov').onclick = async () => {
    const prov = S.controls.filter(c => c.provisional);
    for (const c of prov) {
      await api('/api/control/update', { id: c.id, patch: { label: c.label } });
    }
    await refreshProfile();
    toast(`Accepted ${prov.length}`);
  };

  $('#probestart').onclick = startProbe;

  // Before committing to a pass, prove output reaches the device at all. An
  // LED probe against a controller that has stopped accepting output looks
  // identical to one where nothing happens to be wired up.
  $('#p-test').onclick = async () => {
    const lit = S.controls.filter(c => bindingOf(c, 'output')
      && bindingOf(c, 'output').status !== 'local');
    const box = $('#outcheck');
    if (!lit.length) {
      box.hidden = false;
      box.textContent = 'No LED is mapped yet, so there is nothing known-good '
        + 'to test with. Run a pass and come back.';
      return;
    }
    for (const c of lit.slice(0, 6)) {
      const o = bindingOf(c, 'output');
      await api('/api/send', { status: 'note_on', channel: o.channel || 1,
                               number: o.number, value: o.on || 127 });
    }
    box.hidden = false;
    box.innerHTML = `Lit ${Math.min(lit.length, 6)} LEDs that a previous pass `
      + `confirmed work. <b>If nothing came on</b>, the controller has stopped `
      + `accepting output — unplug its USB and plug it back in. Nothing in `
      + `software will fix that.`;
    setTimeout(() => {
      lit.slice(0, 6).forEach(c => {
        const o = bindingOf(c, 'output');
        api('/api/send', { status: 'note_off', channel: o.channel || 1,
                           number: o.number, value: 0 });
      });
    }, 2500);
  };

  $('#exportprev').onclick = async () => {
    const d = await api(`/api/export?layer=${encodeURIComponent(S.layer)}`);
    $('#exportout').textContent = d.xml + '\n\n/* ---- ' + d.script_file +
      ' ---- */\n\n' + d.script;
  };
  $('#exportwrite').onclick = async () => {
    const d = await api('/api/export/write', { layer: S.layer });
    toast('Wrote ' + d.written.length + ' files');
    $('#exportout').textContent = d.written.join('\n');
  };

  document.addEventListener('keydown', e => {
    if (/^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName)) return;
    if (e.key === 'Escape') { select(null); }
    else if (e.key === 'n' || e.key === 'N') {
      if (S.mode === 'layout') addControl('rect');
    } else if (e.key === 'c' || e.key === 'C') {
      if (S.mode === 'layout') addControl('circle');
    } else if ((e.key === 'Delete' || e.key === 'Backspace') && S.sel
               && S.mode === 'layout') {
      api('/api/control/delete', { id: S.sel })
        .then(refreshProfile).then(() => select(null));
    } else if (e.key === ' ' && S.learn && S.learn.active) {
      e.preventDefault(); finishLearn();
    } else if (S.mode === 'probe' && S.probe && S.probe.active && e.key === '0') {
      answerProbe(null);
    }
  });
}

async function loadPalette() {
  try {
    const p = await api('/api/palette');
    S.palette = p;
    // Index each named colour's hex by encoding it the same way the device
    // does, so a swatch shows roughly what the pad will show.
    S.paletteHex = {};
    for (const [n, info] of Object.entries(p.named || {})) {
      S.paletteHex[n] = info.hex;
    }
  } catch (e) { S.palette = null; }
}

(async function boot() {
  wire();
  await loadPalette();
  await refreshProfile();
  setMode('layout');
  // Fit once the stage actually has a size to measure.
  requestAnimationFrame(() => requestAnimationFrame(zoomToFit));
  window.addEventListener('resize', () => { if (S.zoom <= 0.16) zoomToFit(); });
  await poll();
  setInterval(poll, 350);
})();
