/**
 * Faculty Management Module — config-driven
 * Columns and form fields are generated from window._instanceConfig.
 */

let allFaculty      = [];
let currentEditingId = null;

// ── helpers ─────────────────────────────────────────────────────────────────

function fmConfig() {
  return window._instanceConfig || {};
}

function fmFacultyAttrs() {
  return fmConfig().faculty_attributes || [];
}

function fmServiceTypes() {
  return fmConfig().service_types || [];
}

// Build a form-group block for one extra_config attribute
function renderAttrField(attr, prefix, value) {
  const id   = prefix + '_' + attr.key;
  let input  = '';

  if (attr.type === 'select' && Array.isArray(attr.options)) {
    const opts = attr.options.map(o =>
      '<option value="' + o + '"' + (String(value) === String(o) ? ' selected' : '') + '>' + o + '</option>'
    ).join('');
    input = '<select id="' + id + '"><option value="">— Select —</option>' + opts + '</select>';
  } else if (attr.type === 'number') {
    input = '<input type="number" id="' + id + '" value="' + (value !== undefined ? value : '') + '" step="any">';
  } else if (attr.type === 'checkbox') {
    input = '<label style="display:flex;align-items:center;gap:8px;"><input type="checkbox" id="' + id + '" style="width:auto;"' + (value ? ' checked' : '') + '> ' + (attr.label || attr.key) + '</label>';
    return '<div class="form-group">' + input + '</div>';
  } else {
    input = '<input type="text" id="' + id + '" value="' + (value !== undefined ? value : '') + '">';
  }

  return '<div class="form-group"><label>' + (attr.label || attr.key) + '</label>' + input + '</div>';
}

// Collect extra_config values from a rendered set of fields
function collectExtraConfig(prefix) {
  const attrs  = fmFacultyAttrs();
  const result = {};
  attrs.forEach(function(attr) {
    const el = document.getElementById(prefix + '_' + attr.key);
    if (!el) return;
    if (attr.type === 'checkbox') {
      result[attr.key] = el.checked;
    } else if (attr.type === 'number') {
      const v = parseFloat(el.value);
      if (!isNaN(v)) result[attr.key] = v;
    } else {
      if (el.value !== '') result[attr.key] = el.value;
    }
  });
  return result;
}

// ── table header ─────────────────────────────────────────────────────────────

function buildTableHeader() {
  const attrs       = fmFacultyAttrs();
  const serviceTypes = fmServiceTypes();
  const head = document.getElementById('facultyTableHead');
  if (!head) return;

  let html = '<tr><th style="width:100px;">ID</th><th>Name</th><th>Email</th>';

  attrs.forEach(function(attr) {
    html += '<th style="width:120px;">' + (attr.label || attr.key) + '</th>';
  });

  serviceTypes.forEach(function(st) {
    const label = st.label || st.key;
    html += '<th style="width:100px;" title="Assigned / Target">' + label + '<br><small style="font-weight:400;color:#9ca3af;">(Act/Tgt)</small></th>';
  });

  html += '<th style="width:80px;">Status</th><th style="width:210px;">Actions</th></tr>';
  head.innerHTML = html;

  // Update colspan on any empty-state rows
  const totalCols = 4 + attrs.length + serviceTypes.length;
  document.querySelectorAll('#facultyTableBody td[colspan]').forEach(function(td) {
    td.setAttribute('colspan', totalCols);
  });
}

// ── table body ───────────────────────────────────────────────────────────────

function renderFacultyTable() {
  const tbody = document.getElementById('facultyTableBody');
  const attrs  = fmFacultyAttrs();
  const stypes = fmServiceTypes();
  const totalCols = 4 + attrs.length + stypes.length;

  if (allFaculty.length === 0) {
    tbody.innerHTML = '<tr><td colspan="' + totalCols + '" class="empty-state">' +
      '<div class="empty-state-icon">👥</div>' +
      '<div class="empty-state-title">No Providers</div>' +
      '<div class="empty-state-description">Add your first provider using the form above</div></td></tr>';
    return;
  }

  tbody.innerHTML = '';
  allFaculty.forEach(function(f) {
    const row     = document.createElement('tr');
    const extra   = f.extra_config || {};
    const swCounts = f.service_week_counts || {};

    const statusBadge    = f.active ? '<span class="badge badge-success">Active</span>' : '<span class="badge badge-danger">Inactive</span>';
    const adminBadge     = f.is_admin ? ' <span class="badge badge-info">Admin</span>' : '';
    const moonBadge      = f.moonlighter ? ' <span class="badge badge-warning">🌙 Moonlighter</span>' : '';

    let html = '<td style="font-weight:600;">' + (f.id || '') + '</td>' +
               '<td>' + (f.name || '') + adminBadge + moonBadge + '</td>' +
               '<td style="font-size:13px;">' + (f.email || '—') + '</td>';

    // Extra config attribute columns
    attrs.forEach(function(attr) {
      const val = extra[attr.key];
      html += '<td style="text-align:center;">' + (val !== undefined && val !== null ? val : '—') + '</td>';
    });

    // Service week columns (actual / target)
    stypes.forEach(function(st) {
      const key    = st.key;
      const actual = swCounts[key] || 0;
      const target = extra['target_' + key] || 0;
      if (target > 0) {
        const diff  = actual - target;
        const color = diff > 0 ? '#10b981' : diff < 0 ? '#ef4444' : '#6b7280';
        html += '<td style="text-align:center;"><span style="color:' + color + ';font-weight:600;">' + actual + '</span> / ' + target + '</td>';
      } else {
        html += '<td style="text-align:center;">' + actual + '</td>';
      }
    });

    html += '<td>' + statusBadge + '</td>';
    html += '<td><div style="display:flex;gap:6px;flex-wrap:wrap;">' +
      '<button class="btn-primary btn-sm" onclick="openEditFaculty(\'' + f.id + '\')">Edit</button>' +
      (f.active
        ? '<button class="btn-sm" style="background:#f59e0b;color:white;border:1px solid #f59e0b;" onclick="toggleFacultyStatus(\'' + f.id + '\',false)">Deactivate</button>'
        : '<button class="btn-success btn-sm" onclick="toggleFacultyStatus(\'' + f.id + '\',true)">Activate</button>') +
      '<button class="btn-danger btn-sm" onclick="deleteFaculty(\'' + f.id + '\')">Delete</button>' +
      '</div></td>';

    row.innerHTML = html;
    tbody.appendChild(row);
  });
}

