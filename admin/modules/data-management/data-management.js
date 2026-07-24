/**
 * Data Management Module
 * Surgical data cleanup for beta test data
 */

let unavailabilityData = [];
let moonlightingData = [];
let selectedUnavail = new Set();
let selectedMoonlight = new Set();
let selectedWeekId = null;
let selectedWeekLabel = null;
let availableWeeks = new Map(); // Map of week_id -> {label, count, service_types}
let availableServiceTypes = new Set();
let allFacultyNames = [];       // Unavailability — full list, never filtered down
let allProviderIds = [];        // Moonlighting — full provider list
let allAssignFacultyNames = []; // Assignments — full faculty list

// ==================== TAB SWITCHING ====================

function showDataTab(tabName) {
  // Hide all tabs
  document.querySelectorAll('.sub-tab-content').forEach(tab => {
    tab.classList.remove('active');
  });
  document.querySelectorAll('.sub-tab-btn').forEach(btn => {
    btn.classList.remove('active');
  });

  // Show selected tab
  document.getElementById(`data-tab-${tabName}`).classList.add('active');
  event.target.classList.add('active');

  // Load data if needed
  if (tabName === 'unavailability' && unavailabilityData.length === 0) {
    loadUnavailabilityData();
  } else if (tabName === 'moonlighting' && moonlightingData.length === 0) {
    loadMoonlightingData();
  } else if (tabName === 'assignments' && assignmentsData.length === 0) {
    loadAssignmentsData();
  }
}

// ==================== UNAVAILABILITY REQUESTS ====================

async function loadUnavailabilityData() {
  try {
    showDataAlert('Loading unavailability requests...', 'info');

    const yearFilter = document.getElementById('unavailFilter')?.value || 'all';
    const facultyFilter = document.getElementById('unavailFacultyFilter')?.value || 'all';
    const statusFilter = document.getElementById('unavailStatusFilter')?.value || 'all';
    const serviceTypeFilter = document.getElementById('serviceTypeFilter')?.value || 'all';

    const response = await fetch(`/api/admin/data-management/unavailability-requests?` + new URLSearchParams({
      year: yearFilter,
      faculty: facultyFilter,
      status: statusFilter
    }), {
      credentials: 'same-origin'
    });

    if (!response.ok) throw new Error('Failed to load data');

    unavailabilityData = await response.json();
    selectedUnavail.clear();

    // Cache the full faculty list the first time we load with no faculty filter
    if (facultyFilter === 'all' || allFacultyNames.length === 0) {
      allFacultyNames = [...new Set(unavailabilityData.map(r => r.faculty_name))].sort();
    }

    // Build week index
    buildWeekIndex(serviceTypeFilter);

    // Populate service type filter
    loadServiceTypeFilters();

    renderWeekSelector();
    renderUnavailabilityTable();
    updateUnavailStats();
    loadFacultyFilters();

    showDataAlert('', 'clear');
  } catch (error) {
    showDataAlert(`Error: ${error.message}`, 'error');
  }
}

function buildWeekIndex(serviceTypeFilter = 'all') {
  availableWeeks.clear();
  availableServiceTypes.clear();

  // First, generate all 52 weeks (1-52)
  for (let i = 1; i <= 52; i++) {
    availableWeeks.set(`week-${i}`, {
      label: `Week ${i}`,
      number: i,
      count: 0,
      service_types: new Set(),
      has_data: false
    });
  }

  // Then populate with actual data
  unavailabilityData.forEach(req => {
    availableServiceTypes.add(req.service_type || 'Unknown');

    // Filter by service type if specified
    if (serviceTypeFilter !== 'all' && req.service_type !== serviceTypeFilter) {
      return;
    }

    // Find matching week (by week_id or week_number)
    let weekKey = null;
    if (req.week_id && availableWeeks.has(req.week_id)) {
      weekKey = req.week_id;
    } else if (req.week_number) {
      weekKey = `week-${req.week_number}`;
    }

    if (weekKey && availableWeeks.has(weekKey)) {
      const week = availableWeeks.get(weekKey);
      week.count++;
      week.has_data = true;
      week.service_types.add(req.service_type || 'Unknown');
      // Keep the actual label if we got it from the data
      if (req.week_label) week.label = req.week_label;
    }
  });
}

