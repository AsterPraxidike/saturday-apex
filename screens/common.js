/* Shared engine for the broadcast screens. You shouldn't need to edit this file –
   all the settings live at the top of each screen's .html file. */
(() => {
  // eslint-disable-next-line no-undef
  const S = Object.assign({}, (typeof SETTINGS !== 'undefined' ? SETTINGS : window.SETTINGS) || {});
  const qs = new URLSearchParams(location.search);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  // colors from SETTINGS.colors → CSS variables
  const col = S.colors || {};
  const root = document.documentElement.style;
  [['red', '--red'], ['redBright', '--red-hi'], ['concrete', '--concrete'], ['black', '--ink'], ['white', '--white']]
    .forEach(([k, v]) => { if (col[k]) root.setProperty(v, col[k]); });

  const stage = document.getElementById('stage');
  const fit = () => { stage.style.transform = `scale(${Math.min(innerWidth / 1920, innerHeight / 1080)})`; };
  addEventListener('resize', fit); fit();

  // Countdown target: URL ?at= / ?min= override SETTINGS.startAt / SETTINGS.countdownMinutes.
  function resolve(name) {
    const at = qs.get('at') || S.startAt;
    if (at && /^\d{1,2}(:\d{2})?$/.test(String(at).trim())) {
      const [h, m] = String(at).trim().split(':').map(Number);
      const d = new Date(); d.setHours(h, m || 0, 0, 0);
      if (d.getTime() < Date.now() - 6 * 3600e3) d.setDate(d.getDate() + 1);
      return { target: d.getTime(), total: (+S.countdownMinutes || 10) * 60 };
    }
    const min = +(qs.get('min') || S.countdownMinutes || 0);
    if (!min) return null;
    const key = `apexScreens:${name}:${min}`;
    let t = Date.now() + min * 60e3;
    try {
      const saved = +localStorage.getItem(key);
      if (!qs.has('reset') && saved && saved > Date.now() - 60e3) t = saved;  // survive scene switches
      else localStorage.setItem(key, String(t));
    } catch {}
    return { target: t, total: min * 60 };
  }
  function format(left) {
    const h = Math.floor(left / 3600), m = Math.floor(left % 3600 / 60), s = left % 60;
    return (h ? `${h}:${String(m).padStart(2, '0')}` : String(m).padStart(2, '0')) + ':' + String(s).padStart(2, '0');
  }
  // cb({ left, text, done, progress }) four times a second, or cb(null) when no countdown is set.
  function countdown(name, cb) {
    const r = resolve(name);
    if (!r) { cb(null); return; }
    const run = () => {
      const left = Math.max(0, Math.round((r.target - Date.now()) / 1000));
      cb({ left, done: left === 0, text: left === 0 ? (S.doneText || '00:00') : format(left), progress: Math.min(1, Math.max(0, 1 - left / r.total)) });
    };
    run(); setInterval(run, 250);
  }

  function fitText(el, max) {
    let s = max; el.style.fontSize = s + 'px';
    while (el.scrollWidth > el.clientWidth + 1 && s > 20) { s -= 2; el.style.fontSize = s + 'px'; }
  }
  function fitAll() { document.querySelectorAll('[data-fit]').forEach(el => fitText(el, +el.dataset.fit)); }
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => setTimeout(fitAll, 50));

  const sleep = ms => new Promise(r => setTimeout(r, ms));
  function rotate(list, ms, fn) {
    if (!list || !list.length) return;
    let i = 0; fn(list[0], 0);
    if (list.length > 1) setInterval(() => { i = (i + 1) % list.length; fn(list[i], i); }, ms);
  }
  function rng(seed) { let s = seed >>> 0; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); }
  const $ = id => document.getElementById(id);
  const text = (id, v) => { const el = $(id); if (el) el.textContent = v ?? ''; return el; };
  const showIf = (id, on) => { const el = typeof id === 'string' ? $(id) : id; if (el && !on) el.style.display = 'none'; };
  // Rotating one-line messages that slide up inside a box.
  function ticker(box, msgs, seconds) {
    msgs = (msgs || []).filter(Boolean);
    if (!box || !msgs.length) return false;
    let i = 0, cur = null;
    const next = () => {
      if (cur) { const old = cur; old.classList.remove('on'); old.classList.add('out'); setTimeout(() => old.remove(), 600); }
      cur = document.createElement('div');
      cur.className = 'tk';
      cur.textContent = msgs[i++ % msgs.length];
      box.appendChild(cur);
      let fs = parseFloat(getComputedStyle(cur).fontSize);
      while (cur.scrollWidth > cur.clientWidth + 1 && fs > 12) { fs -= 1; cur.style.fontSize = fs + 'px'; }
      requestAnimationFrame(() => requestAnimationFrame(() => cur.classList.add('on')));
    };
    setTimeout(() => { next(); if (msgs.length > 1) setInterval(next, (+seconds || 6) * 1000); }, 1500);
    return true;
  }

  window.Screens = { S, qs, esc, stage, countdown, fitText, fitAll, sleep, rotate, rng, $, text, showIf, ticker };
})();
