/**
 * Faculty Management Module
 * CRUD operations for faculty members
 */

let allFaculty = [];
let currentEditingId = null;

// Load all faculty on module init
document.addEventListener('DOMContentLoaded', function() {
  if (document.getElementById('facultyTableBody')) {
    loadFaculty();
  }
});

// Base points calculation: effort% × rank multiplier
// Assistant=1, Associate=1.75, Full=2.5
function computeBasePoints(effortPct, rank) {
  const multipliers = { 'Assistant': 1, 'Associate': 1.75, 'Full': 2.5 };
  const m = multipliers[rank];
  if (!m || !effortPct) return '';
  return Math.round(effortPct * m);
}

function calcNewBasePoints() {
  const effort = parseFloat(document.getElementById('newFacultyEffort').value);
  const rank = document.getElementById('newFacultyRank').value;
  const result = computeBasePoints(effort, rank);
  if (result !== '') document.getElementById('newFacultyBasePoints').value = result;
}

function calcEditBasePoints() {
  const effort = parseFloat(document.getElementById('editFacultyEffort').value);
  const rank = document.getElementById('editFacultyRank').value;
  const result = computeBasePoints(effort, rank);
  if (result !== '') document.getElementById('editFacultyBasePoints').value = result;
}

// Load faculty list
async function loadFaculty() {
  try {
    showAlert('facultyAlert', '', 'clear');

    const response = await fetch('/api/admin/faculty', { credentials: 'same-origin' });
    if (!response.ok) throw new Error('Failed to load faculty');

    const data = await response.json();
    allFaculty = Array.isArray(data) ? data : (data.faculty || []); 

    renderFacultyTable();
    updateFacultyCount();

  } catch (error) {
    console.error('Error loading faculty:', error);
    showAlert('facultyAlert', 'Failed to load faculty: ' + error.message, 'error');
  }
}