function renderWeekSelector() {
  const weeksList = document.getElementById('weeksList');

  if (availableWeeks.size === 0) {
    weeksList.innerHTML = `<div style="padding: 16px; text-align: center; color: #9ca3af; font-size: 13px;">No weeks found</div>`;
    return;
  }

  // Sort weeks by number
  const sortedWeeks = Array.from(availableWeeks.entries())
    .sort((a, b) => (a[1].number || 0) - (b[1].number || 0));

  weeksList.innerHTML = sortedWeeks.map(([weekId, week]) => {
    const isSelected = selectedWeekId === weekId;
    const serviceTypesStr = week.count > 0 ? Array.from(week.service_types).join(', ') : 'No data';
    const dataIndicator = week.has_data
      ? '<span style="display: inline-block; width: 8px; height: 8px; background: #10b981; border-radius: 50%; margin-right: 4px;"></span>'
      : '<span style="display: inline-block; width: 8px; height: 8px; background: #d1d5db; border-radius: 50%; margin-right: 4px;"></span>';

    return `
      <button class="week-selector-btn ${isSelected ? 'active' : ''}"
        onclick="selectWeek('${weekId}', '${week.label}')"
        style="
          display: block;
          width: 100%;
          padding: 12px;
          border: none;
          border-bottom: 1px solid #f3f4f6;
          text-align: left;
          background: ${isSelected ? '#dbeafe' : (week.has_data ? '#f0fdf4' : 'white')};
          color: ${isSelected ? '#1e40af' : '#374151'};
          cursor: ${week.has_data ? 'pointer' : 'default'};
          font-size: 13px;
          transition: background 0.15s;
          opacity: ${week.has_data ? '1' : '0.6'};
        }"
        onmouseover="if (${week.has_data}) this.style.background = this.style.background !== '#dbeafe' ? '#f9fafb' : '#dbeafe'"
        onmouseout="this.style.background = '${isSelected ? '#dbeafe' : (week.has_data ? '#f0fdf4' : 'white')}'"
      >
        <div style="font-weight: 600; margin-bottom: 4px; display: flex; align-items: center;">
          ${dataIndicator}
          ${week.label}
        </div>
        <div style="font-size: 11px; opacity: 0.7; margin-left: 12px;">
          ${week.count > 0 ? `${week.count} entry(ies)` : 'No entries'}
        </div>
        ${week.count > 0 ? `<div style="font-size: 11px; opacity: 0.6; margin-top: 4px; margin-left: 12px;">${serviceTypesStr}</div>` : ''}
      </button>
    `;
  }).join('');
}

function selectWeek(weekId, weekLabel) {
  selectedWeekId = weekId;
  selectedWeekLabel = weekLabel;
  renderWeekSelector();

  // Show week actions panel and highlight selection
  const panel = document.getElementById('weekActionsPanel');
  const info = document.getElementById('selectedWeekInfo');
  const week = availableWeeks.get(weekId);

  panel.style.display = 'block';
  info.textContent = `${weekLabel} (${week.count} entries)`;

  renderUnavailabilityTable();
  updateUnavailStats();
}

function clearWeekSelection() {
  selectedWeekId = null;
  selectedWeekLabel = null;
  document.getElementById('weekActionsPanel').style.display = 'none';
  renderWeekSelector();
  renderUnavailabilityTable();
  updateUnavailStats();
}

