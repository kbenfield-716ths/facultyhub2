/**
 * Schedule Management Module
 * Generate and configure 52-week service schedule
 */

let allWeeks = [];
let currentEditingWeekId = null;
let currentScheduleTab = 'overview';
let scheduleCurrentYear = 2026;

// Load heatmap on init
document.addEventListener('DOMContentLoaded', function() {
  if (document.getElementById('heatmapGrid')) {
    loadHeatmap(2026);
  }
});

// Show schedule sub-tab
function showScheduleTab(tabId) {
  // Update buttons
  document.querySelectorAll('.sub-tab-btn').forEach(function(btn) {
    btn.classList.remove('active');
  });
  event.target.classList.add('active');

  // Update content
  document.querySelectorAll('.sub-tab-content').forEach(function(content) {
    content.classList.remove('active');
  });
  document.getElementById('schedule-' + tabId).classList.add('active');

  currentScheduleTab = tabId;

  // Load data for tab
  if (tabId === 'overview') {
    loadHeatmap(scheduleCurrentYear);
  } else if (tabId === 'weeks') {
    loadWeeks();
  } else if (tabId === 'assignments') {
    loadAssignments();
  }
}

// Load heatmap
async function loadHeatmap(year) {
  scheduleCurrentYear = year;

  // Update button states
  document.getElementById('year2025Btn').classList.toggle('active', year === 2025);
  document.getElementById('year2026Btn').classList.toggle('active', year === 2026);
  document.getElementById('year2025Btn').style.background = year === 2025 ? '#667eea' : 'white';
  document.getElementById('year2025Btn').style.color = year === 2025 ? 'white' : '#6b7280';
  document.getElementById('year2025Btn').style.borderColor = year === 2025 ? '#667eea' : '#e5e7eb';
  document.getElementById('year2026Btn').style.background = year === 2026 ? '#667eea' : 'white';
  document.getElementById('year2026Btn').style.color = year === 2026 ? 'white' : '#6b7280';
  document.getElementById('year2026Btn').style.borderColor = year === 2026 ? '#667eea' : '#e5e7eb';

  const loading = document.getElementById('heatmapLoading');
  const grid = document.getElementById('heatmapGrid');

  loading.style.display = 'block';
  grid.style.display = 'none';

  try {
    showAlert('scheduleAlert', '', 'clear');

    const response = await fetch('/api/admin/service-weeks/heatmap?year=' + year, { credentials: 'same-origin' });
    if (!response.ok) throw new Error('Failed to load heatmap data');
    const weeks = await response.json();

    if (weeks.length === 0) {
      grid.innerHTML = '<p style="color: #6b7280; text-align: center; padding: 40px;">No weeks found for this year. Generate weeks in "Generate Schedule" tab.</p>';
    } else {
      grid.innerHTML = weeks.map(function(week) {
        const count = week.unavailable_count || 0;
        let statusClass = 'status-good';
        let statusText = 'Good';
        if (week.staffing_status === 'critical' || count >= 12) {
          statusClass = 'status-critical';
          statusText = 'Critical';
        } else if (week.staffing_status === 'tight' || count >= 8) {
          statusClass = 'status-tight';
          statusText = 'Tight';
        }

        return '<div class="week-cell ' + statusClass + '">' +
          '<div class="week-num">Week ' + week.week_number + '</div>' +
          '<div class="week-label">' + week.label + '</div>' +
          '<div class="week-count">' + count + '</div>' +
          '<div class="week-status">' + statusText + '</div>' +
        '</div>';
      }).join('');
    }

    loading.style.display = 'none';
    grid.style.display = 'grid';
  } catch (error) {
    console.error('Error loading heatmap:', error);
    showAlert('scheduleAlert', 'Failed to load heatmap: ' + error.message, 'error');
    loading.textContent = 'Error: ' + error.message;
  }
}

