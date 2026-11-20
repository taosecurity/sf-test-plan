// Headless test of an sf-test-plan page and its script (assets/page.js; FORMAT.md sections 2 and 3).
// Uses Node's built-in fetch and WebSocket and the Chrome DevTools protocol; no npm packages.
// Usage: node tests/page_test.mjs <page.html> [shots folder]
// Exit code 0 = all passed, 1 = a check failed, 2 = bad arguments or Chrome could not start.
// Chrome always runs with the fixed profile folder %LOCALAPPDATA%\HeadlessChromeProfile: a fresh profile per launch
// makes Chrome try a blank-password Windows logon, and enough of those lock the account out.
import { spawn } from 'node:child_process';
import { writeFileSync, readFileSync, existsSync, mkdirSync, readdirSync, unlinkSync, rmSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { pathToFileURL } from 'node:url';

const file = process.argv[2];
if (!file || !existsSync(file)) {
  console.log(`Usage: node tests/page_test.mjs <page.html> [shots folder]. Page not found: ${file || '(none given)'}`);
  process.exit(2);
}
const pageUrl = pathToFileURL(resolve(file)).href;
const shots = process.argv[3] ? resolve(process.argv[3]) : '';
if (shots) mkdirSync(shots, { recursive: true });
const work = join(tmpdir(), `sf-test-plan-page-test-${process.pid}`);
mkdirSync(work, { recursive: true });

const chromes = [
  process.env.CHROME_PATH,
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  process.env.LOCALAPPDATA && join(process.env.LOCALAPPDATA, 'Google\\Chrome\\Application\\chrome.exe'),
].filter(Boolean);
const chrome = chromes.find((p) => existsSync(p));
if (!chrome) { console.log('Chrome not found. Install Google Chrome or set CHROME_PATH to chrome.exe.'); process.exit(2); }
if (!process.env.LOCALAPPDATA) { console.log('LOCALAPPDATA is not set, so the fixed Chrome profile folder cannot be found.'); process.exit(2); }
const profile = join(process.env.LOCALAPPDATA, 'HeadlessChromeProfile');
const port = Number(process.env.TP_CDP_PORT || 9337);
const proc = spawn(chrome, ['--headless=new', '--disable-gpu', `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`,
  '--no-first-run', '--force-device-scale-factor=1.5', '--window-size=1280,900', 'about:blank'], { stdio: 'ignore' });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function finish(code) { try { proc.kill(); } catch { } try { rmSync(work, { recursive: true, force: true }); } catch { } process.exit(code); }

let targets = [];
for (let i = 0; i < 50 && !targets.some((t) => t.type === 'page'); i++) {
  try { targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json(); } catch { }
  await sleep(200);
}
const target = targets.find((t) => t.type === 'page');
if (!target) { console.log(`Chrome did not open its DevTools port ${port}. Close other headless Chrome windows using the profile, or set TP_CDP_PORT.`); finish(2); }
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener('open', r));

let seq = 0; const waits = {}; const errors = []; const dialogs = []; let dialogAnswer = true;
const send = (method, params = {}) => new Promise((r) => { const i = ++seq; waits[i] = r; ws.send(JSON.stringify({ id: i, method, params })); });
ws.addEventListener('message', (m) => {
  const d = JSON.parse(m.data);
  if (d.id && waits[d.id]) { waits[d.id](d); delete waits[d.id]; }
  if (d.method === 'Runtime.exceptionThrown') errors.push(d.params.exceptionDetails.exception?.description || d.params.exceptionDetails.text);
  if (d.method === 'Page.javascriptDialogOpening') {
    dialogs.push({ type: d.params.type, message: d.params.message });
    const i = ++seq; ws.send(JSON.stringify({ id: i, method: 'Page.handleJavaScriptDialog', params: { accept: d.params.type === 'confirm' ? dialogAnswer : true } }));
  }
});
const ev = async (expr) => {
  const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true, userGesture: true });
  if (r.result?.exceptionDetails) throw new Error(`page threw on: ${expr.slice(0, 80)}: ${r.result.exceptionDetails.exception?.description || r.result.exceptionDetails.text}`);
  return r.result?.result?.value;
};
const shot = async (name) => {
  if (!shots) return;
  const r = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true });
  if (r.result?.data) writeFileSync(join(shots, name), Buffer.from(r.result.data, 'base64'));
};
async function load(reload) {
  await send(reload ? 'Page.reload' : 'Page.navigate', reload ? { ignoreCache: true } : { url: pageUrl });
  for (let i = 0; i < 50; i++) { await sleep(100); if (await ev(`document.readyState === 'complete' && !!window.sfTestplan`).catch(() => false)) return true; }
  return false;
}