async function deleteSelectedWeekData() {
  if (!selectedWeekId) {
    showDataAlert('No week selected', 'warning');
    return;
  }

  const week = availableWeeks.get(selectedWeekId);
  const confirmed = confirm(
    `DELETE ALL ENTRIES FOR ${selectedWeekLabel}?\n\n` +
    `This will permanently delete ${week.count} service availability request(s).\n\n` +
    `This action cannot be undone. Continue?`
  );

  if (!confirmed) return;

  try {
    showDataAlert(`Deleting week ${selectedWeekLabel}...`, 'info');

    // Get all IDs for this week (match by week_id or week_number)
    const weekEntryIds = unavailabilityData
      .filter(req =>
        req.week_id === selectedWeekId ||
        String(req.week_number) === String(selectedWeekId).replace('week-', '')
      )
      .map(req => req.id);

    const response = await fetch('/api/admin/data-management/delete-unavailability', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        request_ids: weekEntryIds
      })
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Delete failed');
    }

    const result = await response.json();
    showDataAlert(`Deleted ${result.deleted_count} entries from ${selectedWeekLabel}`, 'success');

    // Clear selection and reload
    clearWeekSelection();
    await loadUnavailabilityData();

  } catch (error) {
    showDataAlert(`Error: ${error.message}`, 'error');
  }
}

function renderUnavailabilityTable() {
  const tbody = document.getElementById('unavailTableBody');
  if (!tbody) return;

  // Filter by selected week if one is selected (match on week_number for reliability)
  let filteredData = unavailabilityData;
  if (selectedWeekId) {
    filteredData = unavailabilityData.filter(req =>
      req.week_id === selectedWeekId || String(req.week_number) === String(selectedWeekId).replace('week-', '')
    );
  }

  if (filteredData.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="9" style="text-align: center; padding: 40px; color: #9ca3af;">
          No requests found. Try adjusting the filters.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = filteredData.map(req => {
    const isSelected = selectedUnavail.has(String(req.id));
    const isWaveDraft = req.source === 'Wave Draft';
    const statusBadge = req.status === 'unavailable'
      ? '<span class="badge badge-inactive">Unavailable</span>'
      : '<span class="badge badge-active">Available</span>';
    const sourceBadge = isWaveDraft
      ? '<span style="font-size:11px; background:#ede9fe; color:#5b21b6; padding:2px 7px; border-radius:10px; font-weight:600;">Wave Draft</span>'
      : '<span style="font-size:11px; background:#e0f2fe; color:#0369a1; padding:2px 7px; border-radius:10px; font-weight:600;">Direct</span>';

    const rowStyle = isSelected ? 'background:#dbeafe;' : '';

    return `
      <tr id="unavail-row-${req.id}" style="${rowStyle}">
        <td>
          <input type="checkbox"
            id="unavail-cb-${req.id}"
            ${isSelected ? 'checked' : ''}
            onclick="handleUnavailCheck('${req.id}', this)">
        </td>
        <td>${req.faculty_name}</td>
        <td>${req.week_label}</td>
        <td>${req.week_number}</td>
        <td>${statusBadge}</td>
        <td>${req.points_spent || 0}</td>
        <td>${req.points_earned || 0}</td>
        <td>${new Date(req.created_at).toLocaleDateString()}</td>
        <td>${sourceBadge}</td>
      </tr>
    `;
  }).join('');
}

function handleUnavailCheck(id, checkbox) {
  const strId = String(id);
  const row = document.getElementById(`unavail-row-${id}`);
  if (checkbox.checked) {
    selectedUnavail.add(strId);
    if (row) row.style.background = '#dbeafe';
  } else {
    selectedUnavail.delete(strId);
    if (row) row.style.background = '';
  }
  updateUnavailStats();
}

function toggleUnavailSelection(id) {
  if (selectedUnavail.has(id)) {
    selectedUnavail.delete(id);
  } else {
    selectedUnavail.add(id);
  }
  updateUnavailStats();
  renderUnavailabilityTable();
}

function toggleAllUnavail(checkbox) {
  if (checkbox.checked) {
    selectAllUnavail();
  } else {
    deselectAllUnavail();
  }
}

function selectAllUnavail() {
  // Select all visible (filtered) items
  let dataToSelect = unavailabilityData;
  if (selectedWeekId) {
    dataToSelect = unavailabilityData.filter(req =>
      req.week_id === selectedWeekId || String(req.week_number) === String(selectedWeekId).replace('week-', '')
    );
  }
  dataToSelect.forEach(req => selectedUnavail.add(String(req.id)));
  updateUnavailStats();
  renderUnavailabilityTable();
  const cb = document.getElementById('selectAllUnavailCheckbox');
  if (cb) cb.checked = true;
}

function deselectAllUnavail() {
  selectedUnavail.clear();
  updateUnavailStats();
  renderUnavailabilityTable();
  const cb = document.getElementById('selectAllUnavailCheckbox');
  if (cb) cb.checked = false;
}

function updateUnavailStats() {
  // Use filtered data if a week is selected
  let dataToCount = unavailabilityData;
  if (selectedWeekId) {
    dataToCount = unavailabilityData.filter(r => r.week_id === selectedWeekId);
  }

  const unavailable = dataToCount.filter(r => r.status === 'unavailable').length;
  const available = dataToCount.filter(r => r.status === 'available').length;

  document.getElementById('unavailTotalCount').textContent = dataToCount.length;
  document.getElementById('unavailSelectedSum').textContent = selectedUnavail.size;
  document.getElementById('unavailUnavailableCount').textContent = unavailable;
  document.getElementById('unavailAvailableCount').textContent = available;
  document.getElementById('unavailSelectedCount').textContent = selectedUnavail.size;

  // Enable/disable delete button
  const deleteBtn = document.getElementById('deleteUnavailBtn');
  deleteBtn.disabled = selectedUnavail.size === 0;
}

async function deleteSelectedUnavail() {
  if (selectedUnavail.size === 0) {
    showDataAlert('No items selected', 'warning');
    return;
  }

  const selectedRecords = unavailabilityData.filter(req => selectedUnavail.has(String(req.id)));
  const waveDraftCount = selectedRecords.filter(r => r.source === 'Wave Draft').length;
  const waveDraftWarning = waveDraftCount > 0
    ? `\n${waveDraftCount} of these are Wave Draft entries.\n`
    : '';

  const confirmed = confirm(
    `DELETE ${selectedUnavail.size} UNAVAILABILITY REQUEST(S)?\n` +
    waveDraftWarning +
    `\nThis will permanently delete ${selectedUnavail.size} service availability record(s).\n` +
    `This action cannot be undone. Continue?`
  );

  if (!confirmed) return;

  try {
    showDataAlert('Deleting requests...', 'info');

    // Build sources map so backend knows which table each ID belongs to
    const sourcesMap = {};
    selectedRecords.forEach(r => { sourcesMap[String(r.id)] = r.source; });

    const response = await fetch('/api/admin/data-management/delete-unavailability', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        request_ids: Array.from(selectedUnavail),
        sources: sourcesMap
      })
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Delete failed');
    }

    const result = await response.json();
    showDataAlert(`Deleted ${result.deleted_count} requests successfully`, 'success');

    // Reload data
    await loadUnavailabilityData();

  } catch (error) {
    showDataAlert(`Error: ${error.message}`, 'error');
  }
}

