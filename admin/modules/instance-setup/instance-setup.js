/**
 * Instance Setup Wizard
 * Guides a new admin through configuring their FacultyHub deployment.
 */

let setupCurrentStep = 1;
const SETUP_TOTAL_STEPS = 5;

// ── Default shift config ──────────────────────────────────────────────────────
let setupShifts = [
  { key: 'day',   label: 'Day Shift',   start: '07:00', end: '19:00', slots_needed: 2 },
  { key: 'night', label: 'Night Shift', start: '19:00', end: '07:00', slots_needed: 2 },
];

let setupServiceTypes = [
  { key: 'micu', label: 'MICU' },
];

let setupFacultyAttrs = [];

// ── Step navigation ───────────────────────────────────────────────────────────

function setupGoTo(step) {
  document.getElementById('setupStep' + setupCurrentStep).style.display = 'none';
  setupCurrentStep = step;
  document.getElementById('setupStep' + step).style.display = 'block';
  document.getElementById('setupStepLabel').textContent = 'Step ' + step + ' of ' + SETUP_TOTAL_STEPS;
  document.getElementById('setupProgressBar').style.width = (step / SETUP_TOTAL_STEPS * 100) + '%';

  if (step === 2) renderShifts();
  if (step === 3) renderServiceTypes();
  if (step === 4) renderFacultyAttrs();
}

function setupNext(fromStep) {
  if (!setupValidateStep(fromStep)) return;
  if (fromStep < SETUP_TOTAL_STEPS) setupGoTo(fromStep + 1);
}

function setupBack(fromStep) {
  if (fromStep > 1) setupGoTo(fromStep - 1);
}

function setupValidateStep(step) {
  if (step === 1) {
    const gn = document.getElementById('setupGroupName').value.trim();
    if (!gn) { alert('Group Name is required.'); return false; }
  }
  if (step === 3) {
    const types = collectServiceTypes();
    if (types.length === 0) { alert('Add at least one service / rotation type.'); return false; }
    const keys = types.map(function(t) { return t.key; });
    if (new Set(keys).size !== keys.length) { alert('Service type keys must be unique.'); return false; }
  }
  return true;
}

// ── Step 2: Shifts ────────────────────────────────────────────────────────────

function toggleShiftConfig() {
  const isShift = document.getElementById('modelShift').checked;
  document.getElementById('shiftConfigSection').style.display = isShift ? 'block' : 'none';
}

function renderShifts() {
  const container = document.getElementById('shiftsList');
  container.innerHTML = setupShifts.map(function(s, i) {
    return '<div style="display:grid;grid-template-columns:1fr 1fr 80px 80px 80px 40px;gap:8px;align-items:end;margin-bottom:10px;">' +
      '<div><label style="font-size:12px;color:#6b7280;">Key</label>' +
        '<input type="text" value="' + s.key + '" oninput="updateShift(' + i + ',\'key\',this.value)" style="font-size:13px;"></div>' +
      '<div><label style="font-size:12px;color:#6b7280;">Label</label>' +
        '<input type="text" value="' + s.label + '" oninput="updateShift(' + i + ',\'label\',this.value)" style="font-size:13px;"></div>' +
      '<div><label style="font-size:12px;color:#6b7280;">Start</label>' +
        '<input type="time" value="' + s.start + '" oninput="updateShift(' + i + ',\'start\',this.value)" style="font-size:13px;"></div>' +
      '<div><label style="font-size:12px;color:#6b7280;">End</label>' +
        '<input type="time" value="' + s.end + '" oninput="updateShift(' + i + ',\'end\',this.value)" style="font-size:13px;"></div>' +
      '<div><label style="font-size:12px;color:#6b7280;">Slots</label>' +
        '<input type="number" value="' + s.slots_needed + '" min="1" max="20" oninput="updateShift(' + i + ',\'slots_needed\',parseInt(this.value))" style="font-size:13px;"></div>' +
      (setupShifts.length > 1
        ? '<button class="btn-danger btn-sm" style="margin-top:20px;" onclick="removeShift(' + i + ')">✕</button>'
        : '<div></div>') +
      '</div>';
  }).join('');
}

function updateShift(i, field, val) { setupShifts[i][field] = val; }

function addShift() {
  setupShifts.push({ key: 'shift' + (setupShifts.length + 1), label: 'New Shift', start: '07:00', end: '19:00', slots_needed: 2 });
  renderShifts();
}

function removeShift(i) {
  setupShifts.splice(i, 1);
  renderShifts();
}

// ── Step 3: Service types ─────────────────────────────────────────────────────

