/**
 * Grid Rebalancer — grid-rebalancer.js
 * Loaded by the admin module loader after grid-rebalancer.html is injected.
 * All logic is wrapped in an IIFE; public functions are exposed on window.
 */
(function () {

// ── colour palette — base colours for system states ────────
const GR_BASE_COLORS = {
  'Open':        { bg:'#f9fafb', text:'#9ca3af', border:'#e5e7eb' },
  'Blocked':     { bg:'#374151', text:'#ffffff', border:'#4b5563' },
  'Unavailable': { bg:'#9ca3af', text:'#f9fafb', border:'#6b7280' },
};

// Colour wheel for dynamically assigned service types
const GR_COLOR_WHEEL = [
  { bg:'#dbeafe', text:'#1d4ed8', border:'#93c5fd' },
  { bg:'#ede9fe', text:'#6d28d9', border:'#c4b5fd' },
  { bg:'#d1fae5', text:'#065f46', border:'#6ee7b7' },
  { bg:'#ffedd5', text:'#c2410c', border:'#fdba74' },
  { bg:'#fef9c3', text:'#854d0e', border:'#fde047' },
  { bg:'#fce7f3', text:'#9d174d', border:'#f9a8d4' },
  { bg:'#e0f2fe', text:'#0369a1', border:'#7dd3fc' },
];

// Build GR_COLORS dynamically from instance config + base colours
function buildGrColors() {
  const colors = Object.assign({}, GR_BASE_COLORS);
  const types  = (window._instanceConfig && window._instanceConfig.service_types) || [];
  types.forEach(function(st, idx) {
    colors[st.key] = GR_COLOR_WHEEL[idx % GR_COLOR_WHEEL.length];
    // Also register by label in case the grid uses labels
    if (st.label && st.label !== st.key) {
      colors[st.label] = colors[st.key];
    }
  });
  return colors;
}

function buildGrAssignTypes() {
  const types = (window._instanceConfig && window._instanceConfig.service_types) || [];
  if (types.length > 0) return types.map(function(st) { return st.key; });
  // Fallback: derive from what the grid API returns (populated after grLoad)
  return [];
}

let GR_COLORS       = buildGrColors();
let GR_ASSIGN_TYPES = buildGrAssignTypes();
const GR_LOCKED     = new Set(['Blocked', 'Unavailable']);
const GR_COVERAGE   = new Set(GR_ASSIGN_TYPES.slice(0, 3)); // first 3 types get overlap warning

// ── module state ───────────────────────────────────────────
let grFaculty        = [];   // [{id, name, targets}]
let grWeeks          = [];   // [{id, week_number, start_date, end_date, week_type}]
let grGrid           = {};   // { week_id: { faculty_id: assignment } }
let grOriginal       = {};   // deep-cloned snapshot of what came from the DB
let grHistory        = [];   // undo stack
let grDragSrc        = null; // { wid, fid, fi, val }
let grSidebarVisible = true;

// ── zoom state ─────────────────────────────────────────────
// Each level: { label, tableFont(px), colMin(px), rowMin(px), cellH(px) }
const GR_ZOOM_LEVELS = [
  { label: '50%',  tableFont: 7,  colMin: 40,  rowMin: 58,  cellH: 15 },
  { label: '65%',  tableFont: 8,  colMin: 50,  rowMin: 72,  cellH: 18 },
  { label: '80%',  tableFont: 9,  colMin: 62,  rowMin: 88,  cellH: 21 },
  { label: '90%',  tableFont: 10, colMin: 70,  rowMin: 96,  cellH: 24 },
  { label: '100%', tableFont: 11, colMin: 78,  rowMin: 108, cellH: 26 },
];
let grZoomIdx = 4; // default: 100% (matches original CSS)

// Ensure the drag tooltip div exists
(function ensureTip() {
  if (!document.getElementById('grDragTip')) {
    var tip = document.createElement('div');
    tip.id = 'grDragTip';
    document.body.appendChild(tip);
  }
})();

// ── public API (called by onclick="" and triggerModuleInit) ─
window.grLoad             = grLoad;
window.grToggleSidebar    = grToggleSidebar;
window.grUndo             = grUndo;
window.grReset            = grReset;
window.grSave             = grSave;
window.grZoomIn           = grZoomIn;
window.grZoomOut          = grZoomOut;
window.grToggleFullScreen = grToggleFullScreen;

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

    // Refresh colours/types from loaded data (handles case where config wasn't
    // seeded yet or service types came from the grid API response itself)
    if (GR_ASSIGN_TYPES.length === 0 && grFaculty.length > 0) {
      var observed = new Set();
      grFaculty.forEach(function(f) {
        if (f.targets) Object.keys(f.targets).forEach(function(k) { observed.add(k); });
      });
      GR_ASSIGN_TYPES = Array.from(observed);
      GR_COLORS = buildGrColors();
      GR_ASSIGN_TYPES.forEach(function(k, i) {
        if (!GR_COLORS[k]) GR_COLORS[k] = GR_COLOR_WHEEL[i % GR_COLOR_WHEEL.length];
      });
    }

    if (loadEl) loadEl.style.display = 'none';
    if (mainEl) mainEl.style.display = 'flex';

    var cntEl = document.getElementById('grSidebarWeekCount');
    if (cntEl) cntEl.textContent = grWeeks.length + ' wks';

    grApplyZoom();
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
  var balance   = grComputeBalance();

  // abbreviated lane labels for delta chips
  var GR_ABBREV = { 'MICU': 'M', 'APP-ICU': 'A', 'Consults': 'C', 'Procedures': 'P', 'Backup': 'B' };

  // find duplicate last names so we can add a first-initial disambiguator
  var lastNameCount = {};
  grFaculty.forEach(function(f) {
    var ln = f.name.split(' ').slice(1).join(' ');
    lastNameCount[ln] = (lastNameCount[ln] || 0) + 1;
  });

  // thead
  var head = '<thead><tr><th>Week / Dates</th>';
  grFaculty.forEach(function(f, fi) {
    var parts     = f.name.split(' ');
    var firstName = parts[0];
    var lastName  = parts.slice(1).join(' ');
    // show last name only; append ", F." when the last name is shared
    var displayName = (lastNameCount[lastName] > 1)
      ? lastName + ', ' + firstName[0] + '.'
      : lastName;

    var b       = balance[fi];
    var targets = f.targets || {};

    // delta chips: show only lanes where actual ≠ target; vanish when fully balanced
    var chips = GR_ASSIGN_TYPES.map(function(t) {
      var actual = b[t];
      var target = targets[t] || 0;
      if (target === 0) return '';          // no target set — skip
      var delta = actual - target;
      if (delta === 0) return '';           // perfectly on target — disappear
      var isOver = delta > 0;
      var bg     = isOver ? '#fee2e2' : '#dcfce7';
      var color  = isOver ? '#dc2626' : '#16a34a';
      var border = isOver ? '#fca5a5' : '#86efac';
      var label  = GR_ABBREV[t] + (isOver ? '+' + delta : delta); // negative delta carries its own '−'
      return '<span style="display:inline-block;font-size:8px;padding:1px 3px;border-radius:6px;' +
             'background:' + bg + ';color:' + color + ';border:1px solid ' + border + ';' +
             'font-weight:700;margin:1px 1px 0;line-height:1.4;" title="' + grEsc(t) + ': ' + actual +
             ' of ' + target + ' target">' + label + '</span>';
    }).join('');

    head += '<th>' +
      '<span style="display:block;font-size:10px;font-weight:700;">' + grEsc(displayName) + '</span>' +
      (chips ? '<div style="margin-top:2px;line-height:1.6;">' + chips + '</div>' : '') +
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

      // visual overrides: Open → clean white; Unavailable + Blocked → same dark grey, no text
      var isDark   = val === 'Unavailable' || val === 'Blocked';
      var cellBg   = isDark     ? '#6b7280'
                   : val === 'Open' ? '#ffffff'
                   : c.bg;
      var cellBord = isDark     ? '#6b7280'
                   : val === 'Open' ? '#f0f0f0'
                   : c.border;
      var cellText = isDark ? '' : (val === 'Open' ? '' : c.text);
      var label    = isDark ? '' : (val === 'Open' ? '' : val);

      var cls = ['gr-cell',
        locked ? 'gr-locked' : 'gr-draggable',
        isConf ? 'gr-conflict' : '',
        isCh   ? 'gr-changed'  : ''
      ].filter(Boolean).join(' ');

      var tip = grEsc(f.name) + '  ·  Wk ' + week.week_number + '  ·  ' + val +
                (locked ? '  locked' : '  ↕ drag to move');

      body += '<td class="' + cls + '"' +
        ' style="background:' + cellBg + '; border-color:' + cellBord + ';"' +
        ' data-wi="' + wi + '" data-fi="' + fi + '"' +
        ' data-wid="' + week.id + '" data-fid="' + f.id + '"' +
        (locked ? '' : ' draggable="true"') +
        ' title="' + tip + '">' +
        '<div class="gr-inner" style="color:' + cellText + ';">' + label + '</div>' +
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
    var b       = balance[fi];
    var targets = f.targets || {};
    var total   = GR_ASSIGN_TYPES.reduce(function(s, t) { return s + b[t]; }, 0);
    return '<div class="gr-frow">' +
      '<div class="gr-fname" title="' + grEsc(f.name) + '">' + grEsc(f.name) + '</div>' +
      '<div class="gr-fchips">' +
        GR_ASSIGN_TYPES.map(function(t) {
          var actual  = b[t];
          var target  = targets[t] || 0;
          var isOver  = target > 0 && actual > target;
          var isUnder = target > 0 && actual < target;
          // green when under target, red when over, else lane colour
          var bg     = isOver  ? '#fee2e2' : isUnder ? '#dcfce7' : GR_COLORS[t].bg;
          var color  = isOver  ? '#dc2626' : isUnder ? '#16a34a' : GR_COLORS[t].text;
          var border = isOver  ? '#fca5a5' : isUnder ? '#86efac' : GR_COLORS[t].border;
          var label  = target > 0 ? actual + '/' + target : String(actual);
          return '<div class="gr-fchip" style="background:' + bg + ';color:' + color +
                 ';border:1px solid ' + border + ';" title="' + grEsc(t) + ': ' + actual +
                 ' of ' + target + ' target">' + label + '</div>';
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

// ── zoom ───────────────────────────────────────────────────
function grApplyZoom() {
  var z = GR_ZOOM_LEVELS[grZoomIdx];

  // Inject (or update) a <style> tag so overrides are clean and reversible
  var styleEl = document.getElementById('grZoomStyle');
  if (!styleEl) {
    styleEl = document.createElement('style');
    styleEl.id = 'grZoomStyle';
    document.head.appendChild(styleEl);
  }
  styleEl.textContent = [
    '#grTable { font-size: ' + z.tableFont + 'px !important; }',
    '#grTable thead th { min-width: ' + z.colMin + 'px !important; font-size: ' + z.tableFont + 'px !important; padding: 4px 2px !important; }',
    '#grTable thead th:first-child { min-width: ' + z.rowMin + 'px !important; }',
    '#grTable tbody td:first-child { min-width: ' + z.rowMin + 'px !important; font-size: ' + z.tableFont + 'px !important; }',
    '.gr-cell { height: ' + z.cellH + 'px !important; font-size: ' + z.tableFont + 'px !important; }',
  ].join('\n');

  // Update label and button states
  var label = document.getElementById('grZoomLabel');
  if (label) label.textContent = z.label;
  var btnOut = document.getElementById('grZoomOutBtn');
  var btnIn  = document.getElementById('grZoomInBtn');
  if (btnOut) btnOut.disabled = (grZoomIdx <= 0);
  if (btnIn)  btnIn.disabled  = (grZoomIdx >= GR_ZOOM_LEVELS.length - 1);
}

function grZoomIn() {
  if (grZoomIdx < GR_ZOOM_LEVELS.length - 1) { grZoomIdx++; grApplyZoom(); }
}

function grZoomOut() {
  if (grZoomIdx > 0) { grZoomIdx--; grApplyZoom(); }
}

// ── full-screen ────────────────────────────────────────────
function grToggleFullScreen() {
  var mod = document.getElementById('grModule');
  var btn = document.getElementById('grFullScreenBtn');
  if (!mod) return;

  var entering = !mod.classList.contains('gr-fullscreen');
  mod.classList.toggle('gr-fullscreen', entering);

  if (btn) btn.textContent = entering ? '✕ Exit Full Screen' : '⛶';

  if (entering) {
    // Prevent the page behind from scrolling while fullscreen is active
    document.body.style.overflow = 'hidden';
    // Esc key exits
    mod._grEscHandler = function (e) { if (e.key === 'Escape') grToggleFullScreen(); };
    document.addEventListener('keydown', mod._grEscHandler);
  } else {
    document.body.style.overflow = '';
    if (mod._grEscHandler) {
      document.removeEventListener('keydown', mod._grEscHandler);
      delete mod._grEscHandler;
    }
  }
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
      bannerTx.textContent = '' + changes.size + ' unsaved change' + (changes.size !== 1 ? 's' : '');
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
  if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = 'Saving…'; }
  grHideAlert();

  try {
    var resp = await fetch('/api/admin/service-schedule/apply-grid-changes', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ year: parseInt(year), changes: payload, reason: 'Grid rebalancer' })
    });
    var rawText = await resp.text();
    var data;
    try { data = JSON.parse(rawText); }
    catch (parseErr) { throw new Error('HTTP ' + resp.status + ': ' + rawText.slice(0, 200)); }

    if (!resp.ok || !data.success) throw new Error(data.detail || data.message || 'Save failed');

    grOriginal = grDeepClone(grGrid);
    grHistory  = [];
    grRenderTable();
    grRenderSidebar();
    grUpdateToolbar();
    grShowAlert('Saved ' + data.applied + ' change(s) to the database.' +
      (data.skipped ? ' (' + data.skipped + ' skipped — locked cells)' : ''), 'success');

  } catch (err) {
    grShowAlert('Save failed: ' + err.message, 'error');
    console.error('[Grid Rebalancer] save error:', err);
  } finally {
    if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = 'Save to DB'; }
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
