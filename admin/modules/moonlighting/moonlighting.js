/**
 * Moonlighting Management Module
 * Manage night shift signups, generate schedules, export data
 */

let allSignups = [];
let allAssignments = [];
let allProviders = [];
let currentMoonlightingTab = 'signups';

// Load on init
document.addEventListener('DOMContentLoaded', function() {
  if (document.getElementById('signupsTableBody')) {
    loadProviders();
    loadSignups();
  }
});

// Show moonlighting sub-tab
function showMoonlightingTab(tabId) {
  // Update buttons
  document.querySelectorAll('.sub-tab-btn').forEach(function(btn) {
    btn.classList.remove('active');
  });
  event.target.classList.add('active');

  // Update content
  document.querySelectorAll('.sub-tab-content').forEach(function(content) {
    content.classList.remove('active');
  });
  document.getElementById('moonlighting-' + tabId).classList.add('active');

  currentMoonlightingTab = tabId;

  // Load data for tab
  if (tabId === 'signups') {
    loadSignups();
  } else if (tabId === 'assignments') {
    loadAssignments();
  }
}

// Load providers for filters
async function loadProviders() {
  try {
    const response = await fetch('/api/providers', { credentials: 'same-origin' });
    if (!response.ok) return;

    const data = await response.json();
    allProviders = Array.isArray(data) ? data : (data.providers || []);

    // Populate provider dropdowns
    const signupsSelect = document.getElementById('signupsProvider');
    const assignmentsSelect = document.getElementById('assignmentsProvider');

    allProviders.forEach(function(provider) {
      const option1 = document.createElement('option');
      option1.value = provider.id;
      option1.textContent = provider.name;
      signupsSelect.appendChild(option1);

      const option2 = document.createElement('option');
      option2.value = provider.id;
      option2.textContent = provider.name;
      assignmentsSelect.appendChild(option2);
    });

  } catch (error) {
    console.error('Error loading providers:', error);
  }
}

// Load signups
async function loadSignups() {
  try {
    showAlert('moonlightingAlert', '', 'clear');

    const month = document.getElementById('signupsMonth').value;
    const provider = document.getElementById('signupsProvider').value;
    const status = document.getElementById('signupsStatus').value;

    const params = new URLSearchParams();
    if (month !== 'all') params.append('month', month);
    if (provider !== 'all') params.append('provider_id', provider);

    const response = await fetch('/api/admin/signups?' + params.toString(), { credentials: 'same-origin' });
    if (!response.ok) throw new Error('Failed to load signups');

    const data = await response.json();
    allSignups = Array.isArray(data) ? data : (data.signups || []);  // ✓ FIXED

    // Apply status filter
    let filtered = allSignups;
    if (status === 'locked') {
      filtered = allSignups.filter(function(s) { return s.locked; });
    } else if (status === 'flexible') {
      filtered = allSignups.filter(function(s) { return !s.locked; });
    }

    renderSignups(filtered);
    updateSignupsStats(filtered);

  } catch (error) {
    console.error('Error loading signups:', error);
    showAlert('moonlightingAlert', 'Failed to load signups: ' + error.message, 'error');
  }
}

// Render signups table
function renderSignups(signups) {
  const tbody = document.getElementById('signupsTableBody');

  if (signups.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" class="empty-state">' +
      '<div class="empty-state-icon">🌙</div>' +
      '<div class="empty-state-title">No Signups</div>' +
      '<div class="empty-state-description">No moonlighting signups found for selected filters</div>' +
      '</td></tr>';
    return;
  }

  tbody.innerHTML = '';

  signups.forEach(function(signup) {
    const row = document.createElement('tr');

    const date = new Date(signup.date);
    const dayOfWeek = date.toLocaleDateString('en-US', { weekday: 'long' });

    const lockedBadge = signup.locked
      ? '<span class="badge badge-danger">Locked</span>'
      : '<span class="badge badge-success">Flexible</span>';

    row.innerHTML = '<td>' + signup.provider_id + '</td>' +
                    '<td>' + signup.provider_name + '</td>' +
                    '<td>' + formatMonthYear(signup.month) + '</td>' +
                    '<td>' + formatDate(signup.date) + '</td>' +
                    '<td>' + dayOfWeek + '</td>' +
                    '<td style="text-align: center;">' + (signup.desired_nights || 0) + '</td>' +
                    '<td>' + lockedBadge + '</td>';

    tbody.appendChild(row);
  });
}

// Update signups stats
function updateSignupsStats(signups) {
  const uniqueProviderIds = new Set(signups.map(function(s) { return s.provider_id; }));
  const lockedCount = signups.filter(function(s) { return s.locked; }).length;
  const flexibleCount = signups.filter(function(s) { return !s.locked; }).length;

  document.getElementById('totalSignups').textContent = signups.length;
  document.getElementById('uniqueProviders').textContent = uniqueProviderIds.size;
  document.getElementById('lockedCount').textContent = lockedCount;
  document.getElementById('flexibleCount').textContent = flexibleCount;
}

// Format month/year from YYYY-MM string
function formatMonthYear(monthStr) {
  if (!monthStr) return '';
  const parts = monthStr.split('-');
  if (parts.length !== 2) return monthStr;

  const year = parts[0];
  const month = parseInt(parts[1]);
  const date = new Date(year, month - 1, 1);

  return date.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
}

