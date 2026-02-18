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