function exportUnavailData() {
  if (selectedUnavail.size === 0) {
    showDataAlert('No items selected to export', 'warning');
    return;
  }

  const selectedData = unavailabilityData.filter(req => selectedUnavail.has(req.id));
  const csv = convertToCSV(selectedData, [
    'id', 'faculty_id', 'faculty_name', 'week_id', 'week_label',
    'week_number', 'status', 'points_spent', 'points_earned', 'created_at', 'source'
  ]);

  downloadCSV(csv, `unavailability-requests-${new Date().toISOString().split('T')[0]}.csv`);
  showDataAlert(`Exported ${selectedUnavail.size} records`, 'success');
}

// ==================== MOONLIGHTING SIGNUPS ====================

async function loadMoonlightingData() {
  try {
    showDataAlert('Loading moonlighting signups...', 'info');

    const monthFilter = document.getElementById('moonlightMonthFilter')?.value || 'all';
    const facultyFilter = document.getElementById('moonlightProviderFilter')?.value || 'all';

    const response = await fetch(`/api/admin/data-management/moonlighting-signups?` + new URLSearchParams({
      month: monthFilter,
      faculty_filter: facultyFilter
    }), {
      credentials: 'same-origin'
    });

    if (!response.ok) throw new Error('Failed to load data');

    moonlightingData = await response.json();
    selectedMoonlight.clear();

    // Cache full provider list on first load
    if (facultyFilter === 'all' || allProviderIds.length === 0) {
      allProviderIds = [...new Set(moonlightingData.map(s => s.faculty_id))].sort();
    }

    renderMoonlightingTable();
    updateMoonlightStats();
    loadProviderFilters();
    loadMonthFilters();

    showDataAlert('', 'clear');
  } catch (error) {
    showDataAlert(`Error: ${error.message}`, 'error');
  }
}