// ── load ─────────────────────────────────────────────────────────────────────

async function loadFaculty() {
  try {
    showAlert('facultyAlert', '', 'clear');
    const response = await fetch('/api/admin/faculty', { credentials: 'same-origin' });
    if (!response.ok) throw new Error('Failed to load faculty');
    const data = await response.json();
    allFaculty = Array.isArray(data) ? data : (data.faculty || []);
    buildTableHeader();
    renderFacultyTable();
    const active = allFaculty.filter(function(f) { return f.active; }).length;
    document.getElementById('facultyCount').textContent = active + ' active / ' + allFaculty.length + ' total';
  } catch (err) {
    console.error('Error loading faculty:', err);
    showAlert('facultyAlert', 'Failed to load faculty: ' + err.message, 'error');
  }
}

// ── add form toggle ──────────────────────────────────────────────────────────

function toggleAddForm() {
  const form = document.getElementById('addFacultyForm');
  const visible = form.style.display !== 'none';
  form.style.display = visible ? 'none' : 'block';
  if (!visible) {
    // Inject dynamic attribute fields
    const container = document.getElementById('newFacultyExtraFields');
    const attrs = fmFacultyAttrs();
    if (attrs.length > 0) {
      let html = '<div class="form-grid" style="margin-top:12px;">';
      attrs.forEach(function(attr) {
        html += renderAttrField(attr, 'new', undefined);
      });
      html += '</div>';
      container.innerHTML = html;
    } else {
      container.innerHTML = '';
    }
  }
}

// ── add ──────────────────────────────────────────────────────────────────────

async function addFaculty() {
  const id    = document.getElementById('newFacultyId').value.trim().toLowerCase();
  const name  = document.getElementById('newFacultyName').value.trim();
  const email = document.getElementById('newFacultyEmail').value.trim();

  if (!id || !name || !email) {
    showAlert('facultyAlert', 'Please fill in ID, Name, and Email', 'error');
    return;
  }

  const extra = collectExtraConfig('new');

  try {
    const response = await fetch('/api/admin/faculty', {
      credentials: 'same-origin',
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id, name, email, extra_config: extra })
    });
    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || 'Failed to add provider');
    }
    showAlert('facultyAlert', 'Provider added successfully', 'success');
    document.getElementById('addFacultyForm').style.display = 'none';
    document.getElementById('newFacultyId').value = '';
    document.getElementById('newFacultyName').value = '';
    document.getElementById('newFacultyEmail').value = '';
    await loadFaculty();
  } catch (err) {
    showAlert('facultyAlert', 'Failed to add provider: ' + err.message, 'error');
  }
}

// ── edit ─────────────────────────────────────────────────────────────────────

function openEditFaculty(facultyId) {
  const f = allFaculty.find(function(x) { return x.id === facultyId; });
  if (!f) return;
  currentEditingId = facultyId;

  document.getElementById('editFacultyId').value    = f.id;
  document.getElementById('editFacultyName').value  = f.name || '';
  document.getElementById('editFacultyEmail').value = f.email || '';
  document.getElementById('editFacultyAdmin').checked             = !!f.is_admin;
  document.getElementById('editFacultyMoonlighter').checked       = !!f.moonlighter;
  document.getElementById('editFacultyDraftExempt').checked       = !!f.draft_exempt;
  document.getElementById('editFacultyMoonlightingPriority').value = f.moonlighting_priority || 2;
  document.getElementById('moonlightingPriorityGroup').style.display = f.moonlighter ? '' : 'none';

  // Inject dynamic extra_config fields
  const container = document.getElementById('editFacultyExtraFields');
  const attrs  = fmFacultyAttrs();
  const extra  = f.extra_config || {};
  if (attrs.length > 0) {
    let html = '<div class="form-grid">';
    attrs.forEach(function(attr) {
      html += renderAttrField(attr, 'edit', extra[attr.key]);
    });
    // Also show per-service-type targets
    fmServiceTypes().forEach(function(st) {
      const syntheticAttr = { key: 'target_' + st.key, label: (st.label || st.key) + ' Target (weeks)', type: 'number' };
      html += renderAttrField(syntheticAttr, 'edit', extra['target_' + st.key]);
    });
    html += '</div>';
    container.innerHTML = html;
  } else {
    container.innerHTML = '';
  }

  document.getElementById('editFacultyModal').classList.add('show');
}

