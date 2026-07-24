/**
 * Draft System Module
 * Manage availability request draft rounds
 */

let activeDraft = null;
let draftSlots = [];
let draftFacultyList = [];        // Full faculty list from API
let selectedFacultyIds = new Set();  // Currently selected for draft

// Load draft on init
document.addEventListener('DOMContentLoaded', function() {
  if (document.getElementById('activeDraftSection')) {
    loadActiveDraft();
  }
});

// Load active draft
async function loadActiveDraft() {
  try {
    showAlert('draftAlert', '', 'clear');

    // Get all rounds and find active one
    const response = await fetch('/api/draft/admin/rounds', { credentials: 'same-origin' });
    if (!response.ok) throw new Error('Failed to load drafts');

    const data = await response.json();
    const rounds = Array.isArray(data) ? data : (data.rounds || []);  // FIXED

    // Find active round (not completed)
    activeDraft = rounds.find(function(r) { return r.status !== 'completed'; });

    if (!activeDraft) {
      // No active draft
      document.getElementById('activeDraftSection').style.display = 'none';
      document.getElementById('noActiveDraft').style.display = 'block';
      await loadPastDrafts();
      return;
    }

    // Load slots for this round
    const slotsResponse = await fetch('/api/draft/admin/rounds/' + activeDraft.id + '/slots');
    if (slotsResponse.ok) {
      const slotsData = await slotsResponse.json();
      draftSlots = Array.isArray(slotsData) ? slotsData : (slotsData.slots || []);
    } else {
      draftSlots = [];
    }

    renderActiveDraft();
    renderDraftSlots();

    document.getElementById('activeDraftSection').style.display = 'block';
    document.getElementById('noActiveDraft').style.display = 'none';

    await loadPastDrafts();

  } catch (error) {
    console.error('Error loading draft:', error);
    showAlert('draftAlert', 'Failed to load draft: ' + error.message, 'error');
  }
}

// Render active draft
function renderActiveDraft() {
  document.getElementById('activeDraftYear').textContent = activeDraft.year + '-' + (parseInt(activeDraft.year) + 1);
  document.getElementById('activeDraftStatus').textContent = capitalize(activeDraft.status);
  document.getElementById('activeDraftWindow').textContent = activeDraft.window_size + ' hours';
  document.getElementById('activeDraftHours').textContent = activeDraft.hours_per_slot + ' hours';
  document.getElementById('activeDraftFacultyCount').textContent = draftSlots.length;

  // Show/hide buttons based on status
  const pauseBtn = document.getElementById('pauseBtn');
  const resumeBtn = document.getElementById('resumeBtn');
  const startBtn = document.getElementById('startBtn');
  const completeBtn = document.getElementById('completeBtn');

  pauseBtn.style.display = 'none';
  resumeBtn.style.display = 'none';
  startBtn.style.display = 'none';

  if (activeDraft.status === 'not_started') {
    startBtn.style.display = 'inline-block';
  } else if (activeDraft.status === 'active') {
    pauseBtn.style.display = 'inline-block';
  } else if (activeDraft.status === 'paused') {
    resumeBtn.style.display = 'inline-block';
  }
}

// Render draft slots
function renderDraftSlots() {
  const tbody = document.getElementById('draftSlotsTableBody');

  if (draftSlots.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" class="empty-state"><div class="empty-state-title">No Slots</div></td></tr>';
    return;
  }

  // Count statuses
  const counts = {submitted: 0, active: 0, waiting: 0, expired: 0};
  draftSlots.forEach(function(slot) {
    counts[slot.status] = (counts[slot.status] || 0) + 1;
  });

  document.getElementById('submittedCount').textContent = counts.submitted;
  document.getElementById('activeCount').textContent = counts.active;
  document.getElementById('waitingCount').textContent = counts.waiting;
  document.getElementById('expiredCount').textContent = counts.expired;

  tbody.innerHTML = '';

  draftSlots.forEach(function(slot) {
    const row = document.createElement('tr');

    // Status badge
    let statusBadge = '';
    if (slot.status === 'submitted') {
      statusBadge = '<span class="badge badge-success">Submitted</span>';
    } else if (slot.status === 'active') {
      statusBadge = '<span class="badge badge-warning">Active</span>';
    } else if (slot.status === 'waiting') {
      statusBadge = '<span class="badge badge-info">Waiting</span>';
    } else if (slot.status === 'expired') {
      statusBadge = '<span class="badge badge-danger">Expired</span>';
    }

    // Time remaining
    let timeRemaining = '-';
    if (slot.status === 'active' && slot.deadline) {
      timeRemaining = calculateTimeRemaining(slot.deadline);
    }

    row.innerHTML = '<td style="text-align: center; font-weight: 700;">' + slot.priority + '</td>' +
                    '<td>' + slot.faculty_name + '</td>' +
                    '<td>' + statusBadge + '</td>' +
                    '<td>' + (slot.notified_at ? formatDateTime(slot.notified_at) : '-') + '</td>' +
                    '<td>' + (slot.deadline ? formatDateTime(slot.deadline) : '-') + '</td>' +
                    '<td>' + (slot.submitted_at ? formatDateTime(slot.submitted_at) : '-') + '</td>' +
                    '<td>' + timeRemaining + '</td>';

    tbody.appendChild(row);
  });
}

