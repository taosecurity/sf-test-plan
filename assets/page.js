(function () {
  "use strict";
  /* sf-test-plan page script (FORMAT.md sections 2 and 3).
     Adds Pass / Fail / Skip and a note box to every li.check, keeps the marks in this browser
     (localStorage "sf-test-plan:<run>", or in memory when storage is blocked), and runs the toolbar:
     Export (marks.json), Import (merge, newer "at" wins), Copy results (plain text) and Reset.
     Text from storage or an imported file is only ever set with textContent or value, never innerHTML.
     No libraries, no network. */

  var MARKS_FORMAT = "sf-test-plan-marks/1";
  var STORE_FORMAT = "sf-test-plan-store/1";
  var RESULTS = ["pass", "fail", "skip"];
  var NOTE_DELAY = 600;
  var MAX_NOTE = 20000;

  var CFG = {};
  try { CFG = JSON.parse(document.getElementById("tp-config").textContent) || {}; } catch (e) { CFG = {}; }
  var RUN = typeof CFG.run === "string" && CFG.run ? CFG.run : "plan";
  var TITLE = typeof CFG.title === "string" ? CFG.title : document.title;
  var TOOL = typeof CFG.tool === "string" ? CFG.tool : "sf-test-plan";
  /* Browsers share one storage area for every file:// page, so the key names the plan as well as the run
     (CFG.plan: a short hash of the plan's file name and run, made at build time). */
  var PLAN = typeof CFG.plan === "string" && /^[0-9a-f]{1,32}$/.test(CFG.plan) ? CFG.plan : "";
  var KEY = "sf-test-plan:" + RUN + (PLAN ? ":" + PLAN : "");

  /* ---------- small helpers ---------- */
  function $(id) { return document.getElementById(id); }
  function nowIso() { return new Date().toISOString().replace(/\.\d{3}Z$/, "Z"); }
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function localStamp(d) {
    return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()) + " " + pad(d.getHours()) + ":" + pad(d.getMinutes());
  }
  function fileStamp(d) {
    return "" + d.getFullYear() + pad(d.getMonth() + 1) + pad(d.getDate()) + "-" + pad(d.getHours()) + pad(d.getMinutes());
  }
  function timeOf(iso) { var t = Date.parse(iso); return isNaN(t) ? -Infinity : t; }
  function clean(s) { return String(s).replace(/\s+/g, " ").trim(); }
  function hasNote(s) { return !!(s && typeof s.n === "string" && s.n.trim()); }
  function hasAny(s) { return !!(s && (s.r || hasNote(s))); }

  /* ---------- storage (every access in try/catch) ---------- */
  var storageOk = false;
  try {
    var probe = "sf-test-plan:__probe__";
    window.localStorage.setItem(probe, "1");
    window.localStorage.removeItem(probe);
    storageOk = true;
  } catch (e) { storageOk = false; }

  var state = {};       /* id -> {r, n, at, src, pn} for checks on this page */
  /* Stored entries for step numbers this page doesn't have (another build of the plan open in another tab, or an
     older one): written back as they are, so one build's save never erases another's. Marks are keyed by step
     number; a new build that changes its steps should get a new run: (README, FORMAT.md 2). */
  var others = Object.create(null);
  var lastSaved = "";   /* ISO time of the last write to storage */
  var storeDamaged = false;   /* the saved copy can't be read (found at start or after another tab's save); cleared by the next good read or save */
  /* This page found a saved copy in a newer store format (from a newer sf-test-plan). From then until the page is
     reloaded it reads and writes nothing: its marks live in memory only and the save line says to Export them.
     It never takes over another tab's save in that time, so nothing is merged, lost or brought back (FORMAT.md 2). */
  var storeNewer = false;

  /* Which store format a saved copy has: 1 for exactly "sf-test-plan-store/1" or no format; 2 (newer, never
     written over) for any other name that starts "sf-test-plan-store/<n>" with n of 1 or more, whatever follows
     (/2, /1.1, /1.0, /2-rc, even /1 with a trailing space); NaN (damaged, replaced by the next save) only when there
     is no such number (/0, /, /garbage). Settled rule: err toward never writing over (NOTES 0.2.0). */
  function storeMajor(data) {
    if (data.format === undefined || data.format === STORE_FORMAT) return 1;
    var m = typeof data.format === "string" ? /^sf-test-plan-store\/(\d+)/.exec(data.format) : null;
    return m && parseInt(m[1], 10) >= 1 ? 2 : NaN;
  }

  function sanitizeEntry(v) {
    if (!v || typeof v !== "object") return null;
    var r = RESULTS.indexOf(v.r) >= 0 ? v.r : "";
    var n = typeof v.n === "string" ? v.n.slice(0, MAX_NOTE) : "";
    var at = typeof v.at === "string" ? v.at : "";
    var src = v.src === "log" ? "log" : "page";
    /* pn: the note was typed by a person, so a log mark can stay a log mark while the tester's note survives a
       later log import. It is saved here and travels in exports as ns: "page" (FORMAT.md 3). */
    return { r: r, n: n, at: at, src: src, pn: v.pn === true || v.ns === "page" };
  }
  /* Reads the saved marks into state (this page's steps) and others. If storage can't be read or holds damaged
     or newer-format data, others is left as it was, so marks this tab already holds aren't lost.
     Returns "ok", "empty" (nothing saved), "damaged" (saved data can't be read), "newer" (this page found a
     newer store format, now or earlier, and is memory-only until reload: storage isn't read again and nothing is
     written, so this says nothing about what storage holds now) or "unavailable" (no storage). */
  function readStore() {
    if (!storageOk) return "unavailable";
    if (storeNewer) return "newer";   /* memory only until reload */
    var raw = null;
    try { raw = window.localStorage.getItem(KEY); } catch (e) { storageOk = false; return "unavailable"; }
    if (!raw) { others = Object.create(null); lastSaved = ""; storeDamaged = false; return "empty"; }
    var data = null;
    try { data = JSON.parse(raw); } catch (e) { data = null; }
    var major = data && typeof data === "object" ? storeMajor(data) : NaN;
    if (major > 1) { lastSaved = ""; storeDamaged = false; storeNewer = true; return "newer"; }
    if (major !== 1 || !data.checks || typeof data.checks !== "object") { lastSaved = ""; storeDamaged = true; return "damaged"; }
    others = Object.create(null);
    Object.keys(data.checks).forEach(function (id) {
      var s = sanitizeEntry(data.checks[id]);
      if (!s || !hasAny(s) || id.length > 40) return;
      if (Object.prototype.hasOwnProperty.call(byId, id)) state[id] = s;
      else others[id] = s;
    });
    lastSaved = typeof data.saved === "string" ? data.saved : "";
    storeDamaged = false;
    return "ok";
  }
  var dirty = {};   /* ids changed here and not yet written (a note waiting for its pause) */
  function writeStore() {
    dirty = {};
    if (!storageOk || storeNewer) { sayStatus(); return; }   /* never write over a newer sf-test-plan's saved copy */
    var keep = Object.create(null);
    Object.keys(others).forEach(function (id) { keep[id] = others[id]; });
    Object.keys(state).forEach(function (id) { if (hasAny(state[id])) keep[id] = state[id]; });
    try {
      if (Object.keys(keep).length) {
        lastSaved = nowIso();
        window.localStorage.setItem(KEY, JSON.stringify({ format: STORE_FORMAT, run: RUN, saved: lastSaved, checks: keep }));
      } else {
        window.localStorage.removeItem(KEY);
        lastSaved = "";
      }
      storeDamaged = false;
    } catch (e) {
      storageOk = false;  /* blocked or full: carry on in memory */
    }
    sayStatus();
  }

  var savedEl = $("saved");
  function sayStatus(extra) {
    if (!savedEl) return;
    var text, cls;
    if (!storageOk) {
      text = "Marks aren't saved in this browser: use Export before closing.";
      cls = "saved warn";
    } else if (storeNewer) {
      text = "This page found marks saved in this browser by a newer sf-test-plan, so it leaves them as they are and doesn't save the marks shown here. Use Export to keep them, or open the plan with that newer version.";
      cls = "saved warn";
    } else if (storeDamaged) {
      text = "The saved copy in this browser can't be read. Your next saved change replaces it; use Export to keep a copy.";
      cls = "saved warn";
    } else if (lastSaved) {
      text = "Saved in this browser at " + localStamp(new Date(timeOf(lastSaved))) + ".";
      cls = "saved ok";
    } else {
      text = "Marks are saved in this browser as you go.";
      cls = "saved";
    }
    savedEl.textContent = extra ? text + " " + extra : text;
    savedEl.className = cls;
  }

  /* ---------- message line under the toolbar ---------- */
  var tools = $("tools");
  var msgEl = $("toolmsg");
  if (!msgEl) {
    msgEl = document.createElement("div");
    msgEl.id = "toolmsg";
    msgEl.className = "toolmsg";
    msgEl.setAttribute("role", "status");
    msgEl.setAttribute("aria-live", "polite");
    if (tools && tools.parentNode) tools.parentNode.insertBefore(msgEl, tools.nextSibling);
    else document.body.appendChild(msgEl);
  }
  function say(text, kind) {
    msgEl.textContent = text;
    msgEl.className = "toolmsg" + (kind ? " " + kind : "");
    var old = $("copy-fallback");
    if (old) old.parentNode.removeChild(old);
  }

  /* ---------- the checks ---------- */
  var checks = Array.prototype.slice.call(document.querySelectorAll("li.check"));
  var byId = {};
  var hasSmoke = !!$("smoke");

  function stepText(li) {
    var d = li.querySelector(".what > .step") || li.querySelector(".what > div:not(.group-intro)");
    if (!d) return "";
    var c = d.cloneNode(true);
    Array.prototype.forEach.call(c.querySelectorAll(".copycmd"), function (b) { b.parentNode.removeChild(b); });
    return clean(c.textContent).slice(0, 300);
  }
  function groupOf(li) {
    var g = parseInt(li.getAttribute("data-group"), 10);
    return isNaN(g) ? 0 : g;
  }
  function inDeep(li) { return hasSmoke && !!li.closest("#deep"); }

  checks.forEach(function (li) {
    var id = li.getAttribute("data-id");
    if (!id || byId[id]) return;
    var safe = id.replace(/[^A-Za-z0-9_-]/g, "-");
    var seg = document.createElement("div");
    seg.className = "seg";
    seg.setAttribute("role", "radiogroup");
    seg.setAttribute("aria-label", "Result for check " + id);
    var radios = {};
    RESULTS.forEach(function (v) {
      var inp = document.createElement("input");
      inp.type = "radio";
      inp.name = "r-" + safe;
      inp.value = v;
      inp.id = "r-" + safe + "-" + v;
      var lab = document.createElement("label");
      lab.setAttribute("for", inp.id);
      lab.className = "seg-" + v;
      lab.textContent = v.charAt(0).toUpperCase() + v.slice(1);
      inp.addEventListener("change", function () {
        if (!inp.checked) return;
        setMark(id, v);
      });
      /* A second click on the mark already chosen clears it. On a new choice the click comes before
         the change event, so the state still holds the old mark; only a repeat click matches. */
      inp.addEventListener("click", function () {
        if (state[id] && state[id].r === v) { inp.checked = false; setMark(id, ""); }
      });
      seg.appendChild(inp);
      seg.appendChild(lab);
      radios[v] = inp;
    });
    li.appendChild(seg);

    var nd = document.createElement("div");
    nd.className = "note";
    var ta = document.createElement("textarea");
    ta.id = "n-" + safe;
    ta.rows = 2;
    ta.placeholder = "Note (what you saw)";
    ta.setAttribute("aria-label", "Note for check " + id);
    var timer = null;
    ta.addEventListener("input", function () {
      var s = entry(id);
      s.n = ta.value.slice(0, MAX_NOTE);
      s.at = nowIso();  /* any change moves the time, so Export/Import carries the note (newer wins) */
      s.pn = true;      /* a person's note; the mark keeps its own source (page or log) */
      dirty[id] = true;
      paintClasses(id);
      clearTimeout(timer);
      timer = setTimeout(function () { timer = null; writeStore(); }, NOTE_DELAY);
      pendingNotes[id] = function () { if (timer) { clearTimeout(timer); timer = null; writeStore(); } };
    });
    ta.addEventListener("blur", function () { if (timer) { clearTimeout(timer); timer = null; writeStore(); } });
    nd.appendChild(ta);
    li.appendChild(nd);

    byId[id] = { li: li, radios: radios, ta: ta, badge: null };
  });

  var pendingNotes = {};
  function flushNotes() {
    Object.keys(pendingNotes).forEach(function (id) { pendingNotes[id](); });
    pendingNotes = {};
  }
  window.addEventListener("pagehide", flushNotes);
  window.addEventListener("beforeunload", flushNotes);

  function entry(id) {
    if (!state[id]) state[id] = { r: "", n: "", at: "", src: "page" };
    return state[id];
  }
  function setMark(id, v) {
    var s = entry(id);
    s.r = v;
    s.at = nowIso();
    s.src = "page";   /* a mark the tester sets by hand is no longer "from the log" */
    if (!hasAny(s)) delete state[id];
    paint(id);
    tally();
    writeStore();
  }

  /* ---------- painting ---------- */
  function paintClasses(id) {
    var w = byId[id];
    if (!w) return;
    var s = state[id] || {};
    var li = w.li;
    RESULTS.forEach(function (v) { li.classList.toggle("is-" + v, s.r === v); });
    li.classList.toggle("is-open", !s.r);
    li.classList.toggle("has-note", hasNote(s));
    var fromLog = s.src === "log" && !!s.r;
    li.classList.toggle("from-log", fromLog);
    if (fromLog && !w.badge) {
      w.badge = document.createElement("span");
      w.badge.className = "logbadge";
      w.badge.textContent = "Checked from the log";
      var what = li.querySelector(".what");
      if (what) what.appendChild(w.badge); else li.insertBefore(w.badge, li.firstChild);
    } else if (!fromLog && w.badge) {
      w.badge.parentNode.removeChild(w.badge);
      w.badge = null;
    }
  }
  function paint(id, force) {
    var w = byId[id];
    if (!w) return;
    var s = state[id] || {};
    RESULTS.forEach(function (v) { w.radios[v].checked = (s.r === v); });
    if (force || document.activeElement !== w.ta) w.ta.value = s.n || "";
    paintClasses(id);
  }
  function paintAll(force) { Object.keys(byId).forEach(function (id) { paint(id, force); }); tally(); }

  /* ---------- tally ---------- */
  var tallyEl = $("tally");
  var LABELS = { pass: "pass", fail: "fail", skip: "skip", open: "not run" };
  var tallyNums = {};
  if (tallyEl) {
    while (tallyEl.firstChild) tallyEl.removeChild(tallyEl.firstChild);
    ["pass", "fail", "skip", "open"].forEach(function (k) {
      var sp = document.createElement("span");
      sp.className = "tally-item tally-" + k;
      var b = document.createElement("b");
      b.textContent = "0";
      sp.appendChild(b);
      sp.appendChild(document.createTextNode(" " + LABELS[k]));
      tallyEl.appendChild(sp);
      tallyEl.appendChild(document.createTextNode(" "));   /* reads right without CSS too */
      tallyNums[k] = b;
    });
    var tot = document.createElement("span");
    tot.className = "tally-total";
    tallyEl.appendChild(tot);
    tallyNums.total = tot;
  }
  /* With a smoke test, the round is a smoke round until any deep check is marked: then only smoke checks count,
     against the smoke total. Once a deep check is marked it is a full round: every check counts, against all
     checks. This matches `sf-test-plan import` ("Smoke test" / "Full test"). */
  function fullRound() {
    return Object.keys(byId).some(function (id) { return inDeep(byId[id].li) && state[id] && state[id].r; });
  }
  function counts() {
    var c = { pass: 0, fail: 0, skip: 0, open: 0 };
    var full = fullRound();
    Object.keys(byId).forEach(function (id) {
      if (!full && inDeep(byId[id].li)) return;   /* deep checks are optional in a smoke round */
      var s = state[id];
      if (s && s.r) c[s.r]++;
      else c.open++;
    });
    return c;
  }
  function tally() {
    var c = counts();
    if (!tallyEl) return c;
    var total = parseInt(tallyEl.getAttribute("data-total"), 10);
    if (isNaN(total) || fullRound()) total = checks.length;
    Object.keys(c).forEach(function (k) {
      tallyNums[k].textContent = String(c[k]);
      tallyEl.setAttribute("data-" + k, String(c[k]));
      tallyEl.style.setProperty("--" + k, String(c[k]));
    });
    tallyEl.style.setProperty("--total", String(total));
    tallyNums.total.textContent = "of " + total + (total === 1 ? " check" : " checks");
    return c;
  }

  /* ---------- clipboard ---------- */
  function copyText(text, done) {
    function fallback() {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.top = "0";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      var ok = false;
      try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
      document.body.removeChild(ta);
      done(ok);
    }
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function () { done(true); }, fallback);
      } else { fallback(); }
    } catch (e) { fallback(); }
  }

  /* Copy buttons on console and shell commands (the builder marks them code.cmd). */
  Array.prototype.forEach.call(document.querySelectorAll("code.cmd"), function (code) {
    var text = clean(code.textContent);
    if (!text) return;
    var b = document.createElement("button");
    b.type = "button";
    b.className = "copycmd";
    b.textContent = "Copy";
    b.setAttribute("aria-label", "Copy the command " + text);
    b.addEventListener("click", function () {
      copyText(text, function (ok) {
        if (!ok) {  /* copying is blocked here: select the command so Ctrl+C copies it */
          try {
            var r = document.createRange();
            r.selectNodeContents(code);
            var sel = window.getSelection();
            sel.removeAllRanges();
            sel.addRange(r);
          } catch (e) { /* nothing more to do */ }
        }
        b.textContent = ok ? "Copied" : "Selected: press Ctrl+C";
        setTimeout(function () { b.textContent = "Copy"; }, ok ? 1500 : 4000);
      });
    });
    if (code.nextSibling) code.parentNode.insertBefore(b, code.nextSibling);
    else code.parentNode.appendChild(b);
  });

  /* ---------- export ---------- */
  function marksData() {
    var out = [];
    checks.forEach(function (li) {
      var id = li.getAttribute("data-id");
      var s = state[id];
      if (!byId[id] || byId[id].li !== li || !hasAny(s)) return;
      var row = { id: id, r: s.r || "", n: s.n || "", t: stepText(li), g: groupOf(li), at: s.at || nowIso(), src: s.src === "log" ? "log" : "page" };
      if (s.pn && s.n) row.ns = "page";   /* the note was typed by a person (FORMAT.md 3) */
      out.push(row);
    });
    return { format: MARKS_FORMAT, run: RUN, title: TITLE, exported: nowIso(), tool: TOOL, checks: out };
  }
  function exportName(d) { return RUN + "-marks-" + fileStamp(d || new Date()) + ".json"; }
  function doExport() {
    flushNotes();
    var data = marksData();
    var text = JSON.stringify(data, null, 2) + "\n";
    var name = exportName();
    try {
      var blob = new Blob([text], { type: "application/json" });
      var url = URL.createObjectURL(blob);
      var a = document.createElement("a");
      a.href = url;
      a.download = name;
      a.style.display = "none";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(function () { URL.revokeObjectURL(url); }, 10000);
      say("Exported " + data.checks.length + (data.checks.length === 1 ? " check" : " checks") + " to " + name + " (your Downloads folder).", "ok");
    } catch (e) {
      say("Export didn't work in this browser. Use Copy results instead.", "warn");
    }
  }

  /* ---------- import ---------- */
  function importData(data, opts) {
    opts = opts || {};
    var ask = opts.confirm || function (q) { return window.confirm(q); };
    var res = { ok: false, added: 0, kept: 0, unknown: [], bad: 0, message: "" };
    if (!data || typeof data !== "object" || typeof data.format !== "string" || !/^sf-test-plan-marks\//.test(data.format)) {
      res.message = "This file isn't an sf-test-plan marks file (no \"format\": \"" + MARKS_FORMAT + "\"). Pick a file made by Export or by sf-test-plan logs.";
      return res;
    }
    var major = parseInt(data.format.split("/")[1], 10);
    if (major !== 1) {
      res.message = "This file is " + clean(data.format).slice(0, 60) + ", a format this page can't read (it reads " + MARKS_FORMAT + "). Rebuild the page with the sf-test-plan version that made the file.";
      return res;
    }
    if (!Array.isArray(data.checks)) {
      res.message = "This marks file has no \"checks\" list, so there is nothing to import.";
      return res;
    }
    var fileRun = typeof data.run === "string" ? data.run : "";
    if (fileRun !== RUN) {
      var q = "This file is for run \"" + clean(fileRun).slice(0, 64) + "\", but this page is run \"" + RUN + "\". Merge its marks into this page anyway?";
      if (!ask(q)) { res.message = "Import cancelled: the file is for another run."; res.cancelled = true; return res; }
    }
    data.checks.forEach(function (c) {
      if (!c || typeof c !== "object" || typeof c.id !== "string") { res.bad++; return; }
      if (!Object.prototype.hasOwnProperty.call(byId, c.id)) { res.unknown.push(c.id.slice(0, 40)); return; }
      var r = c.r === undefined || c.r === null ? "" : c.r;
      if (r !== "" && RESULTS.indexOf(r) < 0) { res.bad++; return; }
      var inc = sanitizeEntry({ r: r, n: c.n, at: c.at, src: c.src, ns: c.ns });   /* ns: the note's source survives Export/Import */
      if (!hasAny(inc)) { res.bad++; return; }
      var cur = state[c.id];
      /* A mark from the log never replaces the tester's own mark or note: a person's Fail beats a log line. */
      if (inc.src === "log" && hasAny(cur) && cur.src !== "log") { res.kept++; return; }
      if (hasAny(cur) && !(timeOf(inc.at) > timeOf(cur.at))) { res.kept++; return; }
      /* a newer log mark over an older log mark: take the result, keep a note the tester typed */
      if (inc.src === "log" && cur && cur.src === "log" && cur.pn && cur.n) { inc.n = cur.n; inc.pn = true; }
      state[c.id] = inc;
      res.added++;
    });
    res.ok = true;
    paintAll(true);
    writeStore();
    var parts = ["Imported " + res.added + (res.added === 1 ? " check" : " checks") + "."];
    if (res.kept) parts.push(res.kept + " kept as they were, because the marks here are newer or are your own (a log mark never replaces them).");
    if (res.unknown.length) parts.push(res.unknown.length + " not on this page and not added: " + res.unknown.slice(0, 12).join(", ") + (res.unknown.length > 12 ? ", ..." : "") + ".");
    if (res.bad) parts.push(res.bad + " skipped because they were damaged or empty.");
    if (storeNewer) parts.push("They aren't saved, because this page found marks saved by a newer sf-test-plan and saves nothing until it is reloaded; use Export to keep them.");
    res.message = parts.join(" ");
    return res;
  }
  function importText(text, opts) {
    var data;
    try { data = JSON.parse(text); } catch (e) {
      return { ok: false, added: 0, kept: 0, unknown: [], bad: 0, message: "This file isn't valid JSON, so it can't be a marks file. Pick a file made by Export or by sf-test-plan logs." };
    }
    return importData(data, opts);
  }
  var fileInput = $("importfile");
  if (fileInput) {
    fileInput.addEventListener("change", function () {
      var f = fileInput.files && fileInput.files[0];
      if (!f) return;
      var rd = new FileReader();
      rd.onload = function () {
        var res = importText(String(rd.result));
        say((f.name ? clean(f.name).slice(0, 120) + ": " : "") + res.message, res.ok ? "ok" : "warn");
        fileInput.value = "";
      };
      rd.onerror = function () { say("Couldn't read that file. Try again, or pick another copy.", "warn"); fileInput.value = ""; };
      rd.readAsText(f);
    });
  }

  /* ---------- copy results ---------- */
  function sectionTitle(li) {
    if (hasSmoke && li.closest("#smoke")) return "Smoke test";
    var s = li.closest("section");
    var h = s && s.querySelector("h2, h3");
    return h ? clean(h.textContent) : "";
  }
  function report() {
    flushNotes();
    var c = counts();
    var lines = [clean(TITLE || "Test plan") + " results (run " + RUN + ")"];
    lines.push(c.pass + " pass, " + c.fail + " fail, " + c.skip + " skip, " + c.open + " not run");
    var last = null;
    checks.forEach(function (li) {
      var id = li.getAttribute("data-id");
      if (!byId[id] || byId[id].li !== li) return;
      var s = state[id] || {};
      if (inDeep(li) && !hasAny(s)) return;   /* unmarked optional checks stay out of the report */
      var head = sectionTitle(li);
      if (head !== last) { lines.push(""); if (head) lines.push(head); last = head; }
      var r = s.r ? s.r.toUpperCase() : "NOT RUN";
      var line = id + " " + r + (s.src === "log" && s.r ? " (from the log)" : "") + ": " + stepText(li);
      if (hasNote(s)) line += "\n    Note: " + s.n.trim().replace(/\s*\n\s*/g, " / ");
      lines.push(line);
    });
    return lines.join("\n") + "\n";
  }
  function doCopy() {
    var text = report();
    copyText(text, function (ok) {
      if (ok) { say("Results copied. Paste them wherever you keep notes.", "ok"); return; }
      say("Copying is blocked here. Select the text below and copy it.", "warn");
      var ta = document.createElement("textarea");
      ta.id = "copy-fallback";
      ta.className = "copy-fallback";
      ta.readOnly = true;
      ta.rows = 10;
      ta.value = text;
      ta.setAttribute("aria-label", "Results to copy");
      msgEl.parentNode.insertBefore(ta, msgEl.nextSibling);
      ta.focus();
      ta.select();
    });
  }

  /* ---------- reset ---------- */
  function doReset(opts) {
    opts = opts || {};
    var ask = opts.confirm || function (q) { return window.confirm(q); };
    if (!ask("Clear every mark and note on this page (run " + RUN + ")? Use Export first if you want to keep them.")) {
      say("Nothing cleared.");
      return false;
    }
    /* Another tab may have saved while the question was open. With no dialog from here on: read storage again
       (so other builds' newest marks are the ones kept), clear this page's steps, stop the note timers (their
       write now carries the cleared state), and save. Marks for steps this page doesn't have always stay. */
    var read = readStore();
    state = {};
    dirty = {};
    flushNotes();
    paintAll(true);
    writeStore();
    var kept = Object.keys(others).length;
    if (!storageOk) say("Marks and notes on this page cleared here, but this browser isn't saving: reload may bring them back.", "warn");
    else if (read === "newer") say("Marks and notes on this page cleared here only. This page found marks saved by a newer sf-test-plan, so it saves nothing until it is reloaded.", "warn");
    else if (read === "damaged") say("Marks and notes on this page cleared. The saved copy in this browser couldn't be read, so it was replaced; Import an Export to bring back marks from other builds.", "warn");
    else say("Marks and notes on this page cleared." + (kept ? " " + kept + " saved mark" + (kept === 1 ? "" : "s") + " from another build (for steps this page doesn't have) kept." : ""), "ok");
    return true;
  }

  /* ---------- toolbar ---------- */
  if (tools) {
    tools.addEventListener("click", function (ev) {
      var b = ev.target && ev.target.closest ? ev.target.closest("button[data-act]") : null;
      if (!b || !tools.contains(b)) return;
      var act = b.getAttribute("data-act");
      if (act === "export") doExport();
      else if (act === "import") { if (fileInput) fileInput.click(); }
      else if (act === "copy") doCopy();
      else if (act === "reset") doReset();
    });
  }

  /* Another tab with the same page changed the marks. */
  window.addEventListener("storage", function (ev) {
    if (ev.key !== KEY && ev.key !== null) return;   /* null: all site data was cleared */
    /* Another tab saved, cleared or reset. Its save is the truth, so marks, clears and Reset carry over; only
       the note typed here and not yet written (dirty) is laid on top of its entry, and then saved. */
    var mine = state, oursWon = false;
    state = {};
    var read = readStore();
    if (read === "damaged" || read === "newer" || read === "unavailable") {
      /* Nothing readable to take over (or this page is memory-only after finding a newer format): keep the marks
         this tab shows, write nothing (so tabs never answer each other's saves), and let the save line say why. */
      state = mine;
      sayStatus();
      return;
    }
    Object.keys(dirty).forEach(function (id) {
      var a = mine[id] || { n: "" };   /* an emptied note counts too: deleting it is the change */
      var b = state[id] || { r: "", n: "", at: "", src: "page", pn: false };
      b.n = a.n || ""; b.pn = !!b.n;
      if ((a.at || "") > (b.at || "")) b.at = a.at;
      if (hasAny(b)) state[id] = b; else delete state[id];
      oursWon = true;
    });
    paintAll(false);
    if (oursWon) writeStore();
    sayStatus();
  });

  /* A link to #deep (or to anything inside it) opens the folded Deep checks box. */
  function openDeepFor(hash) {
    if (!hash || hash.length < 2) return;
    var name = hash.slice(1);
    try { name = decodeURIComponent(name); } catch (e) { /* a stray % in the address: use it as written */ }
    var d = $("deep"), t = document.getElementById(name);
    if (d && t && (t === d || d.contains(t))) d.open = true;
  }
  window.addEventListener("hashchange", function () { openDeepFor(location.hash); });
  document.addEventListener("click", function (ev) {
    var a = ev.target && ev.target.closest ? ev.target.closest('a[href^="#"]') : null;
    if (a) openDeepFor(a.getAttribute("href"));
  });

  /* ---------- start ---------- */
  readStore();
  paintAll(true);
  sayStatus();
  openDeepFor(location.hash);   /* after the marks load, so nothing here can stop them */

  /* Test hook (used by tests/page_test.mjs and handy in the console). Read-only views plus the same
     actions the buttons run; nothing here talks to the network. */
  window.sfTestplan = {
    version: 1,
    key: KEY,
    storageOk: function () { return storageOk; },
    marks: function () { return marksData(); },
    exportName: exportName,
    importData: importData,
    importText: importText,
    report: report,
    counts: counts,
    reset: doReset
  };
})();
