/**
 * Schedule Summary Report Module
 * Displays fill rates, request compliance, and holiday coverage.
 */

let summaryData = null;

// Auto-load on mount
document.addEventListener('DOMContentLoaded', function () {
  if (document.getElementById('summaryContent')) {
    loadSummary();
  }
});

async function loadSummary() {
  const year = (document.getElementById('summaryYear') || {}).value || 2026;

  document.getElementById('summaryLoading').style.display = 'block';
  document.getElementById('summaryContent').style.display = 'none';
  showSummaryAlert('', 'clear');

  try {
    const response = await fetch('/api/admin/schedule-summary?year=' + year, {
      credentials: 'same-origin'
    });

    if (!response.ok) throw new Error('Failed to load summary (HTTP ' + response.status + ')');

    summaryData = await response.json();

    if (summaryData.error) {
      throw new Error(summaryData.error);
    }

    renderSummary(summaryData);

    document.getElementById('summaryLoading').style.display = 'none';
    document.getElementById('summaryContent').style.display = 'block';

  } catch (error) {
    console.error('Error loading summary:', error);
    document.getElementById('summaryLoading').style.display = 'none';
    showSummaryAlert('Failed to load summary: ' + error.message, 'error');
  }
}

// ── Render ──────────────────────────────────────────────────────────────────

function renderSummary(data) {
  renderStatCards(data);
  renderFillRates(data.fill_rates || []);
  renderHolidayCoverage(data.holiday_coverage || {});
}

function renderStatCards(data) {
  // Overall fill
  const overallPct = data.overall_fill_pct != null ? data.overall_fill_pct + '%' : '—';
  document.getElementById('statOverallFillPct').textContent = overallPct;
  document.getElementById('statOverallFillDetail').textContent =
    (data.total_filled || 0) + ' / ' + (data.total_slots || 0) + ' slots filled';

  // Unavailability
  const ur = data.unavailability_requests || {};
  document.getElementById('statUnavailPct').textContent =
    ur.pct != null ? ur.pct + '%' : (ur.submitted === 0 ? 'N/A' : '—');
  document.getElementById('statUnavailDetail').textContent =
    (ur.honored || 0) + ' / ' + (ur.submitted || 0) + ' requests';

  // Volunteer
  const vr = data.volunteer_requests || {};
  document.getElementById('statVolunteerPct').textContent =
    vr.pct != null ? vr.pct + '%' : (vr.submitted === 0 ? 'N/A' : '—');
  document.getElementById('statVolunteerDetail').textContent =
    (vr.honored || 0) + ' / ' + (vr.submitted || 0) + ' requests';
}

function renderFillRates(fillRates) {
  const tbody = document.getElementById('fillRatesBody');
  tbody.innerHTML = '';

  let totalSlots = 0, totalFilled = 0, totalUnfilled = 0;

  fillRates.forEach(function (r) {
    totalSlots += r.slots || 0;
    totalFilled += r.filled || 0;
    totalUnfilled += r.unfilled || 0;

    const pct = r.pct || 0;
    const barColor = pct >= 90 ? '#10b981' : pct >= 70 ? '#f59e0b' : '#ef4444';

    const tr = document.createElement('tr');
    tr.innerHTML =
      '<td style="font-weight: 600;">' + r.service_type + '</td>' +
      '<td style="text-align: center;">' + r.required_per_week + '</td>' +
      '<td style="text-align: center;">' + r.slots + '</td>' +
      '<td style="text-align: center; color: #10b981; font-weight: 600;">' + r.filled + '</td>' +
      '<td style="text-align: center; color: ' + (r.unfilled > 0 ? '#ef4444' : '#6b7280') + ';">' + r.unfilled + '</td>' +
      '<td>' + buildFillBar(pct, barColor) + '</td>';
    tbody.appendChild(tr);
  });

  // Totals row
  const totalPct = totalSlots > 0 ? Math.round(totalFilled / totalSlots * 1000) / 10 : 0;
  const barColor = totalPct >= 90 ? '#10b981' : totalPct >= 70 ? '#f59e0b' : '#ef4444';
  const tr = document.createElement('tr');
  tr.innerHTML =
    '<td>Total</td>' +
    '<td></td>' +
    '<td style="text-align: center;">' + totalSlots + '</td>' +
    '<td style="text-align: center; color: #10b981;">' + totalFilled + '</td>' +
    '<td style="text-align: center; color: ' + (totalUnfilled > 0 ? '#ef4444' : '#6b7280') + ';">' + totalUnfilled + '</td>' +
    '<td>' + buildFillBar(totalPct, barColor) + '</td>';
  tbody.appendChild(tr);
}

function buildFillBar(pct, color) {
  const width = Math.min(100, Math.max(0, pct));
  return '<div class="fill-bar-container">' +
    '<div class="fill-bar-fill" style="width: ' + width + '%; background: ' + color + ';"></div>' +
    '<span class="fill-bar-label">' + pct + '%</span>' +
    '</div>';
}