function renderMoonlightingTable() {
  const tbody = document.getElementById('moonlightTableBody');

  if (moonlightingData.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="7" style="text-align: center; padding: 40px; color: #9ca3af;">
          No signups found. Try adjusting the filters.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = moonlightingData.map(signup => {
    const isSelected = selectedMoonlight.has(signup.id);

    return `
      <tr class="${isSelected ? 'selected-row' : ''}" data-row-id="${signup.id}">
        <td>
          <input type="checkbox"
            ${isSelected ? 'checked' : ''}>
        </td>
        <td>${signup.faculty_id}</td>
        <td>${signup.faculty_name || 'N/A'}</td>
        <td>${signup.month_label}</td>
        <td>${signup.desired_nights}</td>
        <td>${signup.locked_dates_count || 0}</td>
        <td>${new Date(signup.created_at).toLocaleDateString()}</td>
      </tr>
    `;
  }).join('');

  // Remove old event listener if it exists
  if (tbody.checkboxListener) {
    tbody.removeEventListener('change', tbody.checkboxListener);
  }

  // Add event delegation for checkboxes at tbody level
  tbody.checkboxListener = function(e) {
    if (e.target.tagName !== 'INPUT' || e.target.type !== 'checkbox') return;

    const row = e.target.closest('tr');
    if (!row) return;

    const rowId = row.dataset.rowId;
    if (!rowId) return;

    if (e.target.checked) {
      selectedMoonlight.add(rowId);
      row.classList.add('selected-row');
    } else {
      selectedMoonlight.delete(rowId);
      row.classList.remove('selected-row');
    }

    updateMoonlightStats();
  };

  tbody.addEventListener('change', tbody.checkboxListener);
}

function toggleMoonlightSelection(id) {
  if (selectedMoonlight.has(id)) {
    selectedMoonlight.delete(id);
  } else {
    selectedMoonlight.add(id);
  }
  updateMoonlightStats();
  renderMoonlightingTable();
}

function toggleAllMoonlight(checkbox) {
  if (checkbox.checked) {
    selectAllMoonlight();
  } else {
    deselectAllMoonlight();
  }
}

function selectAllMoonlight() {
  moonlightingData.forEach(signup => selectedMoonlight.add(signup.id));
  updateMoonlightStats();
  renderMoonlightingTable();
  document.getElementById('selectAllMoonlightCheckbox').checked = true;
}

function deselectAllMoonlight() {
  selectedMoonlight.clear();
  updateMoonlightStats();
  renderMoonlightingTable();
  document.getElementById('selectAllMoonlightCheckbox').checked = false;
}

function updateMoonlightStats() {
  const facultyCount = new Set(moonlightingData.map(s => s.faculty_id)).size;

  document.getElementById('moonlightTotalCount').textContent = moonlightingData.length;
  document.getElementById('moonlightSelectedSum').textContent = selectedMoonlight.size;
  document.getElementById('moonlightProvidersCount').textContent = facultyCount;
  document.getElementById('moonlightSelectedCount').textContent = selectedMoonlight.size;

  // Enable/disable delete button
  const deleteBtn = document.getElementById('deleteMoonlightBtn');
  deleteBtn.disabled = selectedMoonlight.size === 0;
}

async function deleteSelectedMoonlight() {
  if (selectedMoonlight.size === 0) {
    showDataAlert('No items selected', 'warning');
    return;
  }

  const confirmed = confirm(
    `DELETE ${selectedMoonlight.size} MOONLIGHTING SIGNUPS?\n\n` +
    `This will permanently delete ${selectedMoonlight.size} moonlighting signup records.\n\n` +
    `This action cannot be undone. Continue?`
  );

  if (!confirmed) return;

  try {
    showDataAlert('Deleting signups...', 'info');

    const response = await fetch('/api/admin/data-management/delete-moonlighting', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        signup_ids: Array.from(selectedMoonlight)
      })
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Delete failed');
    }

    const result = await response.json();
    showDataAlert(`Deleted ${result.deleted_count} signups successfully`, 'success');

    // Reload data
    await loadMoonlightingData();

  } catch (error) {
    showDataAlert(`Error: ${error.message}`, 'error');
  }
}