// Render faculty table
function renderFacultyTable() {
  const tbody = document.getElementById('facultyTableBody');

  if (allFaculty.length === 0) {
    tbody.innerHTML = '<tr><td colspan="14" class="empty-state"><div class="empty-state-icon">👥</div><div class="empty-state-title">No Faculty Members</div><div class="empty-state-description">Add your first faculty member using the form above</div></td></tr>';
    return;
  }

  tbody.innerHTML = '';

  allFaculty.forEach(function(faculty) {
    const row = document.createElement('tr');

    // Compute actual assignments from service_weeks
    const micuActual = (faculty.service_weeks && faculty.service_weeks.MICU) || 0;
    const appIcuActual = (faculty.service_weeks && faculty.service_weeks.APP_ICU) || 0;
    const proceduresActual = (faculty.service_weeks && faculty.service_weeks.Procedures) || 0;
    const consultsActual = (faculty.service_weeks && faculty.service_weeks.Consults) || 0;
    const backupActual = (faculty.service_weeks && faculty.service_weeks.Backup) || 0;
    const totalActual = micuActual + appIcuActual + proceduresActual + consultsActual + backupActual;

    // Get expected targets
    const micuTarget = faculty.micu_weeks || 0;
    const appIcuTarget = faculty.app_icu_weeks || 0;
    const proceduresTarget = faculty.procedure_weeks || 0;
    const consultsTarget = faculty.consult_weeks || 0;
    const backupTarget = faculty.backup_weeks || 0;
    const totalTarget = micuTarget + appIcuTarget + proceduresTarget + consultsTarget + backupTarget;

    // Helper function to format actual/target with color coding
    function formatActualTarget(actual, target) {
      if (target === 0) return actual; // No target set, just show actual
      const diff = actual - target;
      let color = '#6b7280'; // default gray
      if (diff > 0) color = '#10b981'; // green if over
      if (diff < 0) color = '#ef4444'; // red if under
      return '<span style="color: ' + color + '; font-weight: 600;">' + actual + '</span> / ' + target;
    }

    // Status badge
    const statusBadge = faculty.active
      ? '<span class="badge badge-success">Active</span>'
      : '<span class="badge badge-danger">Inactive</span>';

    // Admin badge
    const adminBadge = faculty.is_admin
      ? ' <span class="badge badge-info">Admin</span>'
      : '';

    // Moonlighter badge (with priority indicator for moonlighters)
    let moonlighterBadge = '';
    if (faculty.moonlighter) {
      const prio = faculty.moonlighting_priority || 2;
      const prioLabel = prio === 1 ? ' ⭐High' : (prio === 3 ? ' Low' : '');
      moonlighterBadge = ' <span class="badge badge-warning" title="Moonlighting priority: ' +
        (prio === 1 ? 'High' : prio === 3 ? 'Low' : 'Medium') + '">🌙 Moonlighter' + prioLabel + '</span>';
    }

    row.innerHTML = '<td style="font-weight: 600;">' + (faculty.id || '') + '</td>' +
                    '<td>' + (faculty.name || '') + adminBadge + moonlighterBadge + '</td>' +
                    '<td style="font-size: 13px;">' + (faculty.email || '-') + '</td>' +
                    '<td>' + (faculty.rank || '-') + '</td>' +
                    '<td style="text-align: center;">' + (faculty.clinical_effort_pct || 0) + '%</td>' +
                    '<td style="text-align: center; font-weight: 600;">' + (faculty.base_points || 0) + '</td>' +
                    '<td style="text-align: center;">' + formatActualTarget(micuActual, micuTarget) + '</td>' +
                    '<td style="text-align: center;">' + formatActualTarget(appIcuActual, appIcuTarget) + '</td>' +
                    '<td style="text-align: center;">' + formatActualTarget(proceduresActual, proceduresTarget) + '</td>' +
                    '<td style="text-align: center;">' + formatActualTarget(consultsActual, consultsTarget) + '</td>' +
                    '<td style="text-align: center;">' + formatActualTarget(backupActual, backupTarget) + '</td>' +
                    '<td style="text-align: center; font-weight: 700;">' + formatActualTarget(totalActual, totalTarget) + '</td>' +
                    '<td>' + statusBadge + '</td>' +
                    '<td><div class="action-buttons" style="display: flex; gap: 8px; flex-wrap: wrap;">' +
                      '<button class="btn-primary btn-sm" style="min-width: 90px;" onclick="openEditFaculty(\'' + faculty.id + '\')">Edit</button>' +
                      (faculty.active
                        ? '<button class="btn-sm" style="min-width: 90px; background: #f59e0b; color: white; border: 1px solid #f59e0b;" onclick="toggleFacultyStatus(\'' + faculty.id + '\', false)">Deactivate</button>'
                        : '<button class="btn-success btn-sm" style="min-width: 90px;" onclick="toggleFacultyStatus(\'' + faculty.id + '\', true)">Activate</button>') +
                      (faculty.is_admin
                        ? '<button class="btn-sm" style="min-width: 90px; background: #8b5cf6; color: white; border: 1px solid #8b5cf6;" onclick="toggleAdmin(\'' + faculty.id + '\')" title="Remove admin">🔓 Unadmin</button>'
                        : '<button class="btn-sm" style="min-width: 90px; background: #6366f1; color: white; border: 1px solid #6366f1;" onclick="toggleAdmin(\'' + faculty.id + '\')" title="Make admin">🔐 Admin</button>') +
                      '<button class="btn-danger btn-sm" style="min-width: 90px;" onclick="deleteFaculty(\'' + faculty.id + '\')">Delete</button>' +
                    '</div></td>';

    tbody.appendChild(row);
  });
}

// Update faculty count
function updateFacultyCount() {
  const activeCount = allFaculty.filter(function(f) { return f.active; }).length;
  const totalCount = allFaculty.length;
  document.getElementById('facultyCount').textContent = activeCount + ' active / ' + totalCount + ' total';
}

// Add new faculty
async function addFaculty() {
  const id = document.getElementById('newFacultyId').value.trim().toLowerCase();
  const name = document.getElementById('newFacultyName').value.trim();
  const email = document.getElementById('newFacultyEmail').value.trim();
  const rank = document.getElementById('newFacultyRank').value;
  const clinical_effort_pct = parseInt(document.getElementById('newFacultyEffort').value) || 0;
  const base_points = parseInt(document.getElementById('newFacultyBasePoints').value) || 0;

  if (!id || !name || !email || !rank) {
    showAlert('facultyAlert', 'Please fill in all required fields (ID, Name, Email, Rank)', 'error');
    return;
  }

  try {
    const response = await fetch('/api/admin/faculty', {
      credentials: 'same-origin',
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        id: id,
        name: name,
        email: email,
        rank: rank,
        clinical_effort_pct: clinical_effort_pct,
        base_points: base_points
      })
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to add faculty');
    }

    showAlert('facultyAlert', 'Faculty member added successfully', 'success');

    // Clear form
    document.getElementById('newFacultyId').value = '';
    document.getElementById('newFacultyName').value = '';
    document.getElementById('newFacultyEmail').value = '';
    document.getElementById('newFacultyRank').value = '';
    document.getElementById('newFacultyEffort').value = '';
    document.getElementById('newFacultyBasePoints').value = '';

    // Reload list
    await loadFaculty();

  } catch (error) {
    console.error('Error adding faculty:', error);
    showAlert('facultyAlert', 'Failed to add faculty: ' + error.message, 'error');
  }
}