function renderHolidayCoverage(coverage) {
  const container = document.getElementById('holidayCoverageContainer');
  container.innerHTML = '';

  const holidayLabels = {
    thanksgiving: '🦃 Thanksgiving',
    christmas: '🎄 Christmas / New Year',
    spring_break: '🌸 Spring Break'
  };

  const allKeys = Object.keys(coverage);
  if (allKeys.length === 0) {
    container.innerHTML = '<p style="color: #9ca3af; font-size: 14px;">No holiday weeks configured for this year.</p>';
    return;
  }

  allKeys.forEach(function (holidayType) {
    const weeks = coverage[holidayType] || [];
    const label = holidayLabels[holidayType] || ('🗓️ ' + holidayType.replace(/_/g, ' '));

    const card = document.createElement('div');
    card.className = 'holiday-card';

    let weeksHtml = '';
    if (weeks.length === 0) {
      weeksHtml = '<p style="color: #9ca3af; font-size: 13px;">No weeks found.</p>';
    } else {
      weeks.forEach(function (week) {
        const assignments = week.assignments || [];
        let assignmentLines = '';
        if (assignments.length === 0) {
          assignmentLines = '<span style="color: #ef4444;">⚠️ No assignments yet</span>';
        } else {
          // Group by service type
          const byService = {};
          assignments.forEach(function (a) {
            if (!byService[a.service_type]) byService[a.service_type] = [];
            byService[a.service_type].push(a.faculty_name);
          });
          assignmentLines = Object.entries(byService).map(function ([svc, names]) {
            return '<strong>' + svc + ':</strong> ' + names.join(', ');
          }).join('<br>');
        }

        weeksHtml +=
          '<div class="holiday-week-entry">' +
            '<div class="holiday-week-label">' + week.week_label + '</div>' +
            '<div class="holiday-assignment-list">' + assignmentLines + '</div>' +
          '</div>';
      });
    }

    card.innerHTML = '<h4>' + label + '</h4>' + weeksHtml;
    container.appendChild(card);
  });
}

// ── CSV Export ───────────────────────────────────────────────────────────────

function exportSummaryCSV() {
  if (!summaryData) {
    showSummaryAlert('No data loaded. Click Refresh first.', 'error');
    return;
  }

  const year = (document.getElementById('summaryYear') || {}).value || summaryData.year;
  const rows = [];

  // Header
  rows.push(['FacultyHub Schedule Summary', 'Academic Year: ' + year]);
  rows.push([]);

  // Overall stats
  rows.push(['Overall Fill Rate', (summaryData.overall_fill_pct || 0) + '%',
    (summaryData.total_filled || 0) + ' / ' + (summaryData.total_slots || 0) + ' slots']);

  const ur = summaryData.unavailability_requests || {};
  rows.push(['Unavailability Requests Honored',
    ur.pct != null ? ur.pct + '%' : 'N/A',
    (ur.honored || 0) + ' / ' + (ur.submitted || 0) + ' requests']);

  const vr = summaryData.volunteer_requests || {};
  rows.push(['Volunteer Requests Honored',
    vr.pct != null ? vr.pct + '%' : 'N/A',
    (vr.honored || 0) + ' / ' + (vr.submitted || 0) + ' requests']);

  rows.push([]);

  // Fill rates
  rows.push(['SERVICE FILL RATES']);
  rows.push(['Service Type', 'Required/Week', 'Total Slots', 'Filled', 'Unfilled', 'Fill %']);
  (summaryData.fill_rates || []).forEach(function (r) {
    rows.push([r.service_type, r.required_per_week, r.slots, r.filled, r.unfilled, r.pct + '%']);
  });

  rows.push([]);

  // Holiday coverage
  rows.push(['HOLIDAY COVERAGE']);
  rows.push(['Holiday', 'Week', 'Service', 'Faculty']);
  const coverage = summaryData.holiday_coverage || {};
  Object.entries(coverage).forEach(function ([holidayType, weeks]) {
    (weeks || []).forEach(function (week) {
      const assignments = week.assignments || [];
      if (assignments.length === 0) {
        rows.push([holidayType, week.week_label, '—', 'No assignments']);
      } else {
        assignments.forEach(function (a) {
          rows.push([holidayType, week.week_label, a.service_type, a.faculty_name]);
        });
      }
    });
  });

  // Build CSV string
  const csvContent = rows.map(function (row) {
    return row.map(function (cell) {
      const s = String(cell == null ? '' : cell);
      return s.includes(',') || s.includes('"') || s.includes('\n')
        ? '"' + s.replace(/"/g, '""') + '"'
        : s;
    }).join(',');
  }).join('\n');

  // Trigger download
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'schedule-summary-' + year + '.csv';
  link.click();
  URL.revokeObjectURL(url);
}

// ── Alert helper ─────────────────────────────────────────────────────────────

function showSummaryAlert(message, type) {
  const alert = document.getElementById('summaryAlert');
  if (!alert) return;
  if (type === 'clear') {
    alert.style.display = 'none';
    return;
  }
  alert.textContent = message;
  alert.className = 'alert alert-' + type;
  alert.style.display = 'block';
  if (type === 'success') {
    setTimeout(function () { showSummaryAlert('', 'clear'); }, 3000);
  }
}

// ── Exports ───────────────────────────────────────────────────────────────────
window.loadSummary = loadSummary;
window.exportSummaryCSV = exportSummaryCSV;
