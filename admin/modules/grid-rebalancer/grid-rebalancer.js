/**
 * Grid Rebalancer — grid-rebalancer.js
 * Loaded by the admin module loader after grid-rebalancer.html is injected.
 * All logic is wrapped in an IIFE; public functions are exposed on window.
 */
(function () {

// ── colour palette ─────────────────────────────────────────
const GR_COLORS = {
  'MICU':        { bg:'#dbeafe', text:'#1d4ed8', border:'#93c5fd' },
  'APP-ICU':     { bg:'#ede9fe', text:'#6d28d9', border:'#c4b5fd' },
  'Consults':    { bg:'#d1fae5', text:'#065f46', border:'#6ee7b7' },
  'Procedures':  { bg:'#ffedd5', text:'#c2410c', border:'#fdba74' },
  'Backup':      { bg:'#fef9c3', text:'#854d0e', border:'#fde047' },
  'Open':        { bg:'#f9fafb', text:'#9ca3af', border:'#e5e7eb' },
  'Blocked':     { bg:'#374151', text:'#ffffff', border:'#4b5563' },
  'Unavailable': { bg:'#9ca3af', text:'#f9fafb', border:'#6b7280' },
};
const GR_LOCKED       = new Set(['Blocked', 'Unavailable']);
const GR_ASSIGN_TYPES = ['MICU', 'APP-ICU', 'Consults', 'Procedures', 'Backup'];
const GR_COVERAGE     = new Set(['MICU', 'APP-ICU', 'Procedures']); // flag >1/week

// ── module state ───────────────────────────────────────────
let grFaculty        = [];   // [{id, name}]
let grWeeks          = [];   // [{id, week_number, start_date, end_date, week_type}]
let grGrid           = {};   // { week_id: { faculty_id: assignment } }
let grOriginal       = {};   // deep-cloned snapshot of what came from the DB
let grHistory        = [];   // undo stack
let grDragSrc        = null; // { wid, fid, fi, val }
let grSidebarVisible = true;

// Ensure the drag tooltip div exists
(function ensureTip() {
  if (!document.getElementById('grDragTip')) {
    var tip = document.createElement('div');
    tip.id = 'grDragTip';
    document.body.appendChild(tip);
  }
})();

// ── public API (called by onclick="" and triggerModuleInit) ─
window.grLoad          = grLoad;
window.grToggleSidebar = grToggleSidebar;
window.grUndo          = grUndo;
window.grReset         = grReset;
window.grSave          = grSave;

// ── load ───────────────────────────────────────────────────
async function grLoad() {
  var yearEl = document.getElementById('grYear');
  var year   = yearEl ? yearEl.value : '2026';

  var loadEl = document.getElementById('grLoading');
  var mainEl = document.getElementById('grMain');
  if (loadEl) { loadEl.style.display = 'block'; }
  if (mainEl) { mainEl.style.display = 'none';  }
  grHideAlert();

  try {
    var resp = await fetch('/api/admin/service-schedule/faculty-grid-json?year=' + year, {
      credentials: 'same-origin'
    });
    if (!resp.ok) {
      var errText = await resp.text();
      throw new Error('HTTP ' + resp.status + ': ' + errText);
    }
    var data = await resp.json();

    grFaculty  = data.faculty  || [];
    grWeeks    = data.weeks    || [];
    grGrid     = data.grid     || {};
    grOriginal = grDeepClone(grGrid);
    grHistory  = [];

    if (loadEl) loadEl.style.display = 'none';
    if (mainEl) mainEl.style.display = 'flex';

    var cntEl = document.getElementById('grSidebarWeekCount');
    if (cntEl) cntEl.textContent = grWeeks.length + ' wks';

    grRenderTable();
    grRenderSidebar();
    grUpdateToolbar();

  } catch (err) {
    if (loadEl) loadEl.style.display = 'none';
    grShowAlert('Failed to load schedule: ' + err.message, 'error');
    console.error('[Grid Rebalancer] load error:', err);
  }
}

// ── render table ───────────────────────────────────────────
function grRenderTable() {
  var table = document.getElementById('grTable');
  if (!table) return;

  var conflicts = grDetectConflicts();
  var changes   = grChangedCells();

  // thead
  var head = '<thead><tr><th>Week / Dates</th>';
  grFaculty.forEach(function(f) {
    var parts = f.name.split(' ');
    var first = parts[0];
    var last  = parts.slice(1).join(' ');
    head += '<th>' +
      '<span style="display:block;font-size:10px;font-weight:700;">' + grEsc(first) + '</span>' +
      '<span style="display:block;font-size:9px;font-weight:400;opacity:0.75;">' + grEsc(last) + '</span>' +
      '</th>';
  });
  head += '</tr></thead>';

  // tbody
  var body = '<tbody>';
  grWeeks.forEach(function(week, wi) {
    var wType = (week.week_type || 'regular');
    body += '<tr class="wt-' + wType + '">';
    // row header cell
    var sd = (week.start_date || '').substring(5).replace('-', '/');
    body += '<td>Wk ' + week.week_number + '<br>' +
      '<span style="font-size:9px;font-weight:400;opacity:0.8;">' + sd + '</span><br>' +
      '<span style="font-size:8px;font-weight:400;opacity:0.6;text-transform:capitalize;">' +
      wType.replace(/_/g, ' ') + '</span></td>';

    // faculty cells
    grFaculty.forEach(function(f, fi) {
      var val    = (grGrid[week.id] && grGrid[week.id][f.id]) || 'Open';
      var locked = GR_LOCKED.has(val);
      var ck     = wi + '-' + fi;
      var ck2    = week.id + '|' + f.id;
      var isConf = conflicts.has(ck);
      var isCh   = changes.has(ck2);
      var c      = GR_COLORS[val] || GR_COLORS['Open'];

      var cls = ['gr-cell',
        locked ? 'gr-locked' : 'gr-draggable',
        isConf ? 'gr-conflict' : '',
        isCh   ? 'gr-changed'  : ''
      ].filter(Boolean).join(' ');

      var label = val === 'Open' ? '' : val === 'Unavailable' ? '—' : val === 'Blocked' ? '■' : val;
      var tip   = grEsc(f.name) + '  ·  Wk ' + week.week_number + '  ·  ' + val +
                  (locked ? '  🔒 locked' : '  ↕ drag to move');

      body += '<td class="' + cls + '"' +
        ' style="background:' + c.bg + '; border-color:' + c.border + ';"' +
        ' data-wi="' + wi + '" data-fi="' + fi + '"' +
        ' data-wid="' + week.id + '" data-fid="' + f.id + '"' +
        (locked ? '' : ' draggable="true"') +
        ' title="' + tip + '">' +
        '<div class="gr-inner" style="color:' + c.text + ';">' + label + '</div>' +
        '</td>';
    });

    body += '</tr>';
  });
  body += '</tbody>';

  table.innerHTML = head + body;

  // attach drag/drop listeners
  table.querySelectorAll('td.gr-draggable').forEach(function(td) {
    td.addEventListener('dragstart', grOnDragStart);
    td.addEventListener('dragover',  grOnDragOver);
    td.addEventListener('dragleave', grOnDragLeave);
    td.addEventListener('drop',      grOnDrop);
    td.addEventListener('dragend',   grOnDragEnd);
  });
}

// ── drag handlers ──────────────────────────────────────────
function grOnDragStart(e) {
  var td  = e.currentTarget;
  var wid = td.dataset.wid;
  var fid = td.dataset.fid;
  var val = (grGrid[wid] && grGrid[wid][fid]) || 'Open';
  if (GR_LOCKED.has(val)) { e.preventDefault(); return; }
  grDragSrc = { wid: wid, fid: fid, fi: +td.dataset.fi, val: val };
  e.dataTransfer.effectAllowed = 'move';
  e.dataTransfer.setData('text/plain', val);
  td.classList.add('gr-src');
  var tip = document.getElementById('grDragTip');
  if (tip) {
    tip.textContent = 'Moving ' + val + ' from ' + grFaculty[+td.dataset.fi].name;
    tip.style.display = 'block';
  }
}

function grOnDragOver(e) {
  if (!grDragSrc) return;
  var td  = e.currentTarget;
  var val = (grGrid[td.dataset.wid] && grGrid[td.dataset.wid][td.dataset.fid]) || 'Open';
  if (GR_LOCKED.has(val)) return;
  e.preventDefault();
  e.dataTransfer.dropEffect = 'move';
  td.classList.add('gr-over');
}

function grOnDragLeave(e) {
  e.currentTarget.classList.remove('gr-over');
}

function grOnDrop(e) {
  e.preventDefault();
  var td = e.currentTarget;
  td.classList.remove('gr-over');
  if (!grDragSrc) return;
  var targetWid = td.dataset.wid;
  var targetFid = td.dataset.fid;
  var targetVal = (grGrid[targetWid] && grGrid[targetWid][targetFid]) || 'Open';
  if (GR_LOCKED.has(targetVal)) { grDragSrc = null; return; }
  if (grDragSrc.wid === targetWid && grDragSrc.fid === targetFid) { grDragSrc = null; return; }

  // save snapshot for undo
  grHistory.push(grDeepClone(grGrid));
  if (grHistory.length > 30) grHistory.shift();

  // MOVE: source becomes Open, target gets the assignment
  grGrid[targetWid][targetFid]           = grDragSrc.val;
  grGrid[grDragSrc.wid][grDragSrc.fid]  = 'Open';

  grDragSrc = null;
  grRenderTable();
  grRenderSidebar();
  grUpdateToolbar();
}

function grOnDragEnd(e) {
  e.currentTarget.classList.remove('gr-src');
  grDragSrc = null;
  var tip = document.getElementById('grDragTip');
  if (tip) tip.style.display = 'none';
  document.querySelectorAll('.gr-over').forEach(function(el) { el.classList.remove('gr-over'); });
}

// ── sidebar ────────────────────────────────────────────────
function grRenderSidebar() {
  var body = document.getElementById('grSidebarBody');
  if (!body) return;
  var balance = grComputeBalance();
  body.innerHTML = grFaculty.map(function(f, fi) {
    var b     = balance[fi];
    var total = GR_ASSIGN_TYPES.reduce(function(s, t) { return s + b[t]; }, 0);
    return '<div class="gr-frow">' +
      '<div class="gr-fname" title="' + grEsc(f.name) + '">' + grEsc(f.name) + '</div>' +
      '<div class="gr-fchips">' +
        GR_ASSIGN_TYPES.map(function(t) {
          var c = GR_COLORS[t];
          return '<div class="gr-fchip" style="background:' + c.bg + ';color:' + c.text +
                 ';border:1px solid ' + c.border + ';">' + b[t] + '</div>';
        }).join('') +
        '<div class="gr-ftotal">' + total + '</div>' +
      '</div>' +
    '</div>';
  }).join('');
}

function grToggleSidebar() {
  grSidebarVisible = !grSidebarVisible;
  var sb  = document.getElementById('grSidebar');
  var btn = document.getElementById('grToggleSidebar');
  if (sb)  sb.style.display = grSidebarVisible ? 'flex' : 'none';
  if (btn) btn.textContent  = grSidebarVisible ? 'Hide Balance' : 'Show Balance';
}

// ── toolbar state ──────────────────────────────────────────
function grUpdateToolbar() {
  var changes  = grChangedCells();
  var hasEdits = changes.size > 0;

  var undoBtn  = document.getElementById('grUndoBtn');
  var resetBtn = document.getElementById('grResetBtn');
  var saveBtn  = document.getElementById('grSaveBtn');
  var banner   = document.getElementById('grBanner');
  var bannerTx = document.getElementById('grBannerText');

  if (undoBtn)  { undoBtn.disabled  = grHistory.length === 0;
                  undoBtn.textContent = '↩ Undo (' + grHistory.length + ')'; }
  if (resetBtn)   resetBtn.disabled  = !hasEdits;
  if (saveBtn)    saveBtn.disabled   = !hasEdits;

  if (banner) {
    banner.style.display = hasEdits ? 'block' : 'none';
    if (bannerTx && hasEdits) {
      bannerTx.textContent = '⚠ ' + changes.size + ' unsaved change' + (changes.size !== 1 ? 's' : '');
    }
  }
}

// ── undo ───────────────────────────────────────────────────
function grUndo() {
  if (!grHistory.length) return;
  grGrid = grHistory.pop();
  grRenderTable();
  grRenderSidebar();
  grUpdateToolbar();
}

// ── reset ──────────────────────────────────────────────────
function grReset() {
  if (!confirm('Reset all unsaved changes back to the current database state?')) return;
  grGrid    = grDeepClone(grOriginal);
  grHistory = [];
  grRenderTable();
  grRenderSidebar();
  grUpdateToolbar();
}

// ── save ───────────────────────────────────────────────────
async function grSave() {
  var yearEl  = document.getElementById('grYear');
  var year    = yearEl ? yearEl.value : '2026';
  var changes = grChangedCells();
  if (!changes.size) return;

  var payload = [];
  changes.forEach(function(ck) {
    var parts = ck.split('|');
    var wid   = parts[0];
    var fid   = parts[1];
    payload.push({ week_id: wid, faculty_id: fid, new_assignment: grGrid[wid][fid] });
  });

  var saveBtn = document.getElementById('grSaveBtn');
  if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = '💾 Saving…'; }
  grHideAlert();

  try {
    var resp = await fetch('/api/admin/service-schedule/apply-grid-changes', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ year: parseInt(year), changes: payload, reason: 'Grid rebalancer' })
    });
    var data = await resp.json();

    if (!resp.ok || !data.success) throw new Error(data.detail || data.message || 'Save failed');

    grOriginal = grDeepClone(grGrid);
    grHistory  = [];
    grRenderTable();
    grRenderSidebar();
    grUpdateToolbar();
    grShowAlert('✅ Saved ' + data.applied + ' change(s) to the database.' +
      (data.skipped ? ' (' + data.skipped + ' skipped — locked cells)' : ''), 'success');

  } catch (err) {
    grShowAlert('❌ Save failed: ' + err.message, 'error');
    console.error('[Grid Rebalancer] save error:', err);
  } finally {
    if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = '💾 Save to DB'; }
    grUpdateToolbar();
  }
}