// Calculate time remaining
function calculateTimeRemaining(deadline) {
  const now = new Date();
  const deadlineDate = new Date(deadline);
  const diff = deadlineDate - now;

  if (diff <= 0) return 'Expired';

  const hours = Math.floor(diff / (1000 * 60 * 60));
  const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));

  return hours + 'h ' + minutes + 'm';
}

// ==================== FACULTY PICKER ====================

// Load faculty list for the picker
async function loadFacultyForPicker() {
  var listEl = document.getElementById('facultyPickerList');
  if (!listEl) return;

  try {
    var response = await fetch('/api/admin/faculty', { credentials: 'same-origin' });
    if (!response.ok) throw new Error('Failed to load faculty');

    var data = await response.json();
    // Filter to active, non-draft-exempt only
    draftFacultyList = (Array.isArray(data) ? data : (data.faculty || [])).filter(function(f) {
      return f.active !== false && !f.draft_exempt;
    });

    // Sort alphabetically by name
    draftFacultyList.sort(function(a, b) {
      return (a.name || '').localeCompare(b.name || '');
    });

    renderFacultyPicker();
  } catch (error) {
    console.error('Error loading faculty for picker:', error);
    listEl.innerHTML = '<div style="text-align:center;padding:24px;color:#ef4444;">Failed to load faculty</div>';
  }
}

// Render the faculty picker list
function renderFacultyPicker() {
  var listEl = document.getElementById('facultyPickerList');
  if (!listEl || draftFacultyList.length === 0) {
    if (listEl) listEl.innerHTML = '<div style="text-align:center;padding:24px;color:#9ca3af;">No eligible faculty found</div>';
    return;
  }

  listEl.innerHTML = '';

  // Build ordered list: selected first (in order), then unselected
  var orderedFaculty = getOrderedFaculty();

  var priorityNum = 0;
  orderedFaculty.forEach(function(f) {
    var isSelected = selectedFacultyIds.has(f.id);
    if (isSelected) priorityNum++;

    var div = document.createElement('div');
    div.className = 'faculty-pick-item' + (isSelected ? ' selected' : '');
    div.setAttribute('data-faculty-id', f.id);
    div.draggable = true;

    div.innerHTML =
      '<input type="checkbox" ' + (isSelected ? 'checked' : '') + ' onclick="toggleFacultySelection(\'' + f.id + '\')">' +
      '<span class="faculty-pick-priority">' + (isSelected ? priorityNum : '-') + '</span>' +
      '<span class="faculty-pick-name">' + (f.name || f.id) + '</span>' +
      '<span class="faculty-pick-drag">&#x2630;</span>';

    // Drag events
    div.addEventListener('dragstart', onFacultyDragStart);
    div.addEventListener('dragover', onFacultyDragOver);
    div.addEventListener('dragleave', onFacultyDragLeave);
    div.addEventListener('drop', onFacultyDrop);
    div.addEventListener('dragend', onFacultyDragEnd);

    listEl.appendChild(div);
  });

  updateFacultyCount();
}

// Get faculty in current order (selected items maintain their list order)
function getOrderedFaculty() {
  var listEl = document.getElementById('facultyPickerList');
  var currentOrder = [];

  if (listEl && listEl.children.length > 0) {
    // Preserve current DOM order
    for (var i = 0; i < listEl.children.length; i++) {
      var id = listEl.children[i].getAttribute('data-faculty-id');
      var faculty = draftFacultyList.find(function(f) { return f.id === id; });
      if (faculty) currentOrder.push(faculty);
    }
    // Add any new faculty not yet in DOM
    draftFacultyList.forEach(function(f) {
      if (!currentOrder.find(function(c) { return c.id === f.id; })) {
        currentOrder.push(f);
      }
    });
    return currentOrder;
  }

  return draftFacultyList.slice();
}