// Generate schedule
async function generateSchedule(event) {
  event.preventDefault();

  const year = document.getElementById('configYear').value;
  const startDate = document.getElementById('configStartDate').value;

  if (!startDate) {
    showAlert('scheduleAlert', 'Please provide a start date', 'error');
    return;
  }

  const config = {
    year: parseInt(year),
    start_date: startDate,
    summer_start: document.getElementById('summerStart').value || null,
    summer_end: document.getElementById('summerEnd').value || null,
    spring_break: document.getElementById('springBreak').value || null,
    thanksgiving: document.getElementById('thanksgiving').value || null,
    christmas: document.getElementById('christmas').value || null,
    ats_conference: document.getElementById('atsConference').value || null,
    chest_conference: document.getElementById('chestConference').value || null,
    sccm_conference: document.getElementById('sccmConference').value || null
  };

  if (!confirm('Generate 52 weeks for ' + year + '-' + (parseInt(year) + 1) + '?\n\nThis will create the full academic year schedule with special periods configured.')) {
    return;
  }

  try {
    const response = await fetch('/api/admin/generate-service-weeks', {
      credentials: 'same-origin',
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(config)
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to generate schedule');
    }

    const result = await response.json();
    showAlert('scheduleAlert', 'Successfully generated ' + result.weeks_created + ' weeks!', 'success');

    // Switch to overview tab
    document.querySelector('.sub-tab-btn').click();

  } catch (error) {
    console.error('Error generating schedule:', error);
    showAlert('scheduleAlert', 'Failed to generate schedule: ' + error.message, 'error');
  }
}

// Clear all weeks
async function clearAllWeeks() {
  const year = document.getElementById('configYear').value;

  const confirmMessage = '⚠️ CLEAR ALL WEEKS FOR ' + year + '-' + (parseInt(year) + 1) + '?\n\n' +
                        'This will permanently delete:\n' +
                        '- All 52 weeks for this year\n' +
                        '- All unavailability requests for these weeks\n' +
                        '- All draft progress for this year\n' +
                        '- All generated assignments\n\n' +
                        'This action cannot be undone. Continue?';

  if (!confirm(confirmMessage)) {
    return;
  }

  try {
    const response = await fetch('/api/admin/service-weeks?year=' + year, {
      method: 'DELETE'
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to clear weeks');
    }

    const result = await response.json();
    showAlert('scheduleAlert', 'Cleared ' + result.weeks_deleted + ' weeks', 'success');

  } catch (error) {
    console.error('Error clearing weeks:', error);
    showAlert('scheduleAlert', 'Failed to clear weeks: ' + error.message, 'error');
  }
}

// Load weeks for editing
async function loadWeeks() {
  const year = document.getElementById('weeksYearSelect').value;

  document.getElementById('weeksLoading').style.display = 'block';
  document.getElementById('weeksContent').style.display = 'none';

  try {
    showAlert('scheduleAlert', '', 'clear');

    const response = await fetch('/api/admin/service-weeks?year=' + year);
    if (!response.ok) throw new Error('Failed to load weeks');

    const data = await response.json();
    if (Array.isArray(data)) {
      allWeeks = data;
    } else {
      allWeeks = data.weeks || [];
    }

    renderWeeksTable();

    document.getElementById('weeksLoading').style.display = 'none';
    document.getElementById('weeksContent').style.display = 'block';

  } catch (error) {
    console.error('Error loading weeks:', error);
    showAlert('scheduleAlert', 'Failed to load weeks: ' + error.message, 'error');
    document.getElementById('weeksLoading').style.display = 'none';
  }
}

// Render weeks table
function renderWeeksTable() {
  const tbody = document.getElementById('weeksTableBody');

  if (allWeeks.length === 0) {
    tbody.innerHTML = '<tr><td colspan="8" class="empty-state">' +
      '<div class="empty-state-icon">📅</div>' +
      '<div class="empty-state-title">No Weeks Found</div>' +
      '<div class="empty-state-description">Generate a schedule first</div>' +
      '</td></tr>';
    return;
  }

  tbody.innerHTML = '';

  allWeeks.forEach(function(week) {
    const row = document.createElement('tr');

    row.innerHTML = '<td style="font-weight: 600;">' + (week.week_number || '-') + '</td>' +
                    '<td>' + (week.label || 'Week ' + week.week_number) + '</td>' +
                    '<td>' + formatDate(week.start_date) + '</td>' +
                    '<td>' + formatDate(week.end_date) + '</td>' +
                    '<td><span class="badge">' + (week.week_type || 'regular') + '</span></td>' +
                    '<td style="text-align: center; font-weight: 600;">' + (week.point_cost_off || 1) + '</td>' +
                    '<td style="text-align: center; font-weight: 600;">' + (week.point_reward_work || 0) + '</td>' +
                    '<td><button class="btn-primary btn-sm" onclick="openEditWeek(\'' + week.id + '\')">Edit</button></td>';

    tbody.appendChild(row);
  });
}

// Open edit week modal
function openEditWeek(weekId) {
  const week = allWeeks.find(function(w) { return w.id === weekId; });
  if (!week) return;

  currentEditingWeekId = weekId;

  document.getElementById('editWeekId').value = week.id;
  document.getElementById('editWeekLabel').value = week.label || '';
  document.getElementById('editWeekType').value = week.week_type || 'regular';
  document.getElementById('editWeekCost').value = week.point_cost_off || 1;
  document.getElementById('editWeekReward').value = week.point_reward_work || 0;

  document.getElementById('editWeekModal').classList.add('show');
}

// Close edit week modal
function closeEditWeekModal() {
  document.getElementById('editWeekModal').classList.remove('show');
  currentEditingWeekId = null;
}

// Submit edit week
async function submitEditWeek(event) {
  event.preventDefault();

  if (!currentEditingWeekId) return;

  const payload = {
    label: document.getElementById('editWeekLabel').value.trim(),
    week_type: document.getElementById('editWeekType').value,
    point_cost_off: parseFloat(document.getElementById('editWeekCost').value) || 1,
    point_reward_work: parseFloat(document.getElementById('editWeekReward').value) || 0
  };

  try {
    const response = await fetch('/api/admin/service-weeks/' + currentEditingWeekId, {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to update week');
    }

    showAlert('scheduleAlert', 'Week updated successfully', 'success');
    closeEditWeekModal();
    await loadWeeks();

  } catch (error) {
    console.error('Error updating week:', error);
    alert('Failed to update week: ' + error.message);
  }
}

// ==================== GLOBAL FUNCTION EXPORTS ====================
// Make functions globally accessible for inline onclick handlers

window.showScheduleTab = showScheduleTab;
window.loadHeatmap = loadHeatmap;
window.clearAllWeeks = clearAllWeeks;
window.loadWeeks = loadWeeks;
window.openEditWeek = openEditWeek;
window.closeEditWeekModal = closeEditWeekModal;
window.cleanupUnavailabilityViolations = cleanupUnavailabilityViolations;

// ==================== MODAL CLOSE FUNCTIONALITY ====================

// Close modal when clicking outside (on backdrop)
document.addEventListener('DOMContentLoaded', function() {
  const modal = document.getElementById('editWeekModal');
  if (modal) {
    modal.addEventListener('click', function(event) {
      // Only close if clicking directly on the modal backdrop, not the content
      if (event.target === modal) {
        closeEditWeekModal();
      }
    });
  }

  // Also attach listeners to close button and cancel button
  const closeBtn = modal?.querySelector('.close-btn');
  const cancelBtn = modal?.querySelector('button[type="button"].btn-secondary');

  if (closeBtn) {
    closeBtn.addEventListener('click', function(e) {
      e.preventDefault();
      e.stopPropagation();
      closeEditWeekModal();
    });
  }

  if (cancelBtn) {
    cancelBtn.addEventListener('click', function(e) {
      e.preventDefault();
      e.stopPropagation();
      closeEditWeekModal();
    });
  }
});

// Close modal when pressing ESC key
document.addEventListener('keydown', function(event) {
  if (event.key === 'Escape') {
    const modal = document.getElementById('editWeekModal');
    if (modal && modal.classList.contains('show')) {
      closeEditWeekModal();
    }
  }
});


// ============================================================
// ASSIGNMENTS TAB — Faculty Service Schedule
// ============================================================

/**
 * Load and display current faculty assignments from the DB.
 */
async function loadAssignments() {
  const year = parseInt(document.getElementById('assignmentsYearSelect').value);

  // Show loading, hide everything else
  document.getElementById('assignmentsLoading').style.display = 'block';
  document.getElementById('assignmentsContent').style.display = 'none';
  document.getElementById('assignmentsEmpty').style.display = 'none';
  document.getElementById('assignmentStats').style.display = 'none';
  document.getElementById('generateResultPanel').style.display = 'none';

  try {
    const resp = await fetch('/api/admin/service-schedule?year=' + year, { credentials: 'same-origin' });
    if (!resp.ok) throw new Error('Failed to load schedule');
    const data = await resp.json();

    document.getElementById('assignmentsLoading').style.display = 'none';

    if (!data.success || data.total_assignments === 0) {
      document.getElementById('assignmentsEmpty').style.display = 'block';
      return;
    }

    // Populate stats
    const incomplete = data.total_weeks - data.complete_weeks;
    document.getElementById('statTotalWeeks').textContent = data.total_weeks;
    document.getElementById('statCompleteWeeks').textContent = data.complete_weeks;
    document.getElementById('statTotalAssignments').textContent = data.total_assignments;
    document.getElementById('statIncomplete').textContent = incomplete;
    document.getElementById('statIncomplete').style.color = incomplete > 0 ? '#ef4444' : '#10b981';
    document.getElementById('assignmentStats').style.display = 'block';

    // Render table
    renderAssignmentTable(data.schedule);
    document.getElementById('assignmentsContent').style.display = 'block';

  } catch (err) {
    document.getElementById('assignmentsLoading').style.display = 'none';
    document.getElementById('assignmentsEmpty').style.display = 'block';
    console.error('Error loading assignments:', err);
  }
}

/**
 * Render the week-by-week assignment table.
 */
function renderAssignmentTable(schedule) {
  const tbody = document.getElementById('assignmentsTableBody');

  tbody.innerHTML = schedule.map(function(week) {
    const complete = week.is_complete;
    const rowClass = complete ? 'week-complete' : 'week-understaffed';

    const startDate = new Date(week.start_date + 'T00:00:00');
    const endDate = new Date(week.end_date + 'T00:00:00');
    const dateStr = formatShortDate(startDate) + ' – ' + formatShortDate(endDate);

    function chipsHtml(list) {
      if (!list || list.length === 0) return '<span style="color:#ef4444; font-size:12px;">⚠ Unassigned</span>';
      return list.map(function(f) {
        return '<span class="faculty-chip">' + escapeHtml(f.faculty_name) + '</span>';
      }).join('');
    }

    const statusBadge = complete
      ? '<span class="status-badge ok">✓ Full</span>'
      : '<span class="status-badge warn">⚠ Short</span>';

    return '<tr class="' + rowClass + '">' +
      '<td style="font-weight:600; color:#6b7280;">' + week.week_number + '</td>' +
      '<td style="font-size:12px; color:#374151;">' + dateStr + '</td>' +
      '<td>' + chipsHtml(week.assignments.MICU) + '</td>' +
      '<td>' + chipsHtml(week.assignments['APP-ICU']) + '</td>' +
      '<td>' + chipsHtml(week.assignments.Procedures) + '</td>' +
      '<td>' + chipsHtml(week.assignments.Consults) + '</td>' +
      '<td>' + chipsHtml(week.assignments.Backup) + '</td>' +
      '<td style="text-align:center;">' + statusBadge + '</td>' +
      '</tr>';
  }).join('');
}

/**
 * Show a confirmation dialog before generating assignments.
 */
function confirmGenerateAssignments() {
  const year = parseInt(document.getElementById('assignmentsYearSelect').value);
  const yearLabel = year + '–' + (year + 1);

  if (!confirm(
    'Generate faculty assignments for ' + yearLabel + '?\n\n' +
    'This will:\n' +
    '  • Clear any existing auto-generated assignments\n' +
    '  • Assign faculty to MICU, APP-ICU, Procedures, and Consults\n' +
    '  • Respect all unavailability requests\n' +
    '  • Enforce no back-to-back week constraints\n\n' +
    'Manual overrides will be preserved. Continue?'
  )) return;

  runGenerateAssignments(year, true);
}

/**
 * Show a confirmation dialog before clearing assignments.
 */
async function confirmClearAutoOnly() {
  const year = parseInt(document.getElementById('assignmentsYearSelect').value);
  const yearLabel = year + '–' + (year + 1);

  if (!confirm(
    'Clear ONLY auto-generated assignments for ' + yearLabel + '?\n\n' +
    'Manual assignments and imported CSV assignments will be preserved.\n\n' +
    'Use this to see a clean baseline before re-running the generator.'
  )) return;

  try {
    const resp = await fetch('/api/admin/service-schedule/auto-only?year=' + year, {
      method: 'DELETE',
      credentials: 'same-origin'
    });
    const data = await resp.json();
    if (data.success) {
      showScheduleAlert('🧼 Cleared ' + data.assignments_deleted + ' auto-generated assignment(s). Manual and imported assignments preserved.', 'success');
      await loadAssignments();
    } else {
      showScheduleAlert('Failed to clear auto-generated assignments.', 'error');
    }
  } catch (err) {
    showScheduleAlert('Error: ' + err.message, 'error');
  }
}
window.confirmClearAutoOnly = confirmClearAutoOnly;

function confirmClearAssignments() {
  const year = parseInt(document.getElementById('assignmentsYearSelect').value);
  const yearLabel = year + '–' + (year + 1);

  if (!confirm(
    'Clear ALL assignments for ' + yearLabel + ' and rebuild from scratch?\n\n' +
    'This cannot be undone. Continue?'
  )) return;

  runGenerateAssignments(year, true);
}

/**
 * Call the backend to generate the schedule.
 */
async function runGenerateAssignments(year, clearExisting) {
  // Disable all action buttons during run
  const buttons = document.querySelectorAll('#schedule-assignments button');
  buttons.forEach(function(b) { b.disabled = true; });

  document.getElementById('assignmentsLoading').style.display = 'block';
  document.getElementById('assignmentsContent').style.display = 'none';
  document.getElementById('assignmentsEmpty').style.display = 'none';
  document.getElementById('assignmentStats').style.display = 'none';
  document.getElementById('generateResultPanel').style.display = 'none';

  try {
    const resp = await fetch('/api/admin/generate-service-schedule', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ year: year, clear_existing: clearExisting })
    });

    const result = await resp.json();
    document.getElementById('assignmentsLoading').style.display = 'none';

    if (!resp.ok || !result.success) {
      document.getElementById('generateResultPanel').innerHTML =
        '<div class="issue-panel error"><h4>❌ Generation Failed</h4><p>' +
        escapeHtml(result.error || result.detail || 'Unknown error') + '</p></div>';
      document.getElementById('generateResultPanel').style.display = 'block';
      return;
    }

    // Render result summary
    renderGenerateResult(result);

    // Reload the assignment table
    await loadAssignments();

  } catch (err) {
    document.getElementById('assignmentsLoading').style.display = 'none';
    document.getElementById('generateResultPanel').innerHTML =
      '<div class="issue-panel error"><h4>❌ Network Error</h4><p>' + escapeHtml(err.message) + '</p></div>';
    document.getElementById('generateResultPanel').style.display = 'block';
    console.error('Error generating assignments:', err);
  } finally {
    buttons.forEach(function(b) { b.disabled = false; });
  }
}

