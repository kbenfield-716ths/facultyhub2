/**
 * Schedule Management Module
 * Generate and configure 52-week service schedule
 */

let allWeeks = [];
let currentEditingWeekId = null;
let currentScheduleTab = 'overview';

// Load overview on init
document.addEventListener('DOMContentLoaded', function() {
  if (document.getElementById('overviewContent')) {
    loadOverview();
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
    loadOverview();
  } else if (tabId === 'weeks') {
    loadWeeks();
  }
}

// Load schedule overview
async function loadOverview() {
  const year = document.getElementById('overviewYearSelect').value;

  try {
    showAlert('scheduleAlert', '', 'clear');

    const response = await fetch('/api/admin/service-weeks?year=' + year);
    if (!response.ok) throw new Error('Failed to load overview');

    const rawData = await response.json();

    // Transform to overview format
    const data = {
      weeks: rawData.weeks || [],
      total_weeks: (rawData.weeks || []).length,
      avg_unavailable: 0, // Calculate from weeks if needed
      max_unavailable: 0  // Calculate from weeks if needed
    };

    if (!data.weeks || data.weeks.length === 0) {
      document.getElementById('overviewContent').innerHTML = '<p class="empty-state">' +
        '<div class="empty-state-icon">📅</div>' +
        '<div class="empty-state-title">No Schedule Generated</div>' +
        '<div class="empty-state-description">Use "Generate Schedule" tab to create a 52-week schedule for ' + year + '-' + (parseInt(year) + 1) + '</div>' +
        '</p>';
      return;
    }

    renderOverview(data);

  } catch (error) {
    console.error('Error loading overview:', error);
    showAlert('scheduleAlert', 'Failed to load overview: ' + error.message, 'error');
  }
}

// Render overview
function renderOverview(data) {
  const html = '<div style="margin-bottom: 20px;">' +
    '<div class="stats-row">' +
      '<div class="stat-card">' +
        '<div class="stat-label">Total Weeks</div>' +
        '<div class="stat-value">' + (data.total_weeks || 0) + '</div>' +
      '</div>' +
      '<div class="stat-card">' +
        '<div class="stat-label">Avg Unavailable</div>' +
        '<div class="stat-value">' + (data.avg_unavailable || 0) + '</div>' +
      '</div>' +
      '<div class="stat-card">' +
        '<div class="stat-label">Max Unavailable</div>' +
        '<div class="stat-value">' + (data.max_unavailable || 0) + '</div>' +
      '</div>' +
    '</div>' +
  '</div>' +
  '<h3 style="margin-bottom: 16px; color: #1f2937;">Week-by-Week Status</h3>' +
  '<div class="heatmap-grid">' +
    data.weeks.map(function(week) {
      const unavailCount = week.unavailable_count || 0;
      let statusClass = 'status-good';
      let statusText = 'Good';

      if (unavailCount >= 8) {
        statusClass = 'status-critical';
        statusText = 'Critical';
      } else if (unavailCount >= 5) {
        statusClass = 'status-tight';
        statusText = 'Tight';
      }

      return '<div class="week-cell ' + statusClass + '">' +
        '<div class="week-num">Week ' + week.week_number + '</div>' +
        '<div class="week-label">' + week.label + '</div>' +
        '<div class="week-count">' + unavailCount + '</div>' +
        '<div class="week-status">' + statusText + '</div>' +
      '</div>';
    }).join('') +
  '</div>';

  document.getElementById('overviewContent').innerHTML = html;
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
                    '<td style="text-align: center; font-weight: 600;">' + (week.cost_off || 1) + '</td>' +
                    '<td style="text-align: center; font-weight: 600;">' + (week.reward_work || 0) + '</td>' +
                    '<td><button class="btn-primary btn-sm" onclick="openEditWeek(' + week.id + ')">Edit</button></td>';

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
  document.getElementById('editWeekCost').value = week.cost_off || 1;
  document.getElementById('editWeekReward').value = week.reward_work || 0;

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
    cost_off: parseFloat(document.getElementById('editWeekCost').value) || 1,
    reward_work: parseFloat(document.getElementById('editWeekReward').value) || 0
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