// Open edit modal
function openEditFaculty(facultyId) {
  const faculty = allFaculty.find(function(f) { return f.id === facultyId; });
  if (!faculty) return;

  currentEditingId = facultyId;

  document.getElementById('editFacultyId').value = faculty.id;
  document.getElementById('editFacultyName').value = faculty.name || '';
  document.getElementById('editFacultyEmail').value = faculty.email || '';
  document.getElementById('editFacultyRank').value = faculty.rank || '';
  document.getElementById('editFacultyEffort').value = faculty.clinical_effort_pct || 0;
  document.getElementById('editFacultyBasePoints').value = faculty.base_points || 0;
  document.getElementById('editFacultyBonusPoints').value = faculty.bonus_points || 0;
  document.getElementById('editFacultyAdmin').checked = faculty.is_admin || false;
  document.getElementById('editFacultyMoonlighter').checked = faculty.moonlighter || false;
  document.getElementById('editFacultyDraftExempt').checked = faculty.draft_exempt || false;
  document.getElementById('editFacultyMoonlightingPriority').value = faculty.moonlighting_priority || 2;

  // Show/hide the priority field depending on whether this person is a moonlighter
  document.getElementById('moonlightingPriorityGroup').style.display =
    faculty.moonlighter ? '' : 'none';

  // Expected clinical weeks
  document.getElementById('editFacultyMicuWeeks').value = faculty.micu_weeks || 0;
  document.getElementById('editFacultyAppIcuWeeks').value = faculty.app_icu_weeks || 0;
  document.getElementById('editFacultyProcedureWeeks').value = faculty.procedure_weeks || 0;
  document.getElementById('editFacultyConsultWeeks').value = faculty.consult_weeks || 0;
  document.getElementById('editFacultyBackupWeeks').value = faculty.backup_weeks || 0;

  document.getElementById('editFacultyModal').classList.add('show');
}

// Close edit modal
function closeEditFacultyModal() {
  document.getElementById('editFacultyModal').classList.remove('show');
  currentEditingId = null;
}

// Submit edit faculty
async function submitEditFaculty(event) {
  event.preventDefault();

  if (!currentEditingId) return;

  const payload = {
    name: document.getElementById('editFacultyName').value.trim(),
    email: document.getElementById('editFacultyEmail').value.trim() || null,
    rank: document.getElementById('editFacultyRank').value || null,
    clinical_effort_pct: parseInt(document.getElementById('editFacultyEffort').value) || 0,
    base_points: parseInt(document.getElementById('editFacultyBasePoints').value) || 0,
    bonus_points: parseFloat(document.getElementById('editFacultyBonusPoints').value) || 0,
    is_admin: document.getElementById('editFacultyAdmin').checked,
    moonlighter: document.getElementById('editFacultyMoonlighter').checked,
    draft_exempt: document.getElementById('editFacultyDraftExempt').checked,
    moonlighting_priority: parseInt(document.getElementById('editFacultyMoonlightingPriority').value) || 2,
    micu_weeks: parseInt(document.getElementById('editFacultyMicuWeeks').value) || 0,
    app_icu_weeks: parseInt(document.getElementById('editFacultyAppIcuWeeks').value) || 0,
    procedure_weeks: parseInt(document.getElementById('editFacultyProcedureWeeks').value) || 0,
    consult_weeks: parseInt(document.getElementById('editFacultyConsultWeeks').value) || 0,
    backup_weeks: parseInt(document.getElementById('editFacultyBackupWeeks').value) || 0
  };

  // Strip null values — the backend uses exclude_unset, so omitting a field
  // keeps the existing DB value rather than overwriting it with null
  const cleanPayload = Object.fromEntries(
    Object.entries(payload).filter(([_, v]) => v !== null)
  );

  try {
    const response = await fetch('/api/admin/faculty/' + currentEditingId, {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(cleanPayload)
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to update faculty');
    }

    showAlert('facultyAlert', 'Faculty updated successfully', 'success');
    closeEditFacultyModal();
    await loadFaculty();

  } catch (error) {
    console.error('Error updating faculty:', error);
    alert('Failed to update faculty: ' + error.message);
  }
}

// Toggle faculty active status
async function toggleFacultyStatus(facultyId, newStatus) {
  const action = newStatus ? 'activate' : 'deactivate';

  if (!confirm('Are you sure you want to ' + action + ' this faculty member?')) {
    return;
  }

  try {
    const response = await fetch('/api/admin/faculty/' + facultyId + '/status', {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ is_active: newStatus })
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to update status');
    }

    showAlert('facultyAlert', 'Faculty status updated', 'success');
    await loadFaculty();

  } catch (error) {
    console.error('Error updating status:', error);
    showAlert('facultyAlert', 'Failed to update status: ' + error.message, 'error');
  }
}