/**
 * Render the result panel after generation.
 */
function renderGenerateResult(result) {
  let html = '';

  // Success summary
  html += '<div class="issue-panel success">' +
    '<h4>✅ Schedule Generated — ' + result.assignments_created + ' assignments across ' + result.total_weeks + ' weeks</h4>' +
    '<ul>' +
    '<li>MICU: ' + result.summary.MICU + ' assignments</li>' +
    '<li>APP-ICU: ' + result.summary['APP-ICU'] + ' assignments</li>' +
    '<li>Procedures: ' + result.summary.Procedures + ' assignments</li>' +
    '<li>Consults: ' + result.summary.Consults + ' assignments</li>' +
    '<li>Backup: ' + (result.summary.Backup || 0) + ' assignments</li>' +
    '<li>Back-to-back conflicts prevented: ' + result.back_to_back_prevented + '</li>' +
    '</ul></div>';

  // Staffing issues (understaffed weeks)
  if (result.staffing_issues && result.staffing_issues.length > 0) {
    html += '<div class="issue-panel error">' +
      '<h4>⚠️ Understaffed Weeks (' + result.staffing_issues.length + ')</h4>' +
      '<ul>' +
      result.staffing_issues.map(function(issue) {
        return '<li>Week ' + issue.week + ' (' + escapeHtml(issue.week_label) + ') — ' +
          escapeHtml(issue.service) + ': ' + issue.assigned + '/' + issue.required + ' filled</li>';
      }).join('') +
      '</ul></div>';
  }

  // Capacity issues (faculty significantly over/under target)
  if (result.capacity_issues && result.capacity_issues.length > 0) {
    html += '<div class="issue-panel warning">' +
      '<h4>📊 Capacity Variances (' + result.capacity_issues.length + ')</h4>' +
      '<ul>' +
      result.capacity_issues.map(function(issue) {
        const sign = issue.variance > 0 ? '+' : '';
        return '<li>' + escapeHtml(issue.faculty_name) + ' — ' + escapeHtml(issue.service) + ': ' +
          issue.assigned + ' assigned vs ' + issue.target + ' target (' + sign + issue.variance + ')</li>';
      }).join('') +
      '</ul></div>';
  }

  document.getElementById('generateResultPanel').innerHTML = html;
  document.getElementById('generateResultPanel').style.display = 'block';
}