// ── helpers ────────────────────────────────────────────────
function grComputeBalance() {
  return grFaculty.map(function(f) {
    var counts = {};
    GR_ASSIGN_TYPES.forEach(function(t) { counts[t] = 0; });
    grWeeks.forEach(function(w) {
      var a = grGrid[w.id] && grGrid[w.id][f.id];
      if (GR_ASSIGN_TYPES.indexOf(a) !== -1) counts[a]++;
    });
    return counts;
  });
}

function grDetectConflicts() {
  var out = new Set();
  grWeeks.forEach(function(week, wi) {
    var byType = {};
    grFaculty.forEach(function(f, fi) {
      var a = grGrid[week.id] && grGrid[week.id][f.id];
      if (GR_COVERAGE.has(a)) {
        if (!byType[a]) byType[a] = [];
        byType[a].push(fi);
      }
    });
    Object.keys(byType).forEach(function(t) {
      if (byType[t].length > 1) {
        byType[t].forEach(function(fi) { out.add(wi + '-' + fi); });
      }
    });
  });
  return out;
}

function grChangedCells() {
  var out = new Set();
  grWeeks.forEach(function(week) {
    grFaculty.forEach(function(f) {
      var cur  = (grGrid[week.id]    || {})[f.id];
      var orig = (grOriginal[week.id] || {})[f.id];
      if (cur !== orig) out.add(week.id + '|' + f.id);
    });
  });
  return out;
}

function grDeepClone(g) {
  var clone = {};
  Object.keys(g).forEach(function(wid) {
    clone[wid] = Object.assign({}, g[wid]);
  });
  return clone;
}

function grShowAlert(msg, type) {
  var el = document.getElementById('grAlert');
  if (!el) return;
  el.textContent = msg;
  el.className   = 'alert alert-' + type;
  el.style.display = 'block';
  if (type === 'success') setTimeout(grHideAlert, 5000);
}

function grHideAlert() {
  var el = document.getElementById('grAlert');
  if (el) { el.style.display = 'none'; el.className = 'alert'; }
}

function grEsc(s) {
  return String(s || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── auto-load when the script first runs ───────────────────
grLoad();

})(); // end IIFE