function closeEditFacultyModal() {
  document.getElementById('editFacultyModal').classList.remove('show');
  currentEditingId = null;
}

function toggleMoonlightingPriority() {
  const isMoon = document.getElementById('editFacultyMoonlighter').checked;
  document.getElementById('moonlightingPriorityGroup').style.display = isMoon ? '' : 'none';
}

async function submitEditFaculty(event) {
  event.preventDefault();
  if (!currentEditingId) return;

  const extra = collectExtraConfig('edit');

  const payload = {
    name:                   document.getElementById('editFacultyName').value.trim(),
    email:                  document.getElementById('editFacultyEmail').value.trim() || null,
    is_admin:               document.getElementById('editFacultyAdmin').checked,
    moonlighter:            document.getElementById('editFacultyMoonlighter').checked,
    draft_exempt:           document.getElementById('editFacultyDraftExempt').checked,
    moonlighting_priority:  parseInt(document.getElementById('editFacultyMoonlightingPriority').value) || 2,
    extra_config:           extra,
  };

  try {
    const response = await fetch('/api/admin/faculty/' + currentEditingId, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || 'Failed to update');
    }
    showAlert('facultyAlert', 'Provider updated', 'success');
    closeEditFacultyModal();
    await loadFaculty();
  } catch (err) {
    alert('Failed to update: ' + err.message);
  }
}

// ── status / delete / admin toggle ───────────────────────────────────────────

async function toggleFacultyStatus(facultyId, newStatus) {
  if (!confirm('Are you sure you want to ' + (newStatus ? 'activate' : 'deactivate') + ' this provider?')) return;
  try {
    const response = await fetch('/api/admin/faculty/' + facultyId + '/status', {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_active: newStatus })
    });
    if (!response.ok) throw new Error((await response.json()).detail || 'Failed');
    await loadFaculty();
  } catch (err) {
    showAlert('facultyAlert', 'Failed: ' + err.message, 'error');
  }
}

async function deleteFaculty(facultyId) {
  const f = allFaculty.find(function(x) { return x.id === facultyId; });
  if (!confirm('Delete provider ' + (f ? f.name : facultyId) + '? This cannot be undone.')) return;
  try {
    const response = await fetch('/api/admin/faculty/' + facultyId, { method: 'DELETE' });
    if (!response.ok) throw new Error((await response.json()).detail || 'Failed');
    showAlert('facultyAlert', 'Provider deleted', 'success');
    await loadFaculty();
  } catch (err) {
    showAlert('facultyAlert', 'Failed: ' + err.message, 'error');
  }
}

async function toggleAdmin(facultyId) {
  const f = allFaculty.find(function(x) { return x.id === facultyId; });
  if (!f) return;
  const newStatus = !f.is_admin;
  if (!confirm((newStatus ? 'Grant admin to ' : 'Remove admin from ') + f.name + '?')) return;
  try {
    const response = await fetch('/api/admin/faculty/' + facultyId, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_admin: newStatus })
    });
    if (!response.ok) throw new Error((await response.json()).detail || 'Failed');
    await loadFaculty();
  } catch (err) {
    showAlert('facultyAlert', 'Failed: ' + err.message, 'error');
  }
}

// ── modal close helpers ───────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', function() {
  const modal = document.getElementById('editFacultyModal');
  if (modal) {
    modal.addEventListener('click', function(e) { if (e.target === modal) closeEditFacultyModal(); });
  }
});

document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') {
    const modal = document.getElementById('editFacultyModal');
    if (modal && modal.classList.contains('show')) closeEditFacultyModal();
  }
});

// ── global exports ────────────────────────────────────────────────────────────

window.loadFaculty             = loadFaculty;
window.toggleAddForm           = toggleAddForm;
window.addFaculty              = addFaculty;
window.openEditFaculty         = openEditFaculty;
window.closeEditFacultyModal   = closeEditFacultyModal;
window.submitEditFaculty       = submitEditFaculty;
window.toggleFacultyStatus     = toggleFacultyStatus;
window.deleteFaculty           = deleteFaculty;
window.toggleAdmin             = toggleAdmin;
window.toggleMoonlightingPriority = toggleMoonlightingPriority;