function renderServiceTypes() {
  const container = document.getElementById('serviceTypesList');
  if (setupServiceTypes.length === 0) {
    container.innerHTML = '<p style="color:#9ca3af;font-size:14px;padding:12px 0;">No service types yet. Add one below.</p>';
    return;
  }
  container.innerHTML = setupServiceTypes.map(function(st, i) {
    return '<div style="display:grid;grid-template-columns:1fr 1fr 40px;gap:8px;align-items:end;margin-bottom:10px;">' +
      '<div><label style="font-size:12px;color:#6b7280;">Key (immutable after setup)</label>' +
        '<input type="text" value="' + st.key + '" oninput="updateServiceType(' + i + ',\'key\',this.value)" style="font-size:13px;font-family:monospace;"></div>' +
      '<div><label style="font-size:12px;color:#6b7280;">Display Label</label>' +
        '<input type="text" value="' + st.label + '" oninput="updateServiceType(' + i + ',\'label\',this.value)" style="font-size:13px;"></div>' +
      '<button class="btn-danger btn-sm" style="margin-top:20px;" onclick="removeServiceType(' + i + ')">✕</button>' +
      '</div>';
  }).join('');
}

function collectServiceTypes() {
  const rows = document.querySelectorAll('#serviceTypesList div[style*="grid"]');
  const result = [];
  rows.forEach(function(row, i) {
    const inputs = row.querySelectorAll('input');
    const key   = inputs[0] ? inputs[0].value.trim().toLowerCase().replace(/\s+/g, '_') : '';
    const label = inputs[1] ? inputs[1].value.trim() : '';
    if (key) result.push({ key, label: label || key });
  });
  return result;
}

function updateServiceType(i, field, val) { setupServiceTypes[i][field] = field === 'key' ? val.trim().toLowerCase() : val; }

function addServiceType() {
  setupServiceTypes.push({ key: 'rotation' + (setupServiceTypes.length + 1), label: 'New Rotation' });
  renderServiceTypes();
}

function removeServiceType(i) {
  setupServiceTypes.splice(i, 1);
  renderServiceTypes();
}

// ── Step 4: Faculty attributes ────────────────────────────────────────────────

function renderFacultyAttrs() {
  const container = document.getElementById('facultyAttrsList');
  if (setupFacultyAttrs.length === 0) {
    container.innerHTML = '<p style="color:#9ca3af;font-size:14px;padding:12px 0;">No custom attributes. Core fields (name, email, active) are always included.</p>';
    return;
  }
  container.innerHTML = setupFacultyAttrs.map(function(attr, i) {
    return '<div style="display:grid;grid-template-columns:1fr 1fr 1fr 40px;gap:8px;align-items:end;margin-bottom:10px;">' +
      '<div><label style="font-size:12px;color:#6b7280;">Key</label>' +
        '<input type="text" value="' + attr.key + '" oninput="updateFacultyAttr(' + i + ',\'key\',this.value)" style="font-size:13px;font-family:monospace;"></div>' +
      '<div><label style="font-size:12px;color:#6b7280;">Label</label>' +
        '<input type="text" value="' + attr.label + '" oninput="updateFacultyAttr(' + i + ',\'label\',this.value)" style="font-size:13px;"></div>' +
      '<div><label style="font-size:12px;color:#6b7280;">Type</label>' +
        '<select oninput="updateFacultyAttr(' + i + ',\'type\',this.value)" style="font-size:13px;">' +
          ['text','number','select','checkbox'].map(function(t) {
            return '<option value="' + t + '"' + (attr.type === t ? ' selected' : '') + '>' + t + '</option>';
          }).join('') +
        '</select></div>' +
      '<button class="btn-danger btn-sm" style="margin-top:20px;" onclick="removeFacultyAttr(' + i + ')">✕</button>' +
      '</div>';
  }).join('');
}

function updateFacultyAttr(i, field, val) { setupFacultyAttrs[i][field] = val; }

function addFacultyAttr() {
  setupFacultyAttrs.push({ key: 'attr' + (setupFacultyAttrs.length + 1), label: 'New Attribute', type: 'text' });
  renderFacultyAttrs();
}

function removeFacultyAttr(i) {
  setupFacultyAttrs.splice(i, 1);
  renderFacultyAttrs();
}

// ── Step 5: Activate ──────────────────────────────────────────────────────────

