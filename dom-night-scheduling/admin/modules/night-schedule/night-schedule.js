/**
 * Night Schedule Module — quarter setup, blocked nights, quotas,
 * self-scheduling status, builder preview/apply, and schedule grid.
 */

let nsQuarters = [];
let nsProviders = [];
let nsCurrentQuarterId = null;
let nsCurrentQuarter = null;
let nsActiveTab = 'setup';
let nsLastPreview = null;

const NS_STATUS_LABELS = {
  draft: 'Draft',
  open_for_preferences: 'Open for Preferences',
  building: 'Building',
  published: 'Published',
  archived: 'Archived',
};

// ── PATCH helper (api.js doesn't provide one) ─────────────────────────────────

async function nsApiPatch(endpoint, data) {
  try {
    const response = await fetch(endpoint, {
      method: 'PATCH',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!response.ok) {
      if (handleAuthFailure(response.status)) return;
      const errorText = await response.text();
      throw new Error('API Error: ' + response.status + ' - ' + errorText);
    }
    return await response.json();
  } catch (error) {
    console.error('API PATCH Error:', error);
    throw error;
  }
}

// ── Init ───────────────────────────────────────────────────────────────────

async function initNightSchedule() {
  try {
    nsProviders = await getFaculty();
  } catch (e) {
    nsProviders = [];
    console.warn('Could not load providers:', e);
  }

  // Reset dropdown caches so they repopulate with the loaded providers
  ['nsBlockProvider', 'nsBlockFilter'].forEach(function(id) {
    const el = document.getElementById(id);
    if (el) delete el.dataset.loaded;
  });

  await nsLoadQuarters();
}

function nsActiveProviders() {
  return nsProviders.filter(function(p) { return p.active; });
}

function nsProviderName(id) {
  const p = nsProviders.find(function(p) { return p.id === id; });
  return p ? p.name : id;
}

// ── Quarter list / selection ─────────────────────────────────────────────────

async function nsLoadQuarters() {
  try {
    nsQuarters = await apiGet('/api/admin/night-schedule/quarters');
  } catch (e) {
    return handleApiError(e, 'nsAlert');
  }

  const sel = document.getElementById('nsQuarterSelect');

  if (!nsQuarters.length) {
    sel.innerHTML = '<option value="">No quarters yet — create one above</option>';
    nsCurrentQuarterId = null;
    nsCurrentQuarter = null;
    nsRenderQuarterStats();
    await nsRefreshCurrentTab();
    return;
  }

  const prevSelected = nsCurrentQuarterId;
  sel.innerHTML = nsQuarters.map(function(q) {
    return '<option value="' + q.id + '">' + q.name + ' (' + (NS_STATUS_LABELS[q.status] || q.status) + ')</option>';
  }).join('');

  if (prevSelected && nsQuarters.some(function(q) { return q.id === prevSelected; })) {
    sel.value = prevSelected;
  } else {
    sel.value = nsQuarters[0].id;
  }

  nsCurrentQuarterId = sel.value;
  nsCurrentQuarter = nsQuarters.find(function(q) { return q.id === nsCurrentQuarterId; }) || null;
  nsRenderQuarterStats();
  await nsRefreshCurrentTab();
}

async function nsOnQuarterChange() {
  nsCurrentQuarterId = document.getElementById('nsQuarterSelect').value;
  nsCurrentQuarter = nsQuarters.find(function(q) { return q.id === nsCurrentQuarterId; }) || null;
  nsLastPreview = null;
  document.getElementById('nsPreviewStats').style.display = 'none';
  document.getElementById('nsPreviewDetails').innerHTML = '';
  nsRenderQuarterStats();
  await nsRefreshCurrentTab();
}

function nsRenderQuarterStats() {
  const el = document.getElementById('nsQuarterStats');
  if (!nsCurrentQuarter) {
    el.innerHTML = '';
    return;
  }
  const q = nsCurrentQuarter;
  el.innerHTML = [
    nsStatCard('Status', NS_STATUS_LABELS[q.status] || q.status),
    nsStatCard('Date Range', q.start_date + ' → ' + q.end_date),
    nsStatCard('Periods Generated', q.period_count),
    nsStatCard('Default Quota', q.default_quota + ' / quarter'),
    nsStatCard('Blocked Nights', q.blocked_count),
    nsStatCard('Preferences Submitted', q.preference_count),
  ].join('');
}

function nsStatCard(label, value) {
  return '<div class="stat-card"><div class="stat-label">' + label + '</div>' +
    '<div class="stat-value" style="font-size:18px;">' + value + '</div></div>';
}

// ── New quarter ───────────────────────────────────────────────────────────────

function nsToggleNewQuarterForm() {
  const f = document.getElementById('nsNewQuarterForm');
  f.style.display = (f.style.display === 'none' || !f.style.display) ? 'block' : 'none';
}

async function nsCreateQuarter() {
  const name = document.getElementById('nsNewName').value.trim();
  const start = document.getElementById('nsNewStart').value;
  const end = document.getElementById('nsNewEnd').value;
  if (!name || !start || !end) {
    return showAlert('nsAlert', 'Quarter name, start date, and end date are required.', 'error');
  }
  if (end < start) {
    return showAlert('nsAlert', 'End date must be on or after the start date.', 'error');
  }

  const deadlineRaw = document.getElementById('nsNewDeadline').value;
  const body = {
    name: name,
    start_date: start,
    end_date: end,
    default_quota: parseInt(document.getElementById('nsNewQuota').value, 10) || 0,
    preference_deadline: deadlineRaw ? new Date(deadlineRaw).toISOString() : null,
  };

  try {
    const q = await apiPost('/api/admin/night-schedule/quarters', body);
    showAlert('nsAlert', 'Quarter "' + q.name + '" created.', 'success');
    document.getElementById('nsNewName').value = '';
    document.getElementById('nsNewStart').value = '';
    document.getElementById('nsNewEnd').value = '';
    document.getElementById('nsNewQuota').value = '0';
    document.getElementById('nsNewDeadline').value = '';
    nsToggleNewQuarterForm();
    nsCurrentQuarterId = q.id;
    await nsLoadQuarters();
  } catch (e) {
    handleApiError(e, 'nsAlert');
  }
}

// ── Sub-tabs ───────────────────────────────────────────────────────────────────

function nsShowSubTab(tab) {
  nsActiveTab = tab;
  const root = document.getElementById('nightScheduleRoot');
  root.querySelectorAll('.sub-tab-btn').forEach(function(b) {
    b.classList.toggle('active', b.dataset.tab === tab);
  });
  root.querySelectorAll('.sub-tab-content').forEach(function(c) {
    c.classList.toggle('active', c.id === 'nsTab-' + tab);
  });
  nsRefreshCurrentTab();
}

async function nsRefreshCurrentTab() {
  if (!nsCurrentQuarterId) {
    nsClearSetupForm();
    const emptyRow = function(cols) {
      return '<tr><td colspan="' + cols + '" class="empty-state">Create a quarter above to get started.</td></tr>';
    };
    const blocked = document.getElementById('nsBlockedTableBody');
    if (blocked) blocked.innerHTML = emptyRow(5);
    const quotas = document.getElementById('nsQuotasTableBody');
    if (quotas) quotas.innerHTML = emptyRow(5);
    const prefs = document.getElementById('nsPrefsTableBody');
    if (prefs) prefs.innerHTML = emptyRow(6);
    const sched = document.getElementById('nsScheduleTableBody');
    if (sched) sched.innerHTML = emptyRow(3);
    const exportLink = document.getElementById('nsExportLink');
    if (exportLink) exportLink.href = '#';
    return;
  }

  switch (nsActiveTab) {
    case 'setup':   await nsLoadSetupTab(); break;
    case 'blocked': await nsLoadBlockedTab(); break;
    case 'quotas':  await nsLoadQuotasTab(); break;
    case 'prefs':   await nsLoadPrefsTab(); break;
    case 'builder': await nsLoadBuilderTab(); break;
  }
}

// ── Setup tab ──────────────────────────────────────────────────────────────────

function nsClearSetupForm() {
  ['nsSetupName', 'nsSetupStart', 'nsSetupEnd', 'nsSetupNotes', 'nsSetupDeadline'].forEach(function(id) {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  const quota = document.getElementById('nsSetupQuota');
  if (quota) quota.value = '0';
  const status = document.getElementById('nsSetupStatus');
  if (status) status.value = 'draft';
  const info = document.getElementById('nsPeriodInfo');
  if (info) info.textContent = '—';
}

async function nsLoadSetupTab() {
  if (!nsCurrentQuarterId) return;
  let q;
  try {
    q = await apiGet('/api/admin/night-schedule/quarters/' + nsCurrentQuarterId);
  } catch (e) {
    return handleApiError(e, 'nsAlert');
  }
  nsCurrentQuarter = q;

  document.getElementById('nsSetupName').value = q.name;
  document.getElementById('nsSetupStart').value = q.start_date;
  document.getElementById('nsSetupEnd').value = q.end_date;
  document.getElementById('nsSetupQuota').value = q.default_quota;
  document.getElementById('nsSetupDeadline').value = q.preference_deadline ? q.preference_deadline.slice(0, 16) : '';
  document.getElementById('nsSetupStatus').value = q.status;
  document.getElementById('nsSetupNotes').value = q.notes || '';

  const nights = Math.round((new Date(q.end_date) - new Date(q.start_date)) / 86400000) + 1;
  document.getElementById('nsPeriodInfo').textContent =
    q.period_count + ' period(s) generated for ' + nights + ' night(s) × 2 lanes (admitter/nocturnist). ' +
    q.blocked_count + ' blocked night(s) recorded. ' + q.preference_count + ' preference(s) submitted.';

  nsRenderQuarterStats();
}

async function nsSaveQuarterSetup() {
  if (!nsCurrentQuarterId) return;
  const name = document.getElementById('nsSetupName').value.trim();
  const start = document.getElementById('nsSetupStart').value;
  const end = document.getElementById('nsSetupEnd').value;
  if (!name || !start || !end) {
    return showAlert('nsAlert', 'Quarter name, start date, and end date are required.', 'error');
  }
  if (end < start) {
    return showAlert('nsAlert', 'End date must be on or after the start date.', 'error');
  }

  const deadlineRaw = document.getElementById('nsSetupDeadline').value;
  const body = {
    name: name,
    start_date: start,
    end_date: end,
    default_quota: parseInt(document.getElementById('nsSetupQuota').value, 10) || 0,
    status: document.getElementById('nsSetupStatus').value,
    notes: document.getElementById('nsSetupNotes').value,
    preference_deadline: deadlineRaw ? new Date(deadlineRaw).toISOString() : null,
  };

  try {
    await nsApiPatch('/api/admin/night-schedule/quarters/' + nsCurrentQuarterId, body);
    showAlert('nsAlert', 'Quarter settings saved.', 'success');
    await nsLoadQuarters();
  } catch (e) {
    handleApiError(e, 'nsAlert');
  }
}

async function nsGeneratePeriods() {
  if (!nsCurrentQuarterId) return;
  try {
    const result = await apiPost('/api/admin/night-schedule/quarters/' + nsCurrentQuarterId + '/generate-periods', {});
    showAlert('nsAlert', 'Generated ' + result.created + ' new period(s) across ' + result.total_nights + ' night(s) × ' + result.lanes.length + ' lane(s).', 'success');
    await nsLoadQuarters();
  } catch (e) {
    handleApiError(e, 'nsAlert');
  }
}

// ── Blocked Nights tab ───────────────────────────────────────────────────────

function nsProviderOptions(selectedId) {
  return nsActiveProviders().map(function(p) {
    return '<option value="' + p.id + '"' + (p.id === selectedId ? ' selected' : '') + '>' + p.name + ' (' + p.id + ')</option>';
  }).join('');
}

async function nsLoadBlockedTab() {
  if (!nsCurrentQuarterId) return;

  const providerSelect = document.getElementById('nsBlockProvider');
  if (providerSelect && !providerSelect.dataset.loaded) {
    providerSelect.innerHTML = nsProviderOptions();
    providerSelect.dataset.loaded = '1';
  }
  const filterSelect = document.getElementById('nsBlockFilter');
  if (filterSelect && !filterSelect.dataset.loaded) {
    filterSelect.innerHTML = '<option value="">All providers</option>' + nsProviderOptions();
    filterSelect.dataset.loaded = '1';
  }

  const filterVal = filterSelect ? filterSelect.value : '';
  let rows;
  try {
    const qs = filterVal ? ('?provider_id=' + encodeURIComponent(filterVal)) : '';
    rows = await apiGet('/api/admin/night-schedule/quarters/' + nsCurrentQuarterId + '/blocked-nights' + qs);
  } catch (e) {
    return handleApiError(e, 'nsAlert');
  }

  const tbody = document.getElementById('nsBlockedTableBody');
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No blocked nights recorded yet.</td></tr>';
    return;
  }

  tbody.innerHTML = rows.map(function(r) {
    return '<tr>' +
      '<td>' + r.provider_name + '</td>' +
      '<td>' + r.night_date + '</td>' +
      '<td><span class="badge' + (r.source === 'import' ? ' badge-info' : '') + '">' + r.source + '</span></td>' +
      '<td>' + (r.note || '') + '</td>' +
      '<td><button class="btn-danger btn-sm" onclick="nsDeleteBlockedNight(\'' + r.id + '\')">Delete</button></td>' +
      '</tr>';
  }).join('');
}

async function nsAddBlockedNight() {
  if (!nsCurrentQuarterId) return;
  const provider_id = document.getElementById('nsBlockProvider').value;
  const night_date = document.getElementById('nsBlockDate').value;
  if (!provider_id || !night_date) {
    return showAlert('nsAlert', 'Select a provider and a date.', 'error');
  }
  try {
    const result = await apiPost('/api/admin/night-schedule/quarters/' + nsCurrentQuarterId + '/blocked-nights', { provider_id: provider_id, night_date: night_date });
    showAlert('nsAlert', result.already_existed ? 'That night was already blocked for this provider.' : 'Blocked night added.', 'success');
    document.getElementById('nsBlockDate').value = '';
    await nsLoadBlockedTab();
    await nsLoadQuarters();
  } catch (e) {
    handleApiError(e, 'nsAlert');
  }
}

async function nsDeleteBlockedNight(id) {
  if (!nsCurrentQuarterId) return;
  if (!confirm('Remove this blocked night? The provider will be able to self-schedule it if the window is still open.')) return;
  try {
    await apiDelete('/api/admin/night-schedule/quarters/' + nsCurrentQuarterId + '/blocked-nights/' + id);
    await nsLoadBlockedTab();
    await nsLoadQuarters();
  } catch (e) {
    handleApiError(e, 'nsAlert');
  }
}

async function nsImportBlockedNights() {
  if (!nsCurrentQuarterId) return;
  const csv = document.getElementById('nsBlockCsv').value.trim();
  if (!csv) return showAlert('nsAlert', 'Paste CSV data first.', 'error');

  try {
    const response = await fetch('/api/admin/night-schedule/quarters/' + nsCurrentQuarterId + '/blocked-nights/import', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'text/csv' },
      body: csv,
    });
    if (!response.ok) {
      if (handleAuthFailure(response.status)) return;
      throw new Error('API Error: ' + response.status + ' - ' + (await response.text()));
    }
    const result = await response.json();

    let msg = 'Imported ' + result.imported + ' blocked night(s).';
    if (result.skipped.length) {
      msg += ' Skipped ' + result.skipped.length + ': ' + result.skipped.map(function(s) {
        return 'row ' + s.row + ' (' + s.reason + ')';
      }).join(', ');
    }
    document.getElementById('nsImportResult').textContent = msg;
    showAlert('nsAlert', 'Import complete.', result.skipped.length ? 'warning' : 'success');
    await nsLoadBlockedTab();
    await nsLoadQuarters();
  } catch (e) {
    handleApiError(e, 'nsAlert');
  }
}

