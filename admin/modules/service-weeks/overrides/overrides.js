/**
 * Service Week Overrides Module
 * Admin controls for blocking/assigning faculty
 */

let blocks = [];
let manualAssignments = [];
let facultyList = [];
let weeksList = [];

// ==================== TAB SWITCHING ====================

function showOverrideTab(tabName) {
  document.querySelectorAll('.sub-tab-content').forEach(tab => tab.classList.remove('active'));
  document.querySelectorAll('.sub-tab-btn').forEach(btn => btn.classList.remove('active'));

  document.getElementById('override-tab-' + tabName).classList.add('active');
  event.target.classList.add('active');

  if (tabName === 'blocks') {
    loadBlocks();
  } else if (tabName === 'assignments') {
    loadManualAssignments();
  }
}

// ==================== BLOCKS ====================

async function loadBlocks() {
  try {
    const response = await fetch('/api/admin/service-weeks/blocks?year=2026', {
      credentials: 'same-origin'
    });

    if (!response.ok) throw new Error('Failed to load blocks');

    blocks = await response.json();
    renderBlocksTable();
  } catch (error) {
    showOverrideAlert('Error: ' + error.message, 'error');
  }
}

function renderBlocksTable() {
  const tbody = document.getElementById('blocksTableBody');

  if (blocks.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; padding: 40px; color: #9ca3af;">No blocks found. Click "Create New Block" to add one.</td></tr>';
    return;
  }

  tbody.innerHTML = blocks.map(block =>
    '<tr>' +
      '<td>' + block.faculty_name + '</td>' +
      '<td>' + block.week_label + '</td>' +
      '<td>' + (block.reason || 'No reason provided') + '</td>' +
      '<td>' + (block.created_by_name || 'Admin') + '</td>' +
      '<td>' + new Date(block.created_at).toLocaleDateString() + '</td>' +
      '<td><button class="btn-danger btn-sm" onclick="deleteBlock(\'' + block.id + '\')">Delete</button></td>' +
    '</tr>'
  ).join('');
}

async function deleteBlock(blockId) {
  if (!confirm('Delete this block? Faculty will be eligible for this week again.')) return;

  try {
    const response = await fetch('/api/admin/service-weeks/blocks/' + blockId, {
      method: 'DELETE',
      credentials: 'same-origin'
    });

    if (!response.ok) throw new Error('Delete failed');

    showOverrideAlert('Block deleted successfully', 'success');
    await loadBlocks();
  } catch (error) {
    showOverrideAlert('Error: ' + error.message, 'error');
  }
}

// ==================== MANUAL ASSIGNMENTS ====================

async function loadManualAssignments() {
  try {
    const response = await fetch('/api/admin/service-weeks/manual-assignments?year=2026', {
      credentials: 'same-origin'
    });

    if (!response.ok) throw new Error('Failed to load assignments');

    manualAssignments = await response.json();
    renderAssignmentsTable();
  } catch (error) {
    showOverrideAlert('Error: ' + error.message, 'error');
  }
}

function renderAssignmentsTable() {
  const tbody = document.getElementById('assignmentsTableBody');

  if (manualAssignments.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; padding: 40px; color: #9ca3af;">No manual assignments found. Click "Create Manual Assignment" to add one.</td></tr>';
    return;
  }

  tbody.innerHTML = manualAssignments.map(assignment =>
    '<tr>' +
      '<td>' + assignment.faculty_name + '</td>' +
      '<td>' + assignment.week_label + '</td>' +
      '<td><span class="badge">' + assignment.service_type + '</span></td>' +
      '<td>' + (assignment.reason || 'No reason provided') + '</td>' +
      '<td>' + (assignment.created_by_name || 'Admin') + '</td>' +
      '<td>' + new Date(assignment.created_at).toLocaleDateString() + '</td>' +
      '<td><button class="btn-danger btn-sm" onclick="deleteAssignment(\'' + assignment.id + '\')">Delete</button></td>' +
    '</tr>'
  ).join('');
}

async function deleteAssignment(assignmentId) {
  if (!confirm('Delete this manual assignment?')) return;

  try {
    const response = await fetch('/api/admin/service-weeks/manual-assignments/' + assignmentId, {
      method: 'DELETE',
      credentials: 'same-origin'
    });

    if (!response.ok) throw new Error('Delete failed');

    showOverrideAlert('Assignment deleted successfully', 'success');
    await loadManualAssignments();
  } catch (error) {
    showOverrideAlert('Error: ' + error.message, 'error');
  }
}

// ==================== MODALS ====================

async function showCreateBlockModal() {
  await loadFacultyAndWeeks();
  populateSelect('blockFacultyId', facultyList, 'id', 'name');
  populateSelect('blockWeekId', weeksList, 'id', 'label');
  document.getElementById('createBlockModal').style.display = 'flex';
}

function closeCreateBlockModal() {
  document.getElementById('createBlockModal').style.display = 'none';
  document.getElementById('createBlockForm').reset();
}