/**
 * Format a date as "Jul 7" style.
 */
function formatShortDate(date) {
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

/**
 * Escape HTML for safe rendering.
 */
function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/**
 * Download the full schedule as a CSV file directly from the server.
 */
function exportScheduleCSV() {
  const year = parseInt(document.getElementById('assignmentsYearSelect').value);
  // Let the browser handle the download via a plain link — the server returns
  // Content-Disposition: attachment so the browser saves it automatically.
  const a = document.createElement('a');
  a.href = '/api/admin/service-schedule/export?year=' + year;
  a.download = 'schedule-' + year + '-' + (year + 1) + '.csv';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

function exportScheduleInputs() {
  const year = parseInt(document.getElementById('assignmentsYearSelect').value);
  // Downloads a ZIP containing unavailability CSV + volunteer CSV
  const a = document.createElement('a');
  a.href = '/api/admin/service-schedule/export-inputs?year=' + year;
  a.download = 'schedule-inputs-' + year + '-' + (year + 1) + '.zip';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}
window.exportScheduleInputs = exportScheduleInputs;

/**
 * Find and remove auto-generated assignments that violate a FacultyBlock.
 * Shows a dry-run preview first, then asks the user to confirm removal.
 */
async function cleanupBlockViolations() {
  const year = parseInt(document.getElementById('assignmentsYearSelect').value);

  try {
    // Dry-run first to get the list
    const dryResp = await fetch(
      '/api/admin/service-schedule/cleanup-blocks?year=' + year + '&dry_run=true',
      { method: 'POST', credentials: 'same-origin' }
    );
    if (!dryResp.ok) throw new Error('Dry-run failed');
    const dryData = await dryResp.json();

    if (dryData.removed === 0) {
      showScheduleAlert('✅ No block violations found — schedule is clean.', 'success');
      return;
    }

    // Build a readable list for the confirm dialog
    const lines = dryData.violations.map(function(v) {
      return '  • ' + v.faculty_name + ' → ' + v.week_label + ' (' + v.service_type + ')';
    });
    const msg =
      dryData.removed + ' assignment(s) violate FacultyBlocks and should be removed:\n\n' +
      lines.join('\n') +
      '\n\nRemove these now?';

    if (!confirm(msg)) return;

    // Actually delete
    const resp = await fetch(
      '/api/admin/service-schedule/cleanup-blocks?year=' + year + '&dry_run=false',
      { method: 'POST', credentials: 'same-origin' }
    );
    if (!resp.ok) throw new Error('Cleanup failed');
    const data = await resp.json();

    showScheduleAlert(
      '🧹 Removed ' + data.removed + ' block-violating assignment(s). Reloading...',
      'success'
    );
    await loadAssignments();

  } catch (err) {
    console.error('Block cleanup error:', err);
    showScheduleAlert('Error during block cleanup: ' + err.message, 'error');
  }
}

/**
 * Find and remove auto-generated assignments that violate an unavailability
 * request.  Unavailability is a HARD STOP — 100% must be honored.
 * Shows a dry-run preview first, then asks the user to confirm removal.
 * Manual and imported assignments are NOT removed (admin is responsible).
 */
async function cleanupUnavailabilityViolations() {
  const year = parseInt(document.getElementById('assignmentsYearSelect').value);

  try {
    // Dry-run first to preview
    const dryResp = await fetch(
      '/api/admin/service-schedule/cleanup-unavailability?year=' + year + '&dry_run=true',
      { method: 'POST', credentials: 'same-origin' }
    );
    if (!dryResp.ok) throw new Error('Dry-run failed');
    const dryData = await dryResp.json();

    if (dryData.removed === 0) {
      let msg = '✅ No auto-generated unavailability violations found.';
      if (dryData.manual_imported_violations > 0) {
        msg += '\n\n⚠️ Note: ' + dryData.manual_imported_violations +
          ' manual/imported assignment(s) still conflict with unavailability requests — ' +
          'review those in the Overrides panel.';
        alert(msg);
      } else {
        showScheduleAlert(msg, 'success');
      }
      return;
    }

    // Build readable list
    const lines = dryData.violations.map(function(v) {
      return '  • ' + v.faculty_name + ' → ' + v.week_label + ' (' + v.service_type + ')';
    });
    let msg =
      dryData.removed + ' auto-generated assignment(s) violate unavailability requests:\n\n' +
      lines.join('\n') +
      '\n\nRemove these now?';
    if (dryData.manual_imported_violations > 0) {
      msg += '\n\n⚠️ Note: ' + dryData.manual_imported_violations +
        ' manual/imported conflict(s) will remain — handle those manually.';
    }

    if (!confirm(msg)) return;

    // Actually delete
    const resp = await fetch(
      '/api/admin/service-schedule/cleanup-unavailability?year=' + year + '&dry_run=false',
      { method: 'POST', credentials: 'same-origin' }
    );
    if (!resp.ok) throw new Error('Cleanup failed');
    const data = await resp.json();

    let successMsg = '🚫 Removed ' + data.removed + ' unavailability-violating assignment(s). Reloading...';
    if (data.manual_imported_violations > 0) {
      successMsg += ' (' + data.manual_imported_violations + ' manual/imported conflict(s) remain — check Overrides.)';
    }
    showScheduleAlert(successMsg, 'success');
    await loadAssignments();

  } catch (err) {
    console.error('Unavailability cleanup error:', err);
    showScheduleAlert('Error during unavailability cleanup: ' + err.message, 'error');
  }
}

/**
 * Show an alert on the schedule page.
 */
function showScheduleAlert(message, type) {
  const el = document.getElementById('scheduleAlert');
  if (!el) return;
  el.textContent = message;
  el.className = 'alert alert-' + type;
  el.style.display = 'block';
  if (type === 'success') {
    setTimeout(function() { el.style.display = 'none'; }, 4000);
  }
}
