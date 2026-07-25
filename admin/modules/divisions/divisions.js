/**
 * Divisions Module — manage divisions and their self-scheduling policy.
 * Each division sets how end users get onto the schedule (method) and at
 * what cadence (annual / quarterly / monthly).
 */

let divDivisions = [];
let divMethods = [];
let divCadences = [];

async function initDivisions() {
  try {
    const opts = await apiGet('/api/divisions/scheduling-options');
    divMethods = opts.methods || [];
    divCadences = opts.cadences || [];
  } catch (e) {
    divMethods = [];
    divCadences = [];
  }
  await loadDivisions();
}

async function loadDivisions() {
  try {
    divDivisions = await getDivisions();
  } catch (e) {
    return handleApiError(e, 'divAlert');
  }
  divRenderList();
}

function divMethodMeta(key) {
  return divMethods.find(m => m.key === key) || { label: key, description: '' };
}
function divCadenceMeta(key) {
  return divCadences.find(c => c.key === key) || { label: key, description: '' };
}

function divOptionTags(list, selected) {
  return list.map(o =>
    `<option value="${o.key}" ${o.key === selected ? 'selected' : ''}>${o.label}</option>`
  ).join('');
}

function divRenderList() {
  const host = document.getElementById('divList');
  if (!divDivisions.length) {
    host.innerHTML = '<div class="info-box"><strong>No divisions yet.</strong>' +
      '<p>Create one with “New Division” above.</p></div>';
    return;
  }

  host.innerHTML = divDivisions.map(d => {
    const cfg = d.scheduling_config || {};
    const method = cfg.method || 'manual';
    const cadence = cfg.cadence || 'monthly';
    const k = d.key;
    return `
    <div class="card" style="margin-bottom:16px;border:1px solid #e5e7eb;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
        <h3 style="font-size:16px;font-weight:600;color:#1f2937;display:flex;align-items:center;gap:8px;">
          <span style="display:inline-block;width:12px;height:12px;border-radius:3px;background:${d.color || '#9ca3af'};"></span>
          ${d.label} <code style="font-size:12px;color:#6b7280;">${k}</code>
          ${d.member_count != null ? `<span style="font-size:12px;color:#9ca3af;font-weight:400;">· ${d.member_count} member${d.member_count === 1 ? '' : 's'}</span>` : ''}
        </h3>
        <label style="display:flex;align-items:center;gap:6px;font-size:13px;color:#374151;">
          <input type="checkbox" id="divActive-${k}" ${d.is_active ? 'checked' : ''} style="width:auto;"> Active
        </label>
      </div>

      <div class="form-grid" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;">
        <div class="form-group">
          <label>Label</label>
          <input type="text" id="divLabel-${k}" value="${d.label.replace(/"/g, '&quot;')}">
        </div>
        <div class="form-group">
          <label>Color</label>
          <input type="color" id="divColor-${k}" value="${d.color || '#2563eb'}" style="height:38px;padding:2px;">
        </div>
      </div>

      <h4 style="margin:18px 0 4px;font-size:13px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;color:#6b7280;">
        Self-scheduling policy
      </h4>
      <p style="margin-bottom:12px;color:#9ca3af;font-size:12px;">
        How this division's people get onto the schedule, and how far ahead it's built.
      </p>

      <div class="form-grid" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;">
        <div class="form-group">
          <label>How users get on the schedule</label>
          <select id="divMethod-${k}" onchange="divUpdateMethodDesc('${k}')">
            ${divOptionTags(divMethods, method)}
          </select>
          <small id="divMethodDesc-${k}" style="color:#6b7280;">${divMethodMeta(method).description}</small>
        </div>
        <div class="form-group">
          <label>Schedule cadence</label>
          <select id="divCadence-${k}" onchange="divUpdateCadenceDesc('${k}')">
            ${divOptionTags(divCadences, cadence)}
          </select>
          <small id="divCadenceDesc-${k}" style="color:#6b7280;">${divCadenceMeta(cadence).description}</small>
        </div>
      </div>

      <div class="form-group" style="margin-top:12px;">
        <label style="display:flex;align-items:center;gap:8px;">
          <input type="checkbox" id="divOpen-${k}" ${cfg.self_scheduling_open ? 'checked' : ''} style="width:auto;">
          Self-scheduling window is open to users now
        </label>
        <small style="color:#9ca3af;">Turn on when it's time for this division to pick; turn off to freeze the schedule.</small>
      </div>

      <div class="form-group">
        <label>Notes (optional)</label>
        <textarea id="divNotes-${k}" rows="2" placeholder="e.g. Q3 picks open Aug 1, close Aug 15">${(cfg.notes || '').replace(/</g, '&lt;')}</textarea>
      </div>

      <div style="display:flex;gap:12px;margin-top:8px;">
        <button class="btn-primary" onclick="divSave('${k}')"><span data-icon="save"></span> Save</button>
        <button class="btn-danger btn-sm" onclick="divDelete('${k}')"><span data-icon="trash"></span> Delete division</button>
      </div>
    </div>`;
  }).join('');
}