// Toggle faculty selection
function toggleFacultySelection(facultyId) {
  if (selectedFacultyIds.has(facultyId)) {
    selectedFacultyIds.delete(facultyId);
  } else {
    selectedFacultyIds.add(facultyId);
  }
  renderFacultyPicker();
}

// Select All / Deselect All
function toggleSelectAllFaculty() {
  var searchTerm = (document.getElementById('facultySearchInput') || {}).value || '';
  var visibleFaculty = getVisibleFaculty(searchTerm);

  // If all visible are selected, deselect them; otherwise select all visible
  var allVisibleSelected = visibleFaculty.every(function(f) { return selectedFacultyIds.has(f.id); });

  if (allVisibleSelected) {
    visibleFaculty.forEach(function(f) { selectedFacultyIds.delete(f.id); });
  } else {
    visibleFaculty.forEach(function(f) { selectedFacultyIds.add(f.id); });
  }

  renderFacultyPicker();
  applyFacultySearch();
}

function getVisibleFaculty(searchTerm) {
  if (!searchTerm) return draftFacultyList.slice();
  var term = searchTerm.toLowerCase();
  return draftFacultyList.filter(function(f) {
    return (f.name || '').toLowerCase().indexOf(term) !== -1;
  });
}

function updateFacultyCount() {
  var countEl = document.getElementById('facultySelectedCount');
  if (countEl) {
    var n = selectedFacultyIds.size;
    countEl.textContent = n + ' selected' + (draftFacultyList.length ? ' of ' + draftFacultyList.length : '');
  }

  var btn = document.getElementById('selectAllBtn');
  if (btn) {
    btn.textContent = selectedFacultyIds.size === draftFacultyList.length ? 'Deselect All' : 'Select All';
  }
}

// Faculty search filter
function applyFacultySearch() {
  var term = ((document.getElementById('facultySearchInput') || {}).value || '').toLowerCase();
  var listEl = document.getElementById('facultyPickerList');
  if (!listEl) return;

  for (var i = 0; i < listEl.children.length; i++) {
    var item = listEl.children[i];
    var nameEl = item.querySelector('.faculty-pick-name');
    var name = nameEl ? nameEl.textContent.toLowerCase() : '';
    if (!term || name.indexOf(term) !== -1) {
      item.classList.remove('hidden');
    } else {
      item.classList.add('hidden');
    }
  }
}

// ==================== DRAG AND DROP ====================

var dragSrcEl = null;

function onFacultyDragStart(e) {
  dragSrcEl = this;
  this.classList.add('dragging');
  e.dataTransfer.effectAllowed = 'move';
  e.dataTransfer.setData('text/plain', this.getAttribute('data-faculty-id'));
}

function onFacultyDragOver(e) {
  e.preventDefault();
  e.dataTransfer.dropEffect = 'move';
  this.classList.add('drag-over');
}

function onFacultyDragLeave(e) {
  this.classList.remove('drag-over');
}

function onFacultyDrop(e) {
  e.preventDefault();
  this.classList.remove('drag-over');

  if (dragSrcEl !== this) {
    var list = this.parentNode;
    // Insert dragged item before or after this item
    var allItems = Array.from(list.children);
    var dragIdx = allItems.indexOf(dragSrcEl);
    var dropIdx = allItems.indexOf(this);

    if (dragIdx < dropIdx) {
      list.insertBefore(dragSrcEl, this.nextSibling);
    } else {
      list.insertBefore(dragSrcEl, this);
    }

    // Recalculate priority numbers
    refreshPriorityNumbers();
  }
}

function onFacultyDragEnd(e) {
  this.classList.remove('dragging');
  // Clean up all drag-over classes
  var items = document.querySelectorAll('.faculty-pick-item');
  items.forEach(function(item) { item.classList.remove('drag-over'); });
}

function refreshPriorityNumbers() {
  var listEl = document.getElementById('facultyPickerList');
  if (!listEl) return;

  var num = 0;
  for (var i = 0; i < listEl.children.length; i++) {
    var item = listEl.children[i];
    var id = item.getAttribute('data-faculty-id');
    var prioEl = item.querySelector('.faculty-pick-priority');
    if (selectedFacultyIds.has(id)) {
      num++;
      prioEl.textContent = num;
    } else {
      prioEl.textContent = '-';
    }
  }
}