async function activateInstance() {
  const btn = document.getElementById('setupActivateBtn');
  btn.disabled = true;
  btn.textContent = 'Saving…';

  try {
    const serviceTypes = collectServiceTypes();
    const model = document.getElementById('modelShift').checked ? 'shift_based' : 'weekly_blocks';

    const updates = {
      group_name: document.getElementById('setupGroupName').value.trim(),
      org_name:   document.getElementById('setupOrgName').value.trim(),
      app_name:   document.getElementById('setupAppName').value.trim() || 'Faculty Hub',
      branding: {
        org_label:    document.getElementById('setupOrgLabel').value.trim(),
        accent_color: null,
      },
      scheduling_model: model,
      shift_config:     { shifts: setupShifts },
      service_types:    serviceTypes,
      faculty_attributes: setupFacultyAttrs,
      features: {
        moonlighting:         document.getElementById('featMoonlighting').checked,
        service_availability: document.getElementById('featServiceAvail').checked,
        knowledge_base:       document.getElementById('featKnowledgeBase').checked,
        messages:             document.getElementById('featMessages').checked,
        draft_system:         document.getElementById('featDraftSystem').checked,
      },
    };

    for (const [key, value] of Object.entries(updates)) {
      const res = await fetch('/api/config/' + key, {
        method: 'PUT',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value }),
      });
      if (!res.ok) throw new Error('Failed to save ' + key);
    }

    // Mark setup complete
    const finalRes = await fetch('/api/config/setup', {
      method: 'POST',
      credentials: 'same-origin',
    });
    if (!finalRes.ok) {
      const err = await finalRes.json();
      throw new Error(err.detail || 'Setup finalization failed');
    }

    // Update cached config
    window._instanceConfig = Object.assign(window._instanceConfig || {}, updates, { setup_complete: true });

    // Show done screen
    document.getElementById('setupStep5').style.display = 'none';
    document.getElementById('setupProgressBar').style.width = '100%';
    document.getElementById('setupStepLabel').textContent = 'Complete';
    document.getElementById('setupDone').style.display = 'block';

  } catch (err) {
    document.getElementById('setupAlert').textContent = 'Error: ' + err.message;
    document.getElementById('setupAlert').className = 'alert alert-error';
    document.getElementById('setupAlert').style.display = 'block';
    btn.disabled = false;
    btn.textContent = '✓ Activate Instance';
  }
}

// ── Init ──────────────────────────────────────────────────────────────────────

function initInstanceSetup() {
  // Pre-fill from existing config if any
  const cfg = window._instanceConfig || {};
  if (cfg.group_name)  document.getElementById('setupGroupName').value = cfg.group_name;
  if (cfg.org_name)    document.getElementById('setupOrgName').value   = cfg.org_name;
  if (cfg.app_name)    document.getElementById('setupAppName').value   = cfg.app_name;
  if (cfg.branding && cfg.branding.org_label) {
    document.getElementById('setupOrgLabel').value = cfg.branding.org_label;
  }
  if (cfg.shift_config && cfg.shift_config.shifts && cfg.shift_config.shifts.length) {
    setupShifts = cfg.shift_config.shifts;
  }
  if (cfg.service_types && cfg.service_types.length) {
    setupServiceTypes = cfg.service_types;
  }
  if (cfg.faculty_attributes && cfg.faculty_attributes.length) {
    setupFacultyAttrs = cfg.faculty_attributes;
  }
  if (cfg.scheduling_model === 'weekly_blocks') {
    document.getElementById('modelWeekly').checked = true;
    document.getElementById('shiftConfigSection').style.display = 'none';
  }
  if (cfg.features) {
    if (cfg.features.moonlighting !== undefined)         document.getElementById('featMoonlighting').checked = cfg.features.moonlighting;
    if (cfg.features.service_availability !== undefined) document.getElementById('featServiceAvail').checked = cfg.features.service_availability;
    if (cfg.features.knowledge_base !== undefined)       document.getElementById('featKnowledgeBase').checked = cfg.features.knowledge_base;
    if (cfg.features.messages !== undefined)             document.getElementById('featMessages').checked = cfg.features.messages;
    if (cfg.features.draft_system !== undefined)         document.getElementById('featDraftSystem').checked = cfg.features.draft_system;
  }

  setupGoTo(1);
}

// Global exports
window.setupNext           = setupNext;
window.setupBack           = setupBack;
window.toggleShiftConfig   = toggleShiftConfig;
window.addShift            = addShift;
window.removeShift         = removeShift;
window.updateShift         = updateShift;
window.addServiceType      = addServiceType;
window.removeServiceType   = removeServiceType;
window.updateServiceType   = updateServiceType;
window.addFacultyAttr      = addFacultyAttr;
window.removeFacultyAttr   = removeFacultyAttr;
window.updateFacultyAttr   = updateFacultyAttr;
window.activateInstance    = activateInstance;
window.initInstanceSetup   = initInstanceSetup;