function divUpdateMethodDesc(key) {
  const val = document.getElementById('divMethod-' + key).value;
  document.getElementById('divMethodDesc-' + key).textContent = divMethodMeta(val).description;
}
function divUpdateCadenceDesc(key) {
  const val = document.getElementById('divCadence-' + key).value;
  document.getElementById('divCadenceDesc-' + key).textContent = divCadenceMeta(val).description;
}

async function divSave(key) {
  const d = divDivisions.find(x => x.key === key);
  if (!d) return;
  const payload = {
    key,
    label: document.getElementById('divLabel-' + key).value.trim() || d.label,
    color: document.getElementById('divColor-' + key).value,
    is_active: document.getElementById('divActive-' + key).checked,
    scheduling_config: {
      method: document.getElementById('divMethod-' + key).value,
      cadence: document.getElementById('divCadence-' + key).value,
      self_scheduling_open: document.getElementById('divOpen-' + key).checked,
      notes: document.getElementById('divNotes-' + key).value.trim(),
    },
  };
  try {
    await apiPost('/api/divisions', payload);
  } catch (e) {
    return handleApiError(e, 'divAlert');
  }
  showAlert('divAlert', `Saved "${payload.label}" scheduling policy.`, 'success');
  await loadDivisions();
}

async function divDelete(key) {
  const d = divDivisions.find(x => x.key === key);
  if (!d) return;
  if (!confirm(`Delete division "${d.label}"? Members become unassigned.`)) return;
  try {
    await apiDelete(`/api/divisions/${encodeURIComponent(key)}`);
  } catch (e) {
    const msg = String(e.message || e);
    if (msg.includes('members') || msg.includes('rotations')) {
      if (confirm('This division has members and/or rotations. Delete anyway? Members become unassigned.')) {
        try {
          await apiDelete(`/api/divisions/${encodeURIComponent(key)}?force=true`);
        } catch (e2) {
          return handleApiError(e2, 'divAlert');
        }
      } else {
        return;
      }
    } else {
      return handleApiError(e, 'divAlert');
    }
  }
  showAlert('divAlert', `Deleted division "${d.label}".`, 'success');
  await loadDivisions();
}

// ── New division ──────────────────────────────────────────────────────────────

function divShowNewForm() {
  document.getElementById('divNewForm').style.display = '';
  document.getElementById('divNewKey').focus();
}
function divHideNewForm() {
  document.getElementById('divNewForm').style.display = 'none';
  document.getElementById('divNewKey').value = '';
  document.getElementById('divNewLabel').value = '';
}

async function divCreate() {
  const key = document.getElementById('divNewKey').value.trim().toLowerCase();
  const label = document.getElementById('divNewLabel').value.trim();
  const color = document.getElementById('divNewColor').value;
  if (!key || !label) return showAlert('divAlert', 'Key and label are required.', 'error');
  if (!/^[a-z0-9_]+$/.test(key)) return showAlert('divAlert', 'Key must be lowercase letters, numbers, underscores.', 'error');

  try {
    await apiPost('/api/divisions', {
      key, label, color, is_active: true,
      scheduling_config: { method: 'manual', cadence: 'monthly', self_scheduling_open: false, notes: '' },
    });
  } catch (e) {
    return handleApiError(e, 'divAlert');
  }
  showAlert('divAlert', `Created division "${label}".`, 'success');
  divHideNewForm();
  await loadDivisions();
}
