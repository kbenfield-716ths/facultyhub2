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
    tbody.innerHTML = '<tr><td colspan="13" class="empty-state"><div class="empty-state-icon">👥</div><div class="empty-state-title">No Faculty Members</div><div class="empty-state-description">Add your first faculty member using the form above</div></td></tr>';
    return;
  }

  tbody.innerHTML = '';

  allFaculty.forEach(function(faculty) {
    const row = document.createElement('tr');

    // Compute totals
    const total = (faculty.micu_count || 0) + (faculty.app_icu_count || 0) +
                  (faculty.procedures_count || 0) + (faculty.consults_count || 0);

    // Status badge
    const statusBadge = faculty.active
      ? '<span class="badge badge-success">Active</span>'
      : '<span class="badge badge-danger">Inactive</span>';

    // Admin badge
    const adminBadge = faculty.is_admin
      ? ' <span class="badge badge-info">Admin</span>'
      : '';

    // Moonlighter badge
    const moonlighterBadge = faculty.moonlighter
      ? ' <span class="badge badge-warning">🌙 Moonlighter</span>'
      : '';

    row.innerHTML = '<td style="font-weight: 600;">' + (faculty.id || '') + '</td>' +
                    '<td>' + (faculty.name || '') + adminBadge + moonlighterBadge + '</td>' +
                    '<td style="font-size: 13px;">' + (faculty.email || '-') + '</td>' +
                    '<td>' + (faculty.rank || '-') + '</td>' +
                    '<td style="text-align: center;">' + (faculty.clinical_effort_pct || 0) + '%</td>' +
                    '<td style="text-align: center; font-weight: 600;">' + (faculty.bonus_points || 0) + '</td>' +
                    '<td style="text-align: center;">' + (faculty.micu_count || 0) + '</td>' +
                    '<td style="text-align: center;">' + (faculty.app_icu_count || 0) + '</td>' +
                    '<td style="text-align: center;">' + (faculty.procedures_count || 0) + '</td>' +
                    '<td style="text-align: center;">' + (faculty.consults_count || 0) + '</td>' +
                    '<td style="text-align: center; font-weight: 700;">' + total + '</td>' +
                    '<td>' + statusBadge + '</td>' +
                    '<td><div class="action-buttons">' +
                      '<button class="btn-primary btn-sm" onclick="openEditFaculty(\'' + faculty.id + '\')">Edit</button>' +
                      (faculty.active
                        ? '<button class="btn-secondary btn-sm" onclick="toggleFacultyStatus(\'' + faculty.id + '\', false)">Deactivate</button>'
                        : '<button class="btn-success btn-sm" onclick="toggleFacultyStatus(\'' + faculty.id + '\', true)">Activate</button>') +
                      '<button class="btn-danger btn-sm" onclick="deleteFaculty(\'' + faculty.id + '\')">Delete</button>' +
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

  if (!id || !name) {
    showAlert('facultyAlert', 'Please provide both ID and Name', 'error');
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
        email: email || null
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
  document.getElementById('editFacultyEffort').value = faculty.effort_percent || 0;
  document.getElementById('editFacultyPoints').value = faculty.bonus_points || 0;
  document.getElementById('editFacultyAdmin').checked = faculty.is_admin || false;

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
    effort_percent: parseFloat(document.getElementById('editFacultyEffort').value) || 0,
    bonus_points: parseFloat(document.getElementById('editFacultyPoints').value) || 0,
    is_admin: document.getElementById('editFacultyAdmin').checked
  };

  try {
    const response = await fetch('/api/admin/faculty/' + currentEditingId, {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
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