// Get selected faculty IDs in current DOM order
function getSelectedFacultyInOrder() {
  var listEl = document.getElementById('facultyPickerList');
  var ordered = [];
  if (!listEl) return ordered;

  for (var i = 0; i < listEl.children.length; i++) {
    var id = listEl.children[i].getAttribute('data-faculty-id');
    if (selectedFacultyIds.has(id)) {
      ordered.push(id);
    }
  }
  return ordered;
}

// ==================== MODAL CONTROLS ====================

// Show create draft modal
function showCreateDraftModal() {
  document.getElementById('createDraftModal').classList.add('show');
  selectedFacultyIds.clear();
  loadFacultyForPicker();

  // Wire up search input
  var searchInput = document.getElementById('facultySearchInput');
  if (searchInput) {
    searchInput.value = '';
    searchInput.oninput = applyFacultySearch;
  }
}

// Close create draft modal
function closeCreateDraftModal() {
  document.getElementById('createDraftModal').classList.remove('show');
}

// Submit create draft
async function submitCreateDraft(event) {
  event.preventDefault();

  var selectedList = getSelectedFacultyInOrder();

  if (selectedList.length === 0) {
    alert('Please select at least one faculty member for the draft.');
    return;
  }

  var payload = {
    year: parseInt(document.getElementById('draftYear').value),
    window_size: parseInt(document.getElementById('windowSize').value),
    hours_per_slot: parseInt(document.getElementById('hoursPerSlot').value),
    faculty_priority: selectedList
  };

  if (!payload.year) {
    alert('Please select a year');
    return;
  }

  try {
    var response = await fetch('/api/draft/admin/rounds', {
      credentials: 'same-origin',
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      var error = await response.json();
      throw new Error(error.detail || 'Failed to create draft');
    }

    showAlert('draftAlert', 'Draft created with ' + selectedList.length + ' faculty! Click "Start Draft" to begin.', 'success');
    closeCreateDraftModal();
    await loadActiveDraft();

  } catch (error) {
    console.error('Error creating draft:', error);
    alert('Failed to create draft: ' + error.message);
  }
}

// Start draft
async function startDraft() {
  if (!confirm('Start the draft process?\n\nThe first faculty member will be notified and their slot will open immediately.')) {
    return;
  }

  if (!activeDraft || !activeDraft.id) {
    showAlert('draftAlert', 'No active draft found', 'error');
    return;
  }

  try {
    const response = await fetch('/api/draft/admin/rounds/' + activeDraft.id + '/start', {
      method: 'POST'
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to start draft');
    }

    showAlert('draftAlert', 'Draft started! First slot is now active.', 'success');
    await loadActiveDraft();

  } catch (error) {
    console.error('Error starting draft:', error);
    showAlert('draftAlert', 'Failed to start draft: ' + error.message, 'error');
  }
}

// Pause draft
async function pauseDraft() {
  if (!confirm('Pause the draft?\n\nAll deadlines will be frozen until you resume.')) {
    return;
  }

  if (!activeDraft || !activeDraft.id) {
    showAlert('draftAlert', 'No active draft found', 'error');
    return;
  }

  try {
    const response = await fetch('/api/draft/admin/rounds/' + activeDraft.id + '/pause', {
      method: 'POST'
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to pause draft');
    }

    showAlert('draftAlert', 'Draft paused', 'success');
    await loadActiveDraft();

  } catch (error) {
    console.error('Error pausing draft:', error);
    showAlert('draftAlert', 'Failed to pause draft: ' + error.message, 'error');
  }
}

// Resume draft
async function resumeDraft() {
  if (!confirm('Resume the draft?\n\nDeadlines will continue from where they left off.')) {
    return;
  }

  if (!activeDraft || !activeDraft.id) {
    showAlert('draftAlert', 'No active draft found', 'error');
    return;
  }

  try {
    const response = await fetch('/api/draft/admin/rounds/' + activeDraft.id + '/resume', {
      method: 'POST'
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to resume draft');
    }

    showAlert('draftAlert', 'Draft resumed', 'success');
    await loadActiveDraft();

  } catch (error) {
    console.error('Error resuming draft:', error);
    showAlert('draftAlert', 'Failed to resume draft: ' + error.message, 'error');
  }
}

// Complete draft
async function completeDraft() {
  const confirmMessage = 'Mark draft as complete?\n\n' +
                        'This will:\n' +
                        '- Close all active slots\n' +
                        '- Finalize all submissions\n' +
                        '- Move draft to history\n\n' +
                        'Continue?';

  if (!confirm(confirmMessage)) {
    return;
  }

  if (!activeDraft || !activeDraft.id) {
    showAlert('draftAlert', 'No active draft found', 'error');
    return;
  }

  try {
    const response = await fetch('/api/draft/admin/rounds/' + activeDraft.id + '/complete', {
      method: 'POST'
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to complete draft');
    }

    showAlert('draftAlert', 'Draft marked as complete', 'success');
    await loadActiveDraft();

  } catch (error) {
    console.error('Error completing draft:', error);
    showAlert('draftAlert', 'Failed to complete draft: ' + error.message, 'error');
  }
}

// Check expired slots
async function checkExpiredSlots() {
  if (!activeDraft || !activeDraft.id) {
    showAlert('draftAlert', 'No active draft found', 'error');
    return;
  }

  try {
    const response = await fetch('/api/draft/admin/rounds/' + activeDraft.id + '/check-expired', {
      method: 'POST'
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to check expired slots');
    }

    const result = await response.json();

    if (result.expired_count > 0 || result.activated_count > 0) {
      showAlert('draftAlert', 'Expired: ' + (result.expired_count || 0) + ', Activated: ' + (result.activated_count || 0), 'success');
      await loadActiveDraft();
    } else {
      showAlert('draftAlert', 'No expired slots to advance', 'info');
    }

  } catch (error) {
    console.error('Error checking expired slots:', error);
    showAlert('draftAlert', 'Failed to check expired slots: ' + error.message, 'error');
  }
}

// Load past drafts
async function loadPastDrafts() {
  try {
    const response = await fetch('/api/draft/admin/rounds', { credentials: 'same-origin' });
    if (!response.ok) return;

    const data = await response.json();
    const allRounds = Array.isArray(data) ? data : (data.rounds || []);  // FIXED
    const pastDrafts = allRounds.filter(function(r) { return r.status === 'completed'; });

    if (pastDrafts.length === 0) {
      document.getElementById('pastDraftsSection').style.display = 'none';
      return;
    }

    document.getElementById('pastDraftsSection').style.display = 'block';

    const html = pastDrafts.map(function(draft) {
      return '<div style="background: #f9fafb; padding: 16px; border-radius: 8px; margin-bottom: 12px; border-left: 4px solid #667eea;">' +
        '<div style="display: flex; justify-content: space-between; align-items: center;">' +
          '<div>' +
            '<strong>' + draft.year + '-' + (parseInt(draft.year) + 1) + '</strong>' +
            '<span style="margin-left: 12px; color: #6b7280;">Window: ' + draft.window_size + 'h | Slot: ' + draft.hours_per_slot + 'h</span>' +
          '</div>' +
          '<div style="color: #6b7280; font-size: 13px;">' +
            'Completed ' + formatDate(draft.completed_at) +
          '</div>' +
        '</div>' +
      '</div>';
    }).join('');

    document.getElementById('pastDraftsList').innerHTML = html;

  } catch (error) {
    console.error('Error loading past drafts:', error);
  }
}

// ==================== GLOBAL FUNCTION EXPORTS ====================
// Make functions globally accessible for inline onclick handlers

window.showCreateDraftModal = showCreateDraftModal;
window.closeCreateDraftModal = closeCreateDraftModal;
window.startDraft = startDraft;
window.pauseDraft = pauseDraft;
window.resumeDraft = resumeDraft;
window.completeDraft = completeDraft;
window.checkExpiredSlots = checkExpiredSlots;
window.toggleFacultySelection = toggleFacultySelection;
window.toggleSelectAllFaculty = toggleSelectAllFaculty;

// ==================== MODAL CLOSE FUNCTIONALITY ====================

// Close modal when clicking outside (on backdrop)
document.addEventListener('DOMContentLoaded', function() {
  const modal = document.getElementById('createDraftModal');
  if (modal) {
    modal.addEventListener('click', function(event) {
      // Only close if clicking directly on the modal backdrop, not the content
      if (event.target === modal) {
        closeCreateDraftModal();
      }
    });

    // Also attach listeners to close button and cancel button
    const closeBtn = modal.querySelector('.close-btn');
    const cancelBtn = modal.querySelector('button[type="button"].btn-secondary');

    if (closeBtn) {
      closeBtn.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        closeCreateDraftModal();
      });
    }

    if (cancelBtn) {
      cancelBtn.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        closeCreateDraftModal();
      });
    }
  }
});

// Close modal when pressing ESC key
document.addEventListener('keydown', function(event) {
  if (event.key === 'Escape') {
    const modal = document.getElementById('createDraftModal');
    if (modal && modal.classList.contains('show')) {
      closeCreateDraftModal();
    }
  }
});