function exportMoonlightData() {
  if (selectedMoonlight.size === 0) {
    showDataAlert('No items selected to export', 'warning');
    return;
  }

  const selectedData = moonlightingData.filter(signup => selectedMoonlight.has(signup.id));
  const csv = convertToCSV(selectedData, [
    'id', 'faculty_id', 'faculty_name', 'month_id', 'month_label',
    'desired_nights', 'locked_dates_count', 'created_at'
  ]);

  downloadCSV(csv, `moonlighting-signups-${new Date().toISOString().split('T')[0]}.csv`);
  showDataAlert(`Exported ${selectedMoonlight.size} records`, 'success');
}

// ==================== SERVICE WEEK ASSIGNMENTS ====================

let assignmentsData = [];
let selectedAssignments = new Set();

async function loadAssignmentsData() {
  try {
    showDataAlert('Loading service assignments...', 'info');

    const yearFilter    = document.getElementById('assignYearFilter')?.value || 'all';
    const facultyFilter = document.getElementById('assignFacultyFilter')?.value || 'all';
    const serviceFilter = document.getElementById('assignServiceFilter')?.value || 'all';

    const response = await fetch('/api/admin/data-management/service-assignments?' + new URLSearchParams({
      year: yearFilter,
      faculty: facultyFilter,
      service_type: serviceFilter
    }), { credentials: 'same-origin' });

    if (!response.ok) throw new Error('Failed to load assignments');

    assignmentsData = await response.json();
    selectedAssignments.clear();

    // Cache full faculty list on first load
    if (facultyFilter === 'all' || allAssignFacultyNames.length === 0) {
      allAssignFacultyNames = [...new Set(assignmentsData.map(a => a.faculty_name))].sort();
    }

    renderAssignmentsTable();
    updateAssignmentStats();
    loadAssignmentFacultyFilter();
    loadAssignmentServiceFilter();
    showDataAlert('', 'clear');
  } catch (error) {
    showDataAlert(`Error: ${error.message}`, 'error');
  }
}

function renderAssignmentsTable() {
  const tbody = document.getElementById('assignTableBody');
  if (!tbody) return;

  if (assignmentsData.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:40px;color:#9ca3af;">No assignments found.</td></tr>`;
    return;
  }

  tbody.innerHTML = assignmentsData.map(a => {
    const isSelected = selectedAssignments.has(String(a.id));
    const rowStyle = isSelected ? 'background:#dbeafe;' : '';
    const typeBadge = `<span style="font-size:11px;background:#f0fdf4;color:#166534;padding:2px 8px;border-radius:10px;font-weight:600;">${a.service_type}</span>`;
    const sourceBadge = a.is_manual
      ? '<span style="font-size:11px;background:#fef9c3;color:#854d0e;padding:2px 7px;border-radius:10px;font-weight:600;">Manual</span>'
      : a.imported
        ? '<span style="font-size:11px;background:#e0f2fe;color:#0369a1;padding:2px 7px;border-radius:10px;font-weight:600;">Imported</span>'
        : '<span style="font-size:11px;background:#f3f4f6;color:#374151;padding:2px 7px;border-radius:10px;font-weight:600;">Generated</span>';

    return `
      <tr id="assign-row-${a.id}" style="${rowStyle}">
        <td><input type="checkbox" id="assign-cb-${a.id}" ${isSelected ? 'checked' : ''} onclick="handleAssignCheck('${a.id}', this)"></td>
        <td>${a.faculty_name}</td>
        <td>${a.week_label}</td>
        <td>${a.week_number}</td>
        <td>${typeBadge}</td>
        <td>${new Date(a.created_at).toLocaleDateString()}</td>
        <td>${sourceBadge}</td>
      </tr>`;
  }).join('');
}