// ── Quotas tab ─────────────────────────────────────────────────────────────────

async function nsLoadQuotasTab() {
  if (!nsCurrentQuarterId) return;
  let data;
  try {
    data = await apiGet('/api/admin/night-schedule/quarters/' + nsCurrentQuarterId + '/quotas');
  } catch (e) {
    return handleApiError(e, 'nsAlert');
  }

  const tbody = document.getElementById('nsQuotasTableBody');
  if (!data.providers.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No active providers.</td></tr>';
    return;
  }

  tbody.innerHTML = data.providers.map(function(p) {
    const noteVal = (p.note || '').replace(/"/g, '&quot;');
    return '<tr>' +
      '<td>' + p.name + '</td>' +
      '<td><input type="number" min="0" id="nsQuota_' + p.provider_id + '" value="' + p.target_nights + '" style="width:80px;"></td>' +
      '<td>' + (p.is_override ? '<span class="badge badge-info">Override</span>' : '<span class="badge">Default (' + data.default_quota + ')</span>') + '</td>' +
      '<td><input type="text" id="nsQuotaNote_' + p.provider_id + '" value="' + noteVal + '" style="width:100%;" placeholder="optional note"></td>' +
      '<td>' +
        '<button class="btn-primary btn-sm" onclick="nsSaveQuota(\'' + p.provider_id + '\')">Save</button>' +
        (p.is_override ? ' <button class="btn-secondary btn-sm" onclick="nsClearQuota(\'' + p.provider_id + '\')">Reset</button>' : '') +
      '</td>' +
      '</tr>';
  }).join('');
}

async function nsSaveQuota(providerId) {
  if (!nsCurrentQuarterId) return;
  const targetEl = document.getElementById('nsQuota_' + providerId);
  const noteEl = document.getElementById('nsQuotaNote_' + providerId);
  const target = parseInt(targetEl.value, 10);
  if (isNaN(target) || target < 0) {
    return showAlert('nsAlert', 'Target nights must be a non-negative number.', 'error');
  }
  try {
    await apiPut('/api/admin/night-schedule/quarters/' + nsCurrentQuarterId + '/quotas/' + providerId, {
      target_nights: target,
      note: noteEl.value || null,
    });
    showAlert('nsAlert', 'Quota saved.', 'success');
    await nsLoadQuotasTab();
  } catch (e) {
    handleApiError(e, 'nsAlert');
  }
}

async function nsClearQuota(providerId) {
  if (!nsCurrentQuarterId) return;
  if (!confirm('Reset this provider to the default quota?')) return;
  try {
    await apiDelete('/api/admin/night-schedule/quarters/' + nsCurrentQuarterId + '/quotas/' + providerId);
    await nsLoadQuotasTab();
  } catch (e) {
    handleApiError(e, 'nsAlert');
  }
}

// ── Preferences Status tab ─────────────────────────────────────────────────────

async function nsLoadPrefsTab() {
  if (!nsCurrentQuarterId) return;
  let data;
  try {
    data = await apiGet('/api/admin/night-schedule/quarters/' + nsCurrentQuarterId + '/preferences-status');
  } catch (e) {
    return handleApiError(e, 'nsAlert');
  }

  document.getElementById('nsPrefsDeadlineInfo').textContent = data.preference_deadline
    ? 'Preference deadline: ' + new Date(data.preference_deadline).toLocaleString()
    : 'No preference deadline set for this quarter.';

  const tbody = document.getElementById('nsPrefsTableBody');
  if (!data.providers.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="empty-state">No active providers.</td></tr>';
    return;
  }

  tbody.innerHTML = data.providers.map(function(p) {
    return '<tr>' +
      '<td>' + p.name + '</td>' +
      '<td>' + p.target_nights + '</td>' +
      '<td>' + p.preferred_count + '</td>' +
      '<td>' + p.can_work_count + '</td>' +
      '<td>' + p.blocked_count + '</td>' +
      '<td>' + (p.submitted ? '<span class="badge badge-success">Submitted</span>' : '<span class="badge badge-warning">Not yet</span>') + '</td>' +
      '</tr>';
  }).join('');
}

// ── Builder & Schedule tab ──────────────────────────────────────────────────────

async function nsLoadBuilderTab() {
  if (!nsCurrentQuarterId) return;
  document.getElementById('nsExportLink').href = '/api/admin/night-schedule/quarters/' + nsCurrentQuarterId + '/export';

  if (nsLastPreview) {
    nsRenderPreview(nsLastPreview);
  } else {
    document.getElementById('nsPreviewStats').style.display = 'none';
    document.getElementById('nsPreviewDetails').innerHTML = '';
  }

  await nsLoadScheduleGrid();
}

async function nsPreviewBuild() {
  if (!nsCurrentQuarterId) return;
  try {
    const plan = await apiPost('/api/admin/night-schedule/quarters/' + nsCurrentQuarterId + '/preview', {});
    nsLastPreview = plan;
    nsRenderPreview(plan);
    showAlert('nsAlert', 'Preview generated. Review below, then Run Builder to apply.', 'info');
  } catch (e) {
    handleApiError(e, 'nsAlert');
  }
}

function nsRenderPreview(plan) {
  const statsEl = document.getElementById('nsPreviewStats');
  statsEl.style.display = 'flex';
  statsEl.innerHTML = [
    nsStatCard('Total Slots', plan.total_slots),
    nsStatCard('Auto Slots', plan.auto_slots),
    nsStatCard('Filled by Builder', plan.filled),
    nsStatCard('Still Unfilled', plan.unfilled.length),
    nsStatCard('Manual Kept', plan.manual_assignments.length),
  ].join('');

  let html = '';
  if (plan.unfilled.length) {
    html += '<div class="info-box info-box-danger"><strong>Unfilled Slots (' + plan.unfilled.length + ')</strong><p>' +
      plan.unfilled.map(function(u) { return u.date + ' — ' + u.lane; }).join(', ') +
      '</p></div>';
  } else {
    html += '<div class="info-box info-box-success" style="background:#d1fae5;border-left:4px solid #10b981;">' +
      '<strong style="color:#065f46;">All slots filled</strong>' +
      '<p style="color:#065f46;">Every night/lane in this quarter has an eligible provider.</p></div>';
  }

  html += '<h4 style="margin:16px 0 8px;font-size:14px;">Quota Summary</h4>';
  html += '<div class="table-container"><table class="data-table"><thead><tr><th>Provider</th><th>Target</th><th>Assigned (incl. manual)</th><th>Difference</th></tr></thead><tbody>';
  html += plan.quota_summary.map(function(r) {
    const diff = r.assigned - r.target;
    const diffColor = diff === 0 ? '#065f46' : (diff < 0 ? '#92400e' : '#1e40af');
    return '<tr><td>' + r.name + '</td><td>' + r.target + '</td><td>' + r.assigned + '</td>' +
      '<td style="color:' + diffColor + ';font-weight:600;">' + (diff > 0 ? '+' : '') + diff + '</td></tr>';
  }).join('');
  html += '</tbody></table></div>';

  document.getElementById('nsPreviewDetails').innerHTML = html;
}

async function nsRunBuild() {
  if (!nsCurrentQuarterId) return;
  if (!confirm('Run the builder? This replaces all non-manual assignments for this quarter based on the latest preferences and quotas. Manual overrides are kept.')) return;
  try {
    const result = await apiPost('/api/admin/night-schedule/quarters/' + nsCurrentQuarterId + '/build', {});
    showAlert('nsAlert', 'Builder applied ' + result.applied + ' assignment(s). ' + result.unfilled.length + ' slot(s) remain unfilled.', result.unfilled.length ? 'warning' : 'success');
    nsLastPreview = null;
    document.getElementById('nsPreviewStats').style.display = 'none';
    document.getElementById('nsPreviewDetails').innerHTML = '';
    await nsLoadScheduleGrid();
    await nsLoadQuarters();
  } catch (e) {
    handleApiError(e, 'nsAlert');
  }
}

async function nsLoadScheduleGrid() {
  if (!nsCurrentQuarterId) return;
  let data;
  try {
    data = await apiGet('/api/admin/night-schedule/quarters/' + nsCurrentQuarterId + '/schedule');
  } catch (e) {
    return handleApiError(e, 'nsAlert');
  }

  const tbody = document.getElementById('nsScheduleTableBody');
  if (!data.days.length) {
    tbody.innerHTML = '<tr><td colspan="3" class="empty-state">No periods generated yet. Go to the Setup tab and click "Generate / Sync Periods".</td></tr>';
    return;
  }

  tbody.innerHTML = data.days.map(function(day) {
    return '<tr>' +
      '<td>' + day.date + '</td>' +
      '<td>' + nsSlotSelect(day.lanes.admitter) + '</td>' +
      '<td>' + nsSlotSelect(day.lanes.nocturnist) + '</td>' +
      '</tr>';
  }).join('');
}

function nsSlotSelect(slot) {
  if (!slot) return '<span style="color:#9ca3af;">—</span>';

  let html = '<select onchange="nsSetScheduleSlot(\'' + slot.period_id + '\', this.value)" style="width:100%;max-width:220px;">';
  html += '<option value="">— Unassigned —</option>';
  html += nsActiveProviders().map(function(p) {
    return '<option value="' + p.id + '"' + (slot.provider_id === p.id ? ' selected' : '') + '>' + p.name + '</option>';
  }).join('');
  html += '</select>';

  if (slot.is_manual) {
    html += ' <span class="badge badge-info" style="margin-left:4px;">manual</span>';
  } else if (slot.provider_id) {
    html += ' <span class="badge" style="margin-left:4px;">auto</span>';
  }
  return html;
}

async function nsSetScheduleSlot(periodId, providerId) {
  if (!nsCurrentQuarterId) return;
  try {
    await apiPut('/api/admin/night-schedule/quarters/' + nsCurrentQuarterId + '/schedule/' + periodId, { provider_id: providerId || null });
    showAlert('nsAlert', 'Schedule slot updated.', 'success');
  } catch (e) {
    handleApiError(e, 'nsAlert');
  } finally {
    await nsLoadScheduleGrid();
  }
}
