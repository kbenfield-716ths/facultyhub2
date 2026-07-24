/**
 * Shift Schedule Module — rotation management, period generation,
 * and the month grid for assigning providers/students to shifts.
 */

let ssRotations = [];
let ssProviders = [];
let ssCurrentRotationKey = null;
let ssViewYear = new Date().getFullYear();
let ssViewMonth = new Date().getMonth();   // 0-based
let ssPeriods = [];
let ssEditingKey = null;                   // rotation key being edited, null = new

const SS_FILL_COLORS = {
  understaffed: '#fee2e2',
  below_target: '#fef3c7',
  at_target:    '#d1fae5',
  above_target: '#dbeafe',
};

const SS_DOW = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

// ── PATCH helper (api.js doesn't provide one) ─────────────────────────────────

async function ssApiPatch(endpoint, data) {
  const response = await fetch(endpoint, {
    method: 'PATCH',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    if (handleAuthFailure(response.status)) return;
    throw new Error('API Error: ' + response.status + ' - ' + (await response.text()));
  }
  return await response.json();
}

// ── Init ──────────────────────────────────────────────────────────────────────

async function initShiftSchedule() {
  try {
    ssProviders = await getFaculty();
  } catch (e) {
    ssProviders = [];
    console.warn('Could not load providers:', e);
  }
  await ssLoadRotations();
  ssRenderRotationSelect();
  ssRenderRotationsList();
  await ssLoadGrid();
}

async function ssRefresh() {
  await initShiftSchedule();
}

async function ssLoadRotations() {
  try {
    ssRotations = await apiGet('/api/periods/rotations');
  } catch (e) {
    ssRotations = [];
    return handleApiError(e, 'ssAlert');
  }
  const shiftBased = ssRotations.filter(r => r.model === 'shift_based');
  if (!ssCurrentRotationKey || !shiftBased.find(r => r.key === ssCurrentRotationKey)) {
    ssCurrentRotationKey = shiftBased.length ? shiftBased[0].key : null;
  }
}

function ssCurrentRotation() {
  return ssRotations.find(r => r.key === ssCurrentRotationKey) || null;
}

function ssActiveProviders() {
  return ssProviders.filter(p => p.active).sort((a, b) => a.name.localeCompare(b.name));
}

// ── Rotation selector / month nav ─────────────────────────────────────────────

function ssRenderRotationSelect() {
  const sel = document.getElementById('ssRotationSelect');
  const shiftBased = ssRotations.filter(r => r.model === 'shift_based');
  sel.innerHTML = shiftBased.length
    ? shiftBased.map(r => `<option value="${r.key}" ${r.key === ssCurrentRotationKey ? 'selected' : ''}>${r.label}</option>`).join('')
    : '<option value="">No rotations yet</option>';
}

async function ssOnRotationChange() {
  ssCurrentRotationKey = document.getElementById('ssRotationSelect').value || null;
  await ssLoadGrid();
}

async function ssShiftMonth(delta) {
  ssViewMonth += delta;
  if (ssViewMonth < 0)  { ssViewMonth = 11; ssViewYear--; }
  if (ssViewMonth > 11) { ssViewMonth = 0;  ssViewYear++; }
  await ssLoadGrid();
}

function ssMonthRange() {
  const start = new Date(Date.UTC(ssViewYear, ssViewMonth, 1));
  const end = new Date(Date.UTC(ssViewYear, ssViewMonth + 1, 0));
  const iso = d => d.toISOString().slice(0, 10);
  return { start: iso(start), end: iso(end), days: end.getUTCDate() };
}

// ── Grid ──────────────────────────────────────────────────────────────────────

async function ssLoadGrid() {
  const label = document.getElementById('ssMonthLabel');
  label.textContent = new Date(ssViewYear, ssViewMonth, 1)
    .toLocaleString('en-US', { month: 'long', year: 'numeric' });

  const rotation = ssCurrentRotation();
  const empty = document.getElementById('ssGridEmpty');
  const table = document.getElementById('ssGridTable');
  if (!rotation) {
    empty.style.display = '';
    table.style.display = 'none';
    return;
  }
  empty.style.display = 'none';
  table.style.display = '';

  const { start, end } = ssMonthRange();
  try {
    ssPeriods = await apiGet(`/api/periods?rotation_key=${encodeURIComponent(rotation.key)}&start=${start}&end=${end}`);
  } catch (e) {
    return handleApiError(e, 'ssAlert');
  }
  ssRenderGrid(rotation);
}

function ssRenderGrid(rotation) {
  const head = document.getElementById('ssGridHead');
  const body = document.getElementById('ssGridBody');
  const shifts = rotation.shifts || [];

  head.innerHTML = '<tr><th style="width:110px;">Date</th>' +
    shifts.map(s =>
      `<th>${s.label}<br><small style="font-weight:400;color:#6b7280;">${s.start}–${s.end} · target ${s.target_slots}</small></th>`
    ).join('') + '</tr>';

  // Index periods by date|shift
  const byKey = {};
  ssPeriods.forEach(p => { byKey[p.period_date + '|' + p.shift_type] = p; });

  const { days } = ssMonthRange();
  if (!ssPeriods.length) {
    body.innerHTML = `<tr><td colspan="${shifts.length + 1}" style="text-align:center;color:#6b7280;padding:24px;">
      No periods generated for this month yet — click <strong>Generate This Month</strong> above.</td></tr>`;
    return;
  }

  let rows = '';
  for (let d = 1; d <= days; d++) {
    const dateObj = new Date(Date.UTC(ssViewYear, ssViewMonth, d));
    const dateStr = dateObj.toISOString().slice(0, 10);
    const dow = dateObj.getUTCDay();
    const weekend = (dow === 0 || dow === 6);
    rows += `<tr${weekend ? ' style="background:#f9fafb;"' : ''}>` +
      `<td style="white-space:nowrap;"><strong>${d}</strong> <span style="color:#6b7280;">${SS_DOW[dow]}</span></td>`;
    for (const shift of shifts) {
      const p = byKey[dateStr + '|' + shift.key];
      rows += ssRenderCell(p, rotation);
    }
    rows += '</tr>';
  }
  body.innerHTML = rows;
}

function ssRenderCell(period, rotation) {
  if (!period) {
    return '<td style="color:#d1d5db;text-align:center;">—</td>';
  }
  const bg = SS_FILL_COLORS[period.fill_state] || 'transparent';
  const providers = period.assignments.filter(a => a.role === 'provider');
  const students = period.assignments.filter(a => a.role === 'student');

  const chip = a =>
    `<span style="display:inline-flex;align-items:center;gap:4px;background:#fff;border:1px solid #d1d5db;border-radius:12px;padding:1px 8px;margin:1px;font-size:12px;${a.role === 'student' ? 'border-style:dashed;color:#6b7280;' : ''}">` +
    `${a.role === 'student' ? '🎓 ' : ''}${a.provider_name}` +
    `<a href="#" onclick="ssRemoveAssignment('${a.id}');return false;" title="Remove" style="color:#9ca3af;text-decoration:none;">×</a></span>`;

  const holiday = period.is_holiday ? ' <span title="Holiday">🎉</span>' : '';
  const count = `<a href="#" onclick="ssEditPeriod('${period.id}');return false;" title="Staffing: ${period.provider_count}/${period.target_slots} (min ${period.min_slots}, max ${period.max_slots}). Click to edit."
     style="font-size:11px;color:#374151;text-decoration:none;font-weight:600;">${period.provider_count}/${period.target_slots}${holiday}</a>`;

  return `<td style="background:${bg};min-width:170px;vertical-align:top;">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:2px;">
      ${count}
      <a href="#" onclick="ssShowAssignForm('${period.id}');return false;" title="Assign" style="text-decoration:none;font-weight:700;color:#2563eb;">+</a>
    </div>
    <div>${providers.map(chip).join('')}${students.map(chip).join('')}</div>
    <div id="ssAssign-${period.id}" style="display:none;margin-top:4px;"></div>
  </td>`;
}

// ── Assigning ─────────────────────────────────────────────────────────────────

function ssShowAssignForm(periodId) {
  // Close any other open assign forms
  document.querySelectorAll('[id^="ssAssign-"]').forEach(el => { el.style.display = 'none'; el.innerHTML = ''; });
  const holder = document.getElementById('ssAssign-' + periodId);
  const rotation = ssCurrentRotation();
  const period = ssPeriods.find(p => p.id === periodId);
  const assignedIds = new Set((period ? period.assignments : []).map(a => a.provider_id));
  const options = ssActiveProviders()
    .filter(p => !assignedIds.has(p.id))
    .map(p => `<option value="${p.id}">${p.name}</option>`).join('');
  const roleSelect = (rotation.roles || []).includes('student')
    ? `<select id="ssAssignRole-${periodId}" style="font-size:12px;padding:2px;"><option value="provider">Provider</option><option value="student">Student</option></select>`
    : `<input type="hidden" id="ssAssignRole-${periodId}" value="provider">`;
  holder.innerHTML =
    `<div style="display:flex;gap:4px;flex-wrap:wrap;align-items:center;">
       <select id="ssAssignProvider-${periodId}" style="font-size:12px;padding:2px;max-width:130px;">${options}</select>
       ${roleSelect}
       <button class="btn-primary btn-sm" style="padding:2px 8px;font-size:12px;" onclick="ssAssign('${periodId}')">Add</button>
     </div>`;
  holder.style.display = '';
}

async function ssAssign(periodId) {
  const providerId = document.getElementById('ssAssignProvider-' + periodId).value;
  const role = document.getElementById('ssAssignRole-' + periodId).value;
  if (!providerId) return;
  try {
    const result = await apiPost(`/api/periods/${periodId}/assignments`, { provider_id: providerId, role });
    if (result && result.warning) showAlert('ssAlert', result.warning, 'warning');
  } catch (e) {
    const msg = String(e.message || e);
    if (msg.includes('max staffing')) {
      if (confirm('This shift is at its maximum staffing. Raise the cap by 1 and assign anyway?')) {
        const period = ssPeriods.find(p => p.id === periodId);
        try {
          await ssApiPatch(`/api/periods/${periodId}`, { max_slots: (period ? period.max_slots : 3) + 1 });
          await apiPost(`/api/periods/${periodId}/assignments`, { provider_id: providerId, role });
        } catch (e2) {
          return handleApiError(e2, 'ssAlert');
        }
      }
    } else {
      return handleApiError(e, 'ssAlert');
    }
  }
  await ssLoadGrid();
}

async function ssRemoveAssignment(assignmentId) {
  try {
    await apiDelete(`/api/periods/assignments/${assignmentId}`);
  } catch (e) {
    return handleApiError(e, 'ssAlert');
  }
  await ssLoadGrid();
}

async function ssEditPeriod(periodId) {
  const period = ssPeriods.find(p => p.id === periodId);
  if (!period) return;
  const input = prompt(
    `Edit staffing for ${period.period_date} (${period.shift_type}).\n` +
    `Enter min,target,max — currently ${period.min_slots},${period.target_slots},${period.max_slots}:`,
    `${period.min_slots},${period.target_slots},${period.max_slots}`);
  if (input === null) return;
  const parts = input.split(',').map(s => parseInt(s.trim(), 10));
  if (parts.length !== 3 || parts.some(isNaN)) {
    return showAlert('ssAlert', 'Enter three numbers separated by commas, e.g. 1,2,3', 'error');
  }
  try {
    await ssApiPatch(`/api/periods/${periodId}`, { min_slots: parts[0], slots_needed: parts[1], max_slots: parts[2] });
  } catch (e) {
    return handleApiError(e, 'ssAlert');
  }
  await ssLoadGrid();
}

// ── Generation ────────────────────────────────────────────────────────────────

async function ssGenerateMonth() {
  const rotation = ssCurrentRotation();
  if (!rotation) return showAlert('ssAlert', 'Create a rotation first.', 'error');
  const { start, end } = ssMonthRange();
  try {
    const result = await apiPost('/api/periods/generate',
      { rotation_key: rotation.key, start_date: start, end_date: end });
    showAlert('ssAlert', `Generated ${result.created} new periods for ${rotation.label}.`, 'success');
  } catch (e) {
    return handleApiError(e, 'ssAlert');
  }
  await ssLoadGrid();
}

// ── Tabs ──────────────────────────────────────────────────────────────────────

function ssShowTab(tab) {
  document.getElementById('ssTabGrid').classList.toggle('active', tab === 'grid');
  document.getElementById('ssTabRotations').classList.toggle('active', tab === 'rotations');
  document.getElementById('ssTabBtnGrid').classList.toggle('active', tab === 'grid');
  document.getElementById('ssTabBtnRotations').classList.toggle('active', tab === 'rotations');
}

// ── Rotations management ──────────────────────────────────────────────────────

function ssRenderRotationsList() {
  const body = document.getElementById('ssRotationsBody');
  const count = document.getElementById('ssRotationCount');
  count.textContent = `${ssRotations.length} rotation${ssRotations.length === 1 ? '' : 's'} configured`;
  if (!ssRotations.length) {
    body.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#6b7280;padding:20px;">No rotations yet — create one to get started.</td></tr>';
    return;
  }
  body.innerHTML = ssRotations.map(r => {
    const shiftsDesc = (r.shifts || [])
      .map(s => `${s.label} (${s.min_slots}–${s.target_slots}–${s.max_slots})`)
      .join(', ') || '<span style="color:#9ca3af;">n/a</span>';
    return `<tr>
      <td><code>${r.key}</code></td>
      <td><span style="display:inline-block;width:10px;height:10px;border-radius:3px;background:${r.color || '#9ca3af'};margin-right:6px;"></span>${r.label}</td>
      <td>${r.model}</td>
      <td style="font-size:13px;">${shiftsDesc}</td>
      <td>${(r.roles || []).join(', ')}</td>
      <td>
        <button class="btn-secondary btn-sm" onclick="ssEditRotation('${r.key}')">✏️ Edit</button>
        <button class="btn-danger btn-sm" onclick="ssDeleteRotation('${r.key}')">🗑️</button>
      </td>
    </tr>`;
  }).join('');
}

function ssNewRotation() {
  ssEditingKey = null;
  document.getElementById('ssEditorTitle').textContent = 'New Rotation';
  document.getElementById('ssEditKey').value = '';
  document.getElementById('ssEditKey').disabled = false;
  document.getElementById('ssEditLabel').value = '';
  document.getElementById('ssEditColor').value = '#2563eb';
  document.getElementById('ssEditStudentRole').checked = false;
  document.getElementById('ssShiftRows').innerHTML = '';
  ssAddShiftRow({ key: 'day', label: 'Day', start: '07:00', end: '19:00', min_slots: 1, target_slots: 2, max_slots: 3 });
  ssAddShiftRow({ key: 'night', label: 'Night', start: '19:00', end: '07:00', min_slots: 1, target_slots: 2, max_slots: 3 });
  document.getElementById('ssRotationEditor').style.display = '';
}

function ssEditRotation(key) {
  const r = ssRotations.find(x => x.key === key);
  if (!r) return;
  ssEditingKey = key;
  document.getElementById('ssEditorTitle').textContent = `Edit Rotation — ${r.label}`;
  document.getElementById('ssEditKey').value = r.key;
  document.getElementById('ssEditKey').disabled = true;
  document.getElementById('ssEditLabel').value = r.label;
  document.getElementById('ssEditColor').value = r.color || '#2563eb';
  document.getElementById('ssEditStudentRole').checked = (r.roles || []).includes('student');
  document.getElementById('ssShiftRows').innerHTML = '';
  (r.shifts || []).forEach(s => ssAddShiftRow(s));
  document.getElementById('ssRotationEditor').style.display = '';
}

function ssAddShiftRow(shift) {
  const s = shift || { key: '', label: '', start: '07:00', end: '19:00', min_slots: 1, target_slots: 1, max_slots: 1 };
  const row = document.createElement('tr');
  row.className = 'ss-shift-row';
  row.innerHTML =
    `<td><input type="text" class="ss-sh-key" value="${s.key}" placeholder="day" style="width:90px;"></td>
     <td><input type="text" class="ss-sh-label" value="${s.label}" placeholder="Day Shift" style="width:110px;"></td>
     <td><input type="time" class="ss-sh-start" value="${s.start}" style="width:100px;"></td>
     <td><input type="time" class="ss-sh-end" value="${s.end}" style="width:100px;"></td>
     <td><input type="number" class="ss-sh-min" value="${s.min_slots}" min="0" max="20" style="width:56px;"></td>
     <td><input type="number" class="ss-sh-target" value="${s.target_slots}" min="0" max="20" style="width:56px;"></td>
     <td><input type="number" class="ss-sh-max" value="${s.max_slots}" min="0" max="20" style="width:56px;"></td>
     <td><button class="btn-danger btn-sm" onclick="this.closest('tr').remove()">×</button></td>`;
  document.getElementById('ssShiftRows').appendChild(row);
}

function ssCancelEdit() {
  document.getElementById('ssRotationEditor').style.display = 'none';
  ssEditingKey = null;
}

async function ssSaveRotation() {
  const key = document.getElementById('ssEditKey').value.trim();
  const label = document.getElementById('ssEditLabel').value.trim();
  if (!key || !label) return showAlert('ssAlert', 'Key and label are required.', 'error');
  if (!/^[a-z0-9_]+$/.test(key)) return showAlert('ssAlert', 'Key must be lowercase letters, numbers, underscores.', 'error');

  const shifts = [];
  for (const row of document.querySelectorAll('#ssShiftRows tr')) {
    const get = cls => row.querySelector('.' + cls).value;
    const shiftKey = get('ss-sh-key').trim();
    if (!shiftKey) continue;
    shifts.push({
      key: shiftKey,
      label: get('ss-sh-label').trim() || shiftKey,
      start: get('ss-sh-start'),
      end: get('ss-sh-end'),
      min_slots: parseInt(get('ss-sh-min'), 10) || 0,
      target_slots: parseInt(get('ss-sh-target'), 10) || 0,
      max_slots: parseInt(get('ss-sh-max'), 10) || 0,
    });
  }
  if (!shifts.length) return showAlert('ssAlert', 'Add at least one shift.', 'error');

  const roles = ['provider'];
  if (document.getElementById('ssEditStudentRole').checked) roles.push('student');

  const rotation = {
    key, label,
    model: 'shift_based',
    color: document.getElementById('ssEditColor').value,
    roles, shifts,
  };
  try {
    await apiPost('/api/periods/rotations', rotation);
  } catch (e) {
    return handleApiError(e, 'ssAlert');
  }
  showAlert('ssAlert', `Rotation "${label}" saved.`, 'success');
  ssCancelEdit();
  await ssLoadRotations();
  ssRenderRotationSelect();
  ssRenderRotationsList();
  await ssLoadGrid();
}

async function ssDeleteRotation(key) {
  const r = ssRotations.find(x => x.key === key);
  if (!r) return;
  if (!confirm(`Delete rotation "${r.label}"?`)) return;
  try {
    await apiDelete(`/api/periods/rotations/${encodeURIComponent(key)}`);
  } catch (e) {
    const msg = String(e.message || e);
    if (msg.includes('generated periods')) {
      if (confirm('This rotation has generated periods (and possibly assignments). Delete everything?')) {
        try {
          await apiDelete(`/api/periods/rotations/${encodeURIComponent(key)}?force=true`);
        } catch (e2) {
          return handleApiError(e2, 'ssAlert');
        }
      } else {
        return;
      }
    } else {
      return handleApiError(e, 'ssAlert');
    }
  }
  showAlert('ssAlert', `Rotation "${r.label}" deleted.`, 'success');
  await ssLoadRotations();
  ssRenderRotationSelect();
  ssRenderRotationsList();
  await ssLoadGrid();
}