function handleAssignCheck(id, checkbox) {
  const strId = String(id);
  const row = document.getElementById(`assign-row-${id}`);
  if (checkbox.checked) {
    selectedAssignments.add(strId);
    if (row) row.style.background = '#dbeafe';
  } else {
    selectedAssignments.delete(strId);
    if (row) row.style.background = '';
  }
  updateAssignmentStats();
}

function updateAssignmentStats() {
  const el = id => document.getElementById(id);
  if (el('assignTotalCount'))    el('assignTotalCount').textContent    = assignmentsData.length;
  if (el('assignSelectedCount')) el('assignSelectedCount').textContent = selectedAssignments.size;
  const btn = el('deleteAssignBtn');
  if (btn) btn.disabled = selectedAssignments.size === 0;
}

function selectAllAssignments() {
  assignmentsData.forEach(a => selectedAssignments.add(String(a.id)));
  updateAssignmentStats();
  renderAssignmentsTable();
  const cb = document.getElementById('selectAllAssignCheckbox');
  if (cb) cb.checked = true;
}

function deselectAllAssignments() {
  selectedAssignments.clear();
  updateAssignmentStats();
  renderAssignmentsTable();
  const cb = document.getElementById('selectAllAssignCheckbox');
  if (cb) cb.checked = false;
}

function toggleAllAssignments(checkbox) {
  if (checkbox.checked) selectAllAssignments(); else deselectAllAssignments();
}

async function deleteSelectedAssignments() {
  if (selectedAssignments.size === 0) { showDataAlert('No items selected', 'warning'); return; }

  const confirmed = confirm(
    `DELETE ${selectedAssignments.size} SERVICE ASSIGNMENT(S)?\n\n` +
    `This removes actual schedule blocks — the provider will no longer be assigned to those weeks.\n\n` +
    `This action cannot be undone. Continue?`
  );
  if (!confirmed) return;

  try {
    showDataAlert('Deleting assignments...', 'info');
    const response = await fetch('/api/admin/data-management/delete-assignments', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ assignment_ids: Array.from(selectedAssignments) })
    });
    if (!response.ok) { const e = await response.json(); throw new Error(e.detail || 'Delete failed'); }
    const result = await response.json();
    showDataAlert(`Deleted ${result.deleted_count} assignment(s)`, 'success');
    await loadAssignmentsData();
  } catch (error) {
    showDataAlert(`Error: ${error.message}`, 'error');
  }
}

function loadAssignmentFacultyFilter() {
  const select = document.getElementById('assignFacultyFilter');
  if (!select) return;
  const current = select.value;
  select.innerHTML = '<option value="all">All Faculty</option>' +
    allAssignFacultyNames.map(n => `<option value="${n}">${n}</option>`).join('');
  if (current && current !== 'all') select.value = current;
}

function loadAssignmentServiceFilter() {
  const select = document.getElementById('assignServiceFilter');
  if (!select) return;
  const current = select.value;
  const types = [...new Set(assignmentsData.map(a => a.service_type))].sort();
  select.innerHTML = '<option value="all">All Services</option>' +
    types.map(t => `<option value="${t}">${t}</option>`).join('');
  if (current && types.includes(current)) select.value = current;
}

// ==================== UTILITIES ====================

function loadServiceTypeFilters() {
  const select = document.getElementById('serviceTypeFilter');
  if (!select) return;

  const serviceTypes = Array.from(availableServiceTypes).sort();
  select.innerHTML = '<option value="all">All Services</option>' +
    serviceTypes.map(type => `<option value="${type}">${type}</option>`).join('');
}

async function loadFacultyFilters() {
  const select = document.getElementById('unavailFacultyFilter');
  if (!select) return;

  const currentValue = select.value; // preserve selection before rebuild

  // Always use the full cached list so selecting a faculty doesn't lock the dropdown
  select.innerHTML = '<option value="all">All Faculty</option>' +
    allFacultyNames.map(name => `<option value="${name}">${name}</option>`).join('');

  // Restore previous selection
  if (currentValue && currentValue !== 'all') {
    select.value = currentValue;
  }
}

