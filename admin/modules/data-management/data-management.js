/**
 * Data Management Module
 * Surgical data cleanup for beta test data
 */

let unavailabilityData = [];
let moonlightingData = [];
let selectedUnavail = new Set();
let selectedMoonlight = new Set();

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
  }
}

// ==================== UNAVAILABILITY REQUESTS ====================

async function loadUnavailabilityData() {
  try {
    showDataAlert('Loading unavailability requests...', 'info');

    const yearFilter = document.getElementById('unavailYearFilter').value;
    const facultyFilter = document.getElementById('unavailFacultyFilter').value;
    const statusFilter = document.getElementById('unavailStatusFilter').value;
    const dateFilter = document.getElementById('unavailDateFilter').value;

    const response = await fetch(`/api/admin/data-management/unavailability-requests?` + new URLSearchParams({
      year: yearFilter,
      faculty: facultyFilter,
      status: statusFilter,
      date_range: dateFilter
    }), {
      credentials: 'same-origin'
    });

    if (!response.ok) throw new Error('Failed to load data');

    unavailabilityData = await response.json();
    selectedUnavail.clear();

    renderUnavailabilityTable();
    updateUnavailStats();
    loadFacultyFilters();

    showDataAlert('', 'clear');
  } catch (error) {
    showDataAlert(`Error: ${error.message}`, 'error');
  }
}

function renderUnavailabilityTable() {
  const tbody = document.getElementById('unavailTableBody');

  if (unavailabilityData.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="8" style="text-align: center; padding: 40px; color: #9ca3af;">
          No requests found. Try adjusting the filters.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = unavailabilityData.map(req => {
    const isSelected = selectedUnavail.has(req.id);
    const statusBadge = req.status === 'unavailable'
      ? '<span class="badge badge-inactive">Unavailable</span>'
      : '<span class="badge badge-active">Available</span>';

    return `
      <tr class="${isSelected ? 'selected-row' : ''}">
        <td>
          <input type="checkbox"
            ${isSelected ? 'checked' : ''}
            onchange="toggleUnavailSelection('${req.id}')">
        </td>
        <td>${req.faculty_name}</td>
        <td>${req.week_label}</td>
        <td>${req.week_number}</td>
        <td>${statusBadge}</td>
        <td>${req.points_spent || 0}</td>
        <td>${req.points_earned || 0}</td>
        <td>${new Date(req.created_at).toLocaleDateString()}</td>
      </tr>
    `;
  }).join('');
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
  unavailabilityData.forEach(req => selectedUnavail.add(req.id));
  updateUnavailStats();
  renderUnavailabilityTable();
  document.getElementById('selectAllUnavailCheckbox').checked = true;
}

function deselectAllUnavail() {
  selectedUnavail.clear();
  updateUnavailStats();
  renderUnavailabilityTable();
  document.getElementById('selectAllUnavailCheckbox').checked = false;
}

function updateUnavailStats() {
  const unavailable = unavailabilityData.filter(r => r.status === 'unavailable').length;
  const available = unavailabilityData.filter(r => r.status === 'available').length;

  document.getElementById('unavailTotalCount').textContent = unavailabilityData.length;
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

  const confirmed = confirm(
    `⚠️ DELETE ${selectedUnavail.size} UNAVAILABILITY REQUESTS?\n\n` +
    `This will permanently delete ${selectedUnavail.size} service availability requests.\n\n` +
    `This action cannot be undone. Continue?`
  );

  if (!confirmed) return;

  try {
    showDataAlert('Deleting requests...', 'info');

    const response = await fetch('/api/admin/data-management/delete-unavailability', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        request_ids: Array.from(selectedUnavail)
      })
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Delete failed');
    }

    const result = await response.json();
    showDataAlert(`✅ Deleted ${result.deleted_count} requests successfully`, 'success');

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
    'week_number', 'status', 'points_spent', 'points_earned', 'created_at'
  ]);

  downloadCSV(csv, `unavailability-requests-${new Date().toISOString().split('T')[0]}.csv`);
  showDataAlert(`Exported ${selectedUnavail.size} records`, 'success');
}

// ==================== MOONLIGHTING SIGNUPS ====================

async function loadMoonlightingData() {
  try {
    showDataAlert('Loading moonlighting signups...', 'info');

    const monthFilter = document.getElementById('moonlightMonthFilter').value;
    const providerFilter = document.getElementById('moonlightProviderFilter').value;

    const response = await fetch(`/api/admin/data-management/moonlighting-signups?` + new URLSearchParams({
      month: monthFilter,
      provider: providerFilter
    }), {
      credentials: 'same-origin'
    });

    if (!response.ok) throw new Error('Failed to load data');

    moonlightingData = await response.json();
    selectedMoonlight.clear();

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
      <tr class="${isSelected ? 'selected-row' : ''}">
        <td>
          <input type="checkbox"
            ${isSelected ? 'checked' : ''}
            onchange="toggleMoonlightSelection(${signup.id})">
        </td>
        <td>${signup.provider_id}</td>
        <td>${signup.provider_name || 'N/A'}</td>
        <td>${signup.month_label}</td>
        <td>${signup.desired_nights}</td>
        <td>${signup.locked_dates_count || 0}</td>
        <td>${new Date(signup.created_at).toLocaleDateString()}</td>
      </tr>
    `;
  }).join('');
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
  const providers = new Set(moonlightingData.map(s => s.provider_id)).size;

  document.getElementById('moonlightTotalCount').textContent = moonlightingData.length;
  document.getElementById('moonlightSelectedSum').textContent = selectedMoonlight.size;
  document.getElementById('moonlightProvidersCount').textContent = providers;
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
    `⚠️ DELETE ${selectedMoonlight.size} MOONLIGHTING SIGNUPS?\n\n` +
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
    showDataAlert(`✅ Deleted ${result.deleted_count} signups successfully`, 'success');

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
    'id', 'provider_id', 'provider_name', 'month_id', 'month_label',
    'desired_nights', 'locked_dates_count', 'created_at'
  ]);

  downloadCSV(csv, `moonlighting-signups-${new Date().toISOString().split('T')[0]}.csv`);
  showDataAlert(`Exported ${selectedMoonlight.size} records`, 'success');
}

// ==================== UTILITIES ====================

async function loadFacultyFilters() {
  // Populate faculty filter dropdown
  const select = document.getElementById('unavailFacultyFilter');
  const faculty = [...new Set(unavailabilityData.map(r => r.faculty_name))].sort();

  select.innerHTML = '<option value="all">All Faculty</option>' +
    faculty.map(name => `<option value="${name}">${name}</option>`).join('');
}

async function loadProviderFilters() {
  const select = document.getElementById('moonlightProviderFilter');
  const providers = [...new Set(moonlightingData.map(s => s.provider_id))].sort();

  select.innerHTML = '<option value="all">All Providers</option>' +
    providers.map(id => `<option value="${id}">${id}</option>`).join('');
}

async function loadMonthFilters() {
  const select = document.getElementById('moonlightMonthFilter');
  const months = [...new Set(moonlightingData.map(s => s.month_label))].sort();

  select.innerHTML = '<option value="all">All Months</option>' +
    months.map(label => `<option value="${label}">${label}</option>`).join('');
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

// Initialize on module load
document.addEventListener('DOMContentLoaded', () => {
  loadUnavailabilityData();
});