// Delete faculty
async function deleteFaculty(facultyId) {
  const faculty = allFaculty.find(function(f) { return f.id === facultyId; });
  if (!faculty) return;

  const confirmMessage = 'DELETE FACULTY MEMBER?\n\n' +
                        'Name: ' + faculty.name + '\n' +
                        'ID: ' + faculty.id + '\n\n' +
                        'This will permanently delete this faculty member.\n' +
                        'Any existing assignments may need to be reassigned.\n\n' +
                        'This action cannot be undone. Continue?';

  if (!confirm(confirmMessage)) {
    return;
  }

  try {
    const response = await fetch('/api/admin/faculty/' + facultyId, {
      method: 'DELETE'
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to delete faculty');
    }

    showAlert('facultyAlert', 'Faculty member deleted', 'success');
    await loadFaculty();

  } catch (error) {
    console.error('Error deleting faculty:', error);
    showAlert('facultyAlert', 'Failed to delete faculty: ' + error.message, 'error');
  }
}

// Toggle admin status
async function toggleAdmin(facultyId) {
  const faculty = allFaculty.find(function(f) { return f.id === facultyId; });
  if (!faculty) return;

  const newStatus = !faculty.is_admin;
  const action = newStatus ? 'grant admin privileges to' : 'remove admin privileges from';

  if (!confirm('Are you sure you want to ' + action + ' ' + faculty.name + '?')) {
    return;
  }

  try {
    const response = await fetch('/api/admin/faculty/' + facultyId, {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ is_admin: newStatus })
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to update admin status');
    }

    showAlert('facultyAlert', faculty.name + ' admin status updated', 'success');
    await loadFaculty();

  } catch (error) {
    console.error('Error toggling admin:', error);
    showAlert('facultyAlert', 'Failed to update admin status: ' + error.message, 'error');
  }
}


// ==================== GLOBAL FUNCTION EXPORTS ====================
// Make functions globally accessible for inline onclick handlers

window.calcNewBasePoints = calcNewBasePoints;
window.calcEditBasePoints = calcEditBasePoints;
window.loadFaculty = loadFaculty;
window.addFaculty = addFaculty;
window.openEditFaculty = openEditFaculty;
window.closeEditFacultyModal = closeEditFacultyModal;
window.submitEditFaculty = submitEditFaculty;
window.toggleFacultyStatus = toggleFacultyStatus;
window.deleteFaculty = deleteFaculty;
window.toggleAdmin = toggleAdmin;

// ==================== MODAL CLOSE FUNCTIONALITY ====================

// Close modal when clicking outside (on backdrop)
document.addEventListener('DOMContentLoaded', function() {
  const modal = document.getElementById('editFacultyModal');
  if (modal) {
    modal.addEventListener('click', function(event) {
      // Only close if clicking directly on the modal backdrop, not the content
      if (event.target === modal) {
        closeEditFacultyModal();
      }
    });
  }
});

// Close modal when pressing ESC key
document.addEventListener('keydown', function(event) {
  if (event.key === 'Escape') {
    const modal = document.getElementById('editFacultyModal');
    if (modal && modal.classList.contains('show')) {
      closeEditFacultyModal();
    }
  }
});