async function loadProviderFilters() {
  const select = document.getElementById('moonlightProviderFilter');
  if (!select) return;

  const currentValue = select.value;

  select.innerHTML = '<option value="all">All Providers</option>' +
    allProviderIds.map(id => `<option value="${id}">${id}</option>`).join('');

  if (currentValue && currentValue !== 'all') {
    select.value = currentValue;
  }
}

async function loadMonthFilters() {
  const select = document.getElementById('moonlightMonthFilter');

  // Create unique month entries with both id and label
  const monthMap = new Map();
  moonlightingData.forEach(s => {
    if (!monthMap.has(s.month_id)) {
      monthMap.set(s.month_id, s.month_label);
    }
  });

  // Sort by label
  const months = Array.from(monthMap.entries()).sort((a, b) => a[1].localeCompare(b[1]));

  select.innerHTML = '<option value="all">All Months</option>' +
    months.map(([id, label]) => `<option value="${id}">${label}</option>`).join('');
}

function convertToCSV(data, columns) {
  const headers = columns.join(',');
  const rows = data.map(row =>
    columns.map(col => {
      const value = row[col] || '';
      return `"${String(value).replace(/"/g, '""')}"`;
    }).join(',')
  );
  return [headers, ...rows].join('\n');
}

function downloadCSV(csv, filename) {
  const blob = new Blob([csv], { type: 'text/csv' });
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  window.URL.revokeObjectURL(url);
}

function showDataAlert(message, type) {
  const alert = document.getElementById('dataManagementAlert');
  if (type === 'clear') {
    alert.style.display = 'none';
    return;
  }

  alert.textContent = message;
  alert.className = `alert alert-${type}`;
  alert.style.display = 'block';

  if (type === 'success' || type === 'info') {
    setTimeout(() => showDataAlert('', 'clear'), 3000);
  }
}

// ==================== GLOBAL FUNCTION EXPORTS ====================
// Make functions globally accessible for inline onclick handlers

window.showDataTab = showDataTab;
window.loadUnavailabilityData = loadUnavailabilityData;
window.loadMoonlightingData = loadMoonlightingData;
window.selectAllUnavail = selectAllUnavail;
window.deselectAllUnavail = deselectAllUnavail;
window.selectAllMoonlight = selectAllMoonlight;
window.deselectAllMoonlight = deselectAllMoonlight;
window.toggleAllUnavail = toggleAllUnavail;
window.toggleAllMoonlight = toggleAllMoonlight;
window.toggleUnavailSelection = toggleUnavailSelection;
window.toggleMoonlightSelection = toggleMoonlightSelection;
window.deleteSelectedUnavail = deleteSelectedUnavail;
window.deleteSelectedMoonlight = deleteSelectedMoonlight;
window.exportUnavailData = exportUnavailData;
window.exportMoonlightData = exportMoonlightData;
window.selectWeek = selectWeek;
window.clearWeekSelection = clearWeekSelection;
window.deleteSelectedWeekData = deleteSelectedWeekData;
window.buildWeekIndex = buildWeekIndex;
window.renderWeekSelector = renderWeekSelector;
window.loadServiceTypeFilters = loadServiceTypeFilters;
window.handleUnavailCheck = handleUnavailCheck;
window.handleAssignCheck = handleAssignCheck;
window.loadAssignmentsData = loadAssignmentsData;
window.selectAllAssignments = selectAllAssignments;
window.deselectAllAssignments = deselectAllAssignments;
window.toggleAllAssignments = toggleAllAssignments;
window.deleteSelectedAssignments = deleteSelectedAssignments;
window.initDataManagement = initDataManagement;

function initDataManagement() {
  // Reset state on each module load so stale selections don't carry over
  selectedUnavail.clear();
  selectedMoonlight.clear();
  selectedAssignments.clear();
  selectedWeekId = null;
  selectedWeekLabel = null;
  unavailabilityData = [];
  moonlightingData = [];
  assignmentsData = [];
  allFacultyNames = [];
  allProviderIds = [];
  allAssignFacultyNames = [];
  loadUnavailabilityData();
}