// Export signups to CSV
function exportSignupsCSV() {
  if (allSignups.length === 0) {
    alert('No signups to export');
    return;
  }

  const month = document.getElementById('signupsMonth').value;
  const filename = month === 'all'
    ? 'moonlighting_signups_all.csv'
    : 'moonlighting_signups_' + month.replace('-', '_') + '.csv';

  // Prepare data for export
  const exportData = allSignups.map(function(signup) {
    const date = new Date(signup.date);
    const dayOfWeek = date.toLocaleDateString('en-US', { weekday: 'long' });

    return {
      'Provider ID': signup.provider_id,
      'Provider Name': signup.provider_name,
      'Month': signup.month,
      'Date': signup.date,
      'Day of Week': dayOfWeek,
      'Desired Nights': signup.desired_nights || 0,
      'Locked': signup.locked ? 'Yes' : 'No'
    };
  });

  exportToCSV(exportData, filename);
  showAlert('moonlightingAlert', 'Exported ' + exportData.length + ' signups to ' + filename, 'success');
}

// Load assignments
async function loadAssignments() {
  try {
    showAlert('moonlightingAlert', '', 'clear');

    const month = document.getElementById('assignmentsMonth').value;
    const provider = document.getElementById('assignmentsProvider').value;

    const params = new URLSearchParams();
    if (month !== 'all') params.append('month', month);
    if (provider !== 'all') params.append('provider_id', provider);

    const response = await fetch('/api/admin/assignments?' + params.toString(), { credentials: 'same-origin' });
    if (!response.ok) throw new Error('Failed to load assignments');

    const data = await response.json();
    allAssignments = Array.isArray(data) ? data : (data.assignments || []);  // ✓ FIXED

    renderAssignments(allAssignments);
    updateAssignmentsStats(allAssignments);

  } catch (error) {
    console.error('Error loading assignments:', error);
    showAlert('moonlightingAlert', 'Failed to load assignments: ' + error.message, 'error');
  }
}

// Render assignments table
function renderAssignments(assignments) {
  const tbody = document.getElementById('assignmentsTableBody');

  if (assignments.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="empty-state">' +
      '<div class="empty-state-icon">📋</div>' +
      '<div class="empty-state-title">No Assignments</div>' +
      '<div class="empty-state-description">No moonlighting assignments found. Generate a schedule to create assignments.</div>' +
      '</td></tr>';
    return;
  }

  tbody.innerHTML = '';

  assignments.forEach(function(assignment) {
    const row = document.createElement('tr');

    const date = new Date(assignment.date);
    const dayOfWeek = date.toLocaleDateString('en-US', { weekday: 'long' });

    row.innerHTML = '<td>' + assignment.provider_id + '</td>' +
                    '<td>' + assignment.provider_name + '</td>' +
                    '<td>' + assignment.shift_name + '</td>' +
                    '<td>' + formatDate(assignment.date) + '</td>' +
                    '<td>' + dayOfWeek + '</td>' +
                    '<td>' + formatMonthYear(assignment.month) + '</td>';

    tbody.appendChild(row);
  });
}

// Update assignments stats
function updateAssignmentsStats(assignments) {
  const uniqueProviderIds = new Set(assignments.map(function(a) { return a.provider_id; }));

  // Calculate coverage - assuming 63 total shifts
  const coveragePercent = assignments.length > 0
    ? Math.round((assignments.length / 63) * 100)
    : 0;

  document.getElementById('totalAssignments').textContent = assignments.length;
  document.getElementById('assignedProviders').textContent = uniqueProviderIds.size;
  document.getElementById('coveragePercent').textContent = coveragePercent + '%';
}

// Export assignments to CSV
function exportAssignmentsCSV() {
  if (allAssignments.length === 0) {
    alert('No assignments to export');
    return;
  }

  const month = document.getElementById('assignmentsMonth').value;
  const filename = month === 'all'
    ? 'moonlighting_assignments_all.csv'
    : 'moonlighting_assignments_' + month.replace('-', '_') + '.csv';

  // Prepare data for export
  const exportData = allAssignments.map(function(assignment) {
    const date = new Date(assignment.date);
    const dayOfWeek = date.toLocaleDateString('en-US', { weekday: 'long' });

    return {
      'Provider ID': assignment.provider_id,
      'Provider Name': assignment.provider_name,
      'Shift Name': assignment.shift_name,
      'Date': assignment.date,
      'Day of Week': dayOfWeek,
      'Month': assignment.month
    };
  });

  exportToCSV(exportData, filename);
  showAlert('moonlightingAlert', 'Exported ' + exportData.length + ' assignments to ' + filename, 'success');
}

// Generate moonlighting schedule
async function generateMoonlightingSchedule() {
  const month = document.getElementById('generateMonth').value;

  if (!confirm('Run optimizer for ' + formatMonthYear(month) + '?\n\nThis will generate moonlighting assignments based on provider signups.')) {
    return;
  }

  try {
    showAlert('moonlightingAlert', 'Running optimizer... This may take a moment.', 'info');

    const response = await fetch('/api/admin/run_optimizer?month=' + month, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'}
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to generate schedule');
    }

    const result = await response.json();

    showAlert('moonlightingAlert',
      'Successfully generated ' + result.assignments_created + ' assignments for ' +
      formatMonthYear(month) + '!', 'success');

    // Switch to assignments tab and reload
    document.getElementById('assignmentsMonth').value = month;
    await loadAssignments();

  } catch (error) {
    console.error('Error generating schedule:', error);
    showAlert('moonlightingAlert', 'Failed to generate schedule: ' + error.message, 'error');
  }
}