let fails = 0;
const check = (name, ok, info = '') => { console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${!ok && info ? ': ' + info : ''}`); if (!ok) fails++; };
const HOSTILE = '<img src=x onerror=alert(1)>';
const safe = (cid) => cid.replace(/[^A-Za-z0-9_-]/g, '-');
const click = (cid, v) => ev(`document.querySelector('label[for="r-${safe(cid)}-${v}"]').click()`);
const markOf = (cid) => ev(`(document.querySelector('input[name="r-${safe(cid)}"]:checked')||{}).value||''`);
const openN = () => ev(`+document.getElementById('tally').getAttribute('data-open')`);
const liHas = (cid, cls) => ev(`document.querySelector('li.check[data-id="${cid}"]').classList.contains('${cls}')`);
const noteOf = (cid) => ev(`document.getElementById('n-${safe(cid)}').value`);
const stored = () => ev(`(()=>{try{return JSON.parse(localStorage.getItem(sfTestplan.key)||'null')}catch(e){return 'blocked'}})()`);
const msg = () => ev(`(document.getElementById('toolmsg')||{}).textContent||''`);
async function typeNote(cid, text) {
  await ev(`(()=>{const t=document.getElementById('n-${safe(cid)}'); t.focus(); t.select();})()`);
  await send('Input.insertText', { text });
  await ev(`document.getElementById('n-${safe(cid)}').blur()`);
}
async function setFile(path) {
  const doc = await send('DOM.getDocument', {});
  const q = await send('DOM.querySelector', { nodeId: doc.result.root.nodeId, selector: '#importfile' });
  await send('DOM.setFileInputFiles', { nodeId: q.result.nodeId, files: [path] });
  for (let i = 0; i < 30; i++) { await sleep(100); if ((await msg()).length) return; }
}

try {
  await send('Runtime.enable'); await send('Page.enable'); await send('DOM.enable');
  await send('Emulation.setFocusEmulationEnabled', { enabled: true });  // headless pages lack focus, which blocks the clipboard
  await send('Browser.grantPermissions', { permissions: ['clipboardReadWrite', 'clipboardSanitizedWrite'] }).catch(() => { });
  if (!(await load(false))) { console.log(`FAIL the page loads with its script (window.sfTestplan missing): ${file}`); finish(1); }
  // Start from empty marks: the fixed profile keeps localStorage between runs.
  await ev(`localStorage.removeItem(sfTestplan.key)`); await load(true);

  const KEY = await ev(`sfTestplan.key`);
  const run = await ev(`JSON.parse(document.getElementById('tp-config').textContent).run`);
  const planId = await ev(`JSON.parse(document.getElementById('tp-config').textContent).plan || ''`);
  check('storage key is sf-test-plan:<run>[:<plan>]', KEY === `sf-test-plan:${run}` + (planId ? `:${planId}` : ''), KEY);
  const ids = await ev(`[...document.querySelectorAll('li.check')].map(li=>li.getAttribute('data-id'))`);
  const hasSmoke = await ev(`!!document.getElementById('smoke')`);
  const smokeIds = await ev(`[...document.querySelectorAll('#smoke li.check')].map(li=>li.getAttribute('data-id'))`);
  const deepIds = await ev(`[...document.querySelectorAll('#deep li.check')].map(li=>li.getAttribute('data-id'))`);
  check('every check has Pass/Fail/Skip and a note box', await ev(`[...document.querySelectorAll('li.check')].every(li=>li.querySelectorAll('.seg[role=radiogroup] input[type=radio]').length===3 && li.querySelectorAll('.seg label').length===3 && !!li.querySelector('.note textarea[aria-label]'))`));
  const open0 = await openN();
  check('"not run" counts only smoke checks when there is a smoke test', hasSmoke ? open0 === smokeIds.length : open0 === ids.length, `open ${open0}, smoke ${smokeIds.length}, all ${ids.length}`);
  check('the save line says marks save in this browser', /saved in this browser/i.test(await ev(`document.getElementById('saved').textContent`)));

  const a = (smokeIds[0] || ids[0]), b = (smokeIds[1] || ids[1]), c = (smokeIds[2] || ids[2]);
  await click(a, 'pass'); await sleep(100);
  check('a click marks Pass', (await markOf(a)) === 'pass' && (await openN()) === open0 - 1 && (await liHas(a, 'is-pass')));
  await click(a, 'pass'); await sleep(100);
  check('a second click on Pass clears it', (await markOf(a)) === '' && (await openN()) === open0 && !(await liHas(a, 'is-pass')) && (await liHas(a, 'is-open')));
  await click(a, 'pass'); await click(a, 'fail'); await sleep(100);
  check('changing Pass to Fail keeps Fail', (await markOf(a)) === 'fail' && (await liHas(a, 'is-fail')) && !(await liHas(a, 'is-pass')));
  await click(a, 'fail'); await sleep(100);
  check('a second click on Fail clears it', (await markOf(a)) === '');
  await click(a, 'skip');
  await typeNote(a, 'first note'); await sleep(100);
  await click(a, 'skip'); await sleep(100);
  const sa = (await stored())?.checks?.[a];
  check('clearing a mark keeps the note, and it is saved', (await noteOf(a)) === 'first note' && sa && sa.r === '' && sa.n === 'first note' && (await liHas(a, 'has-note')), JSON.stringify(sa));
  check('the save line says when marks were last saved', /Saved in this browser at \d{4}-\d\d-\d\d \d\d:\d\d/.test(await ev(`document.getElementById('saved').textContent`)));

  // notes are debounced: typing alone saves after a pause, without blur
  await ev(`(()=>{const t=document.getElementById('n-${safe(b)}'); t.focus();})()`);
  await send('Input.insertText', { text: 'typed slowly' });
  await sleep(1000);
  check('a typed note is saved after a short pause', (await stored())?.checks?.[b]?.n === 'typed slowly');
  await ev(`document.activeElement && document.activeElement.blur()`);

  // a hostile note stays text
  await click(c, 'pass');
  await typeNote(c, HOSTILE);
  check('a hostile note stays text', (await noteOf(c)) === HOSTILE && (await ev(`document.querySelectorAll('img').length`)) === 0);

  await click(a, 'pass'); await sleep(100);
  await load(true);
  check('reload keeps marks and notes', (await markOf(a)) === 'pass' && (await noteOf(a)) === 'first note' && (await markOf(c)) === 'pass' && (await noteOf(c)) === HOSTILE && (await noteOf(b)) === 'typed slowly' && (await liHas(a, 'is-pass')), `${await markOf(a)} ${await noteOf(a)} ${await markOf(c)}`);
  check('a hostile stored note stays text after reload', (await ev(`document.querySelectorAll('img').length`)) === 0);

  if (hasSmoke && deepIds.length) {
    await ev(`document.getElementById('deep').open = true`);
    const before = await openN();
    const passBefore = await ev(`+document.getElementById('tally').getAttribute('data-pass')`);
    await click(deepIds[0], 'pass'); await sleep(100);
    const t = await ev(`(()=>{const e=document.getElementById('tally');return {p:+e.getAttribute('data-pass'),f:+e.getAttribute('data-fail'),s:+e.getAttribute('data-skip'),o:+e.getAttribute('data-open'),tot:e.querySelector('.tally-total').textContent}})()`);
    check('marking a deep check makes it a full round: every check counts, against all checks',
      t.p === passBefore + 1 && t.p + t.f + t.s + t.o === ids.length && t.tot.includes(String(ids.length)), JSON.stringify(t));
    await click(deepIds[0], 'pass'); await sleep(100);
    check('clearing the deep check goes back to the smoke round', (await openN()) === before);
  }

  // Export: the real button, with the download caught in a work folder
  const dl = join(work, 'downloads'); mkdirSync(dl, { recursive: true });
  let dlr = await send('Browser.setDownloadBehavior', { behavior: 'allow', downloadPath: dl });
  if (dlr.error) dlr = await send('Page.setDownloadBehavior', { behavior: 'allow', downloadPath: dl });
  await ev(`document.querySelector('#tools button[data-act="export"]').click()`);
  let got = '';
  for (let i = 0; i < 50 && !got; i++) { await sleep(100); got = readdirSync(dl).find((f) => f.endsWith('.json')) || ''; }
  const nameRe = new RegExp(`^${run.replace(/[.]/g, '\\.')}-marks-\\d{8}-\\d{4}\\.json$`);
  check('Export downloads <run>-marks-<yyyymmdd-hhmm>.json', nameRe.test(got), got || '(no download)');
  let exp = null;
  try { exp = JSON.parse(readFileSync(join(dl, got), 'utf8')); } catch { exp = await ev(`sfTestplan.marks()`); }
  const ea = exp?.checks?.find((x) => x.id === a); const eb = exp?.checks?.find((x) => x.id === b);
  check('export follows FORMAT.md 3', exp && exp.format === 'sf-test-plan-marks/1' && exp.run === run && typeof exp.title === 'string' && /Z$/.test(exp.exported || '') && /^sf-test-plan/.test(exp.tool || '') && Array.isArray(exp.checks), JSON.stringify(exp).slice(0, 200));
  check('export holds every check with a mark or a note, and only those', exp && exp.checks.length === 3 && ea && ea.r === 'pass' && ea.n === 'first note' && eb && eb.r === '' && eb.n === 'typed slowly' && typeof ea.g === 'number' && typeof ea.t === 'string' && ea.t.length > 0 && ea.t.length <= 300 && /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$/.test(ea.at) && ea.src === 'page', JSON.stringify(exp?.checks));
  check('exported step text leaves out the Copy labels', exp && exp.checks.every((x) => !/Copy$/.test(x.t) && !/\dCopy/.test(x.t)));

  // Import through the real file input: newer wins, older is kept, unknown ids reported, log badge
  const d = smokeIds[3] || ids[3];
  await click(b, 'fail'); await sleep(50);  // b now has a fresh mark; the file's older one must lose
  const imp = {
    format: 'sf-test-plan-marks/1', run, title: 'x', exported: '2030-01-01T00:00:00Z', tool: 'sf-test-plan 0.1.0', extra: 'ignored',
    checks: [
      { id: a, r: 'skip', n: 'newer from file', t: '', g: 1, at: '2030-01-01T00:00:00Z', src: 'page', future: 1 },
      { id: b, r: 'pass', n: 'old from file', t: '', g: 1, at: '2000-01-01T00:00:00Z', src: 'page' },
      { id: d, r: 'pass', n: HOSTILE, t: HOSTILE, g: 2, at: '2030-01-01T00:00:00Z', src: 'log' },
      { id: '999.999', r: 'pass', n: '', t: 'not here', g: 999, at: '2030-01-01T00:00:00Z', src: 'page' },
      { id: HOSTILE, r: 'fail', n: '', t: '', g: 9, at: '2030-01-01T00:00:00Z', src: 'page' },
      { id: c, r: 'fail', n: 'from the log', t: '', g: 1, at: '2030-01-01T00:00:00Z', src: 'log' },
      { id: '__proto__', r: 'pass', n: '', t: '', g: 1, at: '2030-01-01T00:00:00Z', src: 'page' },
    ],
  };
  const impPath = join(work, 'import.json'); writeFileSync(impPath, JSON.stringify(imp));
  await setFile(impPath);
  const m1 = await msg();
  check('import: the newer mark from the file wins', (await markOf(a)) === 'skip' && (await noteOf(a)) === 'newer from file');
  check('import: a newer mark on the page is kept', (await markOf(b)) === 'fail' && (await noteOf(b)) === 'typed slowly');
  check('import: a newer log mark never replaces the tester\'s own mark', (await markOf(c)) === 'pass' && (await noteOf(c)) === HOSTILE);
  check('import: an id like __proto__ is reported as unknown', m1.includes('__proto__'), m1);
  check('import: unknown ids are reported, not added', /not on this page/.test(m1) && m1.includes('999.999') && (await ev(`!!document.querySelector('li.check[data-id="999.999"]')`)) === false, m1);
  check('import: a log mark shows "Checked from the log"', (await markOf(d)) === 'pass' && (await liHas(d, 'from-log')) && (await ev(`(document.querySelector('li.check[data-id="${d}"] .logbadge')||{}).textContent`)) === 'Checked from the log');
  check('import: hostile text stays text', (await noteOf(d)) === HOSTILE && m1.includes(HOSTILE) && (await ev(`document.querySelectorAll('img').length`)) === 0);
  check('import: the merged marks are saved', (await stored())?.checks?.[a]?.r === 'skip' && (await stored())?.checks?.[d]?.src === 'log');
  await click(d, 'pass'); await click(d, 'pass'); await sleep(50);
  check('changing a log mark by hand removes the badge', !(await liHas(d, 'from-log')) && !(await ev(`!!document.querySelector('li.check[data-id="${d}"] .logbadge')`)));

  // Another format is refused, and so is broken JSON
  const before2 = JSON.stringify(await stored());
  const r2 = await ev(`sfTestplan.importData({format:'sf-test-plan-marks/2',run:${JSON.stringify(run)},checks:[{id:${JSON.stringify(a)},r:'fail',n:'',at:'2040-01-01T00:00:00Z'}]})`);
  const p2 = join(work, 'v2.json'); writeFileSync(p2, JSON.stringify({ format: 'sf-test-plan-marks/2', run, checks: [] }));
  await ev(`document.getElementById('toolmsg').textContent=''`); await setFile(p2);
  const m2 = await msg();
  check('import refuses another major format with a clear message', r2 && r2.ok === false && /can't read/.test(r2.message) && /can't read/.test(m2) && JSON.stringify(await stored()) === before2 && (await markOf(a)) === 'skip', `${r2?.message} | ${m2}`);
  const r3 = await ev(`sfTestplan.importText('{not json')`);
  check('import refuses a file that is not JSON', r3 && r3.ok === false && /valid JSON/.test(r3.message));

  // A different run asks first: yes merges, no leaves everything alone
  dialogs.length = 0; dialogAnswer = true;
  const other = { format: 'sf-test-plan-marks/1', run: 'other-run', checks: [{ id: c, r: 'fail', n: 'other run', at: '2031-01-01T00:00:00Z', src: 'page' }] };
  const r4 = await ev(`sfTestplan.importData(${JSON.stringify(other)})`);
  check('import of another run asks, and merges on yes', dialogs.some((x) => x.type === 'confirm' && x.message.includes('other-run')) && r4.ok && (await markOf(c)) === 'fail', JSON.stringify(dialogs));
  dialogAnswer = false; other.checks[0].r = 'skip'; other.checks[0].at = '2032-01-01T00:00:00Z';
  const r5 = await ev(`sfTestplan.importData(${JSON.stringify(other)})`);
  check('import of another run changes nothing on no', r5.ok === false && (await markOf(c)) === 'fail');
  dialogAnswer = true;

  // Copy results and the Copy buttons on commands
  await ev(`document.querySelector('#tools button[data-act="copy"]').click()`); await sleep(400);
  const rep = await ev(`navigator.clipboard.readText().then(t=>t,()=>'')`) || await ev(`(document.getElementById('copy-fallback')||{}).value||''`);
  check('Copy results puts plain-text results on the clipboard', rep.includes(`(run ${run})`) && rep.includes(`${a} SKIP`) && rep.includes('Note: newer from file') && /\d+ pass, \d+ fail, \d+ skip, \d+ not run/.test(rep), rep.slice(0, 300));
  const cmds = await ev(`[...document.querySelectorAll('code.cmd')].map(x=>x.textContent.replace(/\\s+/g,' ').trim())`);
  const btnN = await ev(`[...document.querySelectorAll('code.cmd')].filter(x=>x.nextElementSibling && x.nextElementSibling.classList.contains('copycmd')).length`);
  check('every code.cmd has a Copy button (none on this page is fine)', btnN === cmds.length, `${btnN} of ${cmds.length}`);
  if (cmds.length) {
    await ev(`document.querySelector('.copycmd').scrollIntoView({block:'center'})`);
    await ev(`document.querySelector('.copycmd').click()`); await sleep(400);
    const label = await ev(`document.querySelector('.copycmd').textContent`);
    const clip = await ev(`navigator.clipboard.readText().then(t=>t,()=>'(clipboard not readable)')`);
    check('a Copy button puts the command on the clipboard', label === 'Copied' && clip === cmds[0], `button "${label}", clipboard "${clip}"`);
    await shot('copy-button.png');
  }
  check('Copy results leaves out the Copy labels', !cmds.some((x) => rep.includes(x + 'Copy') || rep.includes(x + ' Copy')));

  // Reset asks; no keeps everything, yes clears marks and storage
  dialogAnswer = false; await ev(`document.querySelector('#tools button[data-act="reset"]').click()`); await sleep(100);
  check('Reset asks first and keeps marks on no', (await markOf(a)) === 'skip');
  dialogAnswer = true; await ev(`document.querySelector('#tools button[data-act="reset"]').click()`); await sleep(100);
  check('Reset clears every mark, note and the stored copy on yes', (await ev(`document.querySelectorAll('.seg input:checked').length`)) === 0 && (await noteOf(a)) === '' && (await stored()) === null && (await openN()) === open0);

  // Everything marked Pass: the tally never goes past its total (code review, 2026-11-19)
  if (hasSmoke) await ev(`document.getElementById('deep') && (document.getElementById('deep').open = true)`);
  for (const id of ids) await click(id, 'pass');
  await sleep(100);
  const all = await ev(`(()=>{const e=document.getElementById('tally');return {p:+e.getAttribute('data-pass'),o:+e.getAttribute('data-open'),tot:e.querySelector('.tally-total').textContent}})()`);
  check('all checks marked Pass: pass equals the total and nothing is left', all.p === ids.length && all.o === 0 && all.tot.includes(String(ids.length)), JSON.stringify(all));
  dialogAnswer = true; await ev(`document.querySelector('#tools button[data-act="reset"]').click()`); await sleep(100);

  // Screenshots: desktop, then phone width with no sideways scroll, then dark mode
  await click(a, 'pass'); await click(b, 'fail'); await click(c, 'skip'); await sleep(50);
  await ev(`document.getElementById('deep') && (document.getElementById('deep').open = true)`);
  await ev(`scrollTo(0,0)`); await shot('desktop.png');
  await send('Emulation.setDeviceMetricsOverride', { width: 360, height: 780, deviceScaleFactor: 2, mobile: true });
  await sleep(300);
  const sw = await ev(`({sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth, iw: innerWidth})`);
  check('phone width 360px has no sideways scroll', sw.sw <= sw.cw && sw.cw <= 360, JSON.stringify(sw));
  await shot('phone-360.png');
  await send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-color-scheme', value: 'dark' }] });
  await sleep(200);
  check('dark mode is reported to the page', await ev(`matchMedia('(prefers-color-scheme: dark)').matches`));
  await shot('phone-360-dark.png');
  await send('Emulation.clearDeviceMetricsOverride'); await sleep(200);
  await shot('desktop-dark.png');
  await send('Emulation.setEmulatedMedia', { features: [] });

  // Storage blocked: the page still works in memory and says so
  await ev(`localStorage.removeItem(sfTestplan.key)`);
  const blocker = await send('Page.addScriptToEvaluateOnNewDocument', { source: `(()=>{const t=()=>{throw new DOMException('blocked by test','SecurityError')}; try{Object.defineProperty(window,'localStorage',{configurable:true,get:t});}catch(e){} for (const m of ['getItem','setItem','removeItem','key','clear']) { try{Storage.prototype[m]=t;}catch(e){} } })();` });
  await load(true);
  const savedTxt = await ev(`document.getElementById('saved').textContent`);
  check('blocked storage: the page says marks are not saved', savedTxt.includes("Marks aren't saved in this browser: use Export before closing.") && (await ev(`sfTestplan.storageOk()`)) === false, savedTxt);
  await click(a, 'pass'); await typeNote(a, 'in memory'); await sleep(100);
  const memExp = await ev(`sfTestplan.marks()`);
  check('blocked storage: marks, tally and export still work', (await markOf(a)) === 'pass' && (await openN()) === open0 - 1 && memExp.checks.some((x) => x.id === a && x.r === 'pass' && x.n === 'in memory'));
  await send('Page.removeScriptToEvaluateOnNewDocument', { identifier: blocker.result.identifier });
  await load(true);

  check('no alert or other unexpected dialog opened', !dialogs.some((x) => x.type === 'alert' || x.type === 'prompt'), JSON.stringify(dialogs));
  check('no page errors', errors.length === 0, errors.join(' | '));
} catch (e) {
  check('the test ran to the end', false, e && e.stack || String(e));
}

// Leave nothing behind in the shared profile.
try { await ev(`localStorage.removeItem(sfTestplan.key)`); } catch { }
console.log(fails ? `${fails} FAILED` : 'ALL PASSED');
finish(fails ? 1 : 0);