async function submitBlock(e) {
  e.preventDefault();

  const payload = {
    faculty_id: document.getElementById('blockFacultyId').value,
    week_id: document.getElementById('blockWeekId').value,
    reason: document.getElementById('blockReason').value
  };

  try {
    const response = await fetch('/api/admin/service-weeks/create-block', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (!response.ok) throw new Error('Failed to create block');

    showOverrideAlert('Block created successfully', 'success');
    closeCreateBlockModal();
    await loadBlocks();
  } catch (error) {
    showOverrideAlert('Error: ' + error.message, 'error');
  }
}

async function showCreateAssignmentModal() {
  await loadFacultyAndWeeks();
  populateSelect('assignFacultyId', facultyList, 'id', 'name');
  populateSelect('assignWeekId', weeksList, 'id', 'label');
  document.getElementById('createAssignmentModal').style.display = 'flex';
}

function closeCreateAssignmentModal() {
  document.getElementById('createAssignmentModal').style.display = 'none';
  document.getElementById('createAssignmentForm').reset();
}

async function submitAssignment(e) {
  e.preventDefault();

  const payload = {
    faculty_id: document.getElementById('assignFacultyId').value,
    week_id: document.getElementById('assignWeekId').value,
    service_type: document.getElementById('assignServiceType').value,
    reason: document.getElementById('assignReason').value
  };

  try {
    const response = await fetch('/api/admin/service-weeks/create-manual-assignment', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      let errorMsg = 'Failed to create assignment';
      try {
        const errData = await response.json();
        if (errData.detail) errorMsg = errData.detail;
      } catch (_) {}
      throw new Error(errorMsg);
    }

    const data = await response.json();

    // Show bumped assignments first — these were auto-removed to make room
    if (data.bumped && data.bumped.length > 0) {
      const bumpedNames = data.bumped.join(', ');
      showOverrideAlert(
        'Auto-removed to balance slot count: ' + bumpedNames,
        'warning'
      );
    }

    // Show any conflict warnings (e.g. unavailability override)
    if (data.warnings && data.warnings.length > 0) {
      data.warnings.forEach(function(warning) {
        showOverrideAlert('' + warning, 'warning');
      });
    }

    showOverrideAlert('Manual assignment created successfully', 'success');

    closeCreateAssignmentModal();
    await loadManualAssignments();
  } catch (error) {
    showOverrideAlert('Error: ' + error.message, 'error');
  }
}

// ==================== UTILITIES ====================

async function loadFacultyAndWeeks() {
  if (facultyList.length === 0) {
    const response = await fetch('/api/admin/faculty', { credentials: 'same-origin' });
    facultyList = await response.json();
  }

  if (weeksList.length === 0) {
    const response = await fetch('/api/admin/service-weeks?year=2026', { credentials: 'same-origin' });
    weeksList = await response.json();
  }
}

function populateSelect(selectId, data, valueKey, labelKey) {
  const select = document.getElementById(selectId);
  select.innerHTML = '<option value="">Select...</option>' +
    data.map(item => '<option value="' + item[valueKey] + '">' + item[labelKey] + '</option>').join('');
}

function showOverrideAlert(message, type) {
  const alert = document.getElementById('overridesAlert');
  if (type === 'clear') {
    alert.style.display = 'none';
    return;
  }

  alert.textContent = message;
  alert.className = 'alert alert-' + type;
  alert.style.display = 'block';

  if (type === 'success' || type === 'info') {
    setTimeout(function() { showOverrideAlert('', 'clear'); }, 3000);
  }
}

// ==================== GLOBAL FUNCTION EXPORTS ====================
// Make functions globally accessible for inline onclick handlers

window.showOverrideTab = showOverrideTab;
window.showCreateBlockModal = showCreateBlockModal;
window.showCreateAssignmentModal = showCreateAssignmentModal;
window.closeCreateBlockModal = closeCreateBlockModal;
window.closeCreateAssignmentModal = closeCreateAssignmentModal;
window.submitBlock = submitBlock;
window.submitAssignment = submitAssignment;
window.deleteBlock = deleteBlock;
window.deleteAssignment = deleteAssignment;

// Initialize
document.addEventListener('DOMContentLoaded', function() {
  loadBlocks();

  // ==================== MODAL CLOSE FUNCTIONALITY ====================

  // Close block modal when clicking outside (on backdrop)
  const blockModal = document.getElementById('createBlockModal');
  if (blockModal) {
    blockModal.addEventListener('click', function(event) {
      if (event.target === blockModal) {
        closeCreateBlockModal();
      }
    });
  }

  // Close assignment modal when clicking outside (on backdrop)
  const assignModal = document.getElementById('createAssignmentModal');
  if (assignModal) {
    assignModal.addEventListener('click', function(event) {
      if (event.target === assignModal) {
        closeCreateAssignmentModal();
      }
    });
  }
});

// Close modals when pressing ESC key
document.addEventListener('keydown', function(event) {
  if (event.key === 'Escape') {
    const blockModal = document.getElementById('createBlockModal');
    const assignModal = document.getElementById('createAssignmentModal');

    if (blockModal && blockModal.style.display === 'flex') {
      closeCreateBlockModal();
    }
    if (assignModal && assignModal.style.display === 'flex') {
      closeCreateAssignmentModal();
    }
  }
});
