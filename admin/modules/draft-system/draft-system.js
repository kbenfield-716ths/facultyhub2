/**
 * Draft System Module
 * Manage availability request draft rounds
 */

let activeDraft = null;
let draftSlots = [];

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
    const rounds = data.rounds || [];

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
      draftSlots = slotsData.slots || [];
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

// Show create draft modal
function showCreateDraftModal() {
  document.getElementById('createDraftModal').classList.add('show');
}

// Close create draft modal
function closeCreateDraftModal() {
  document.getElementById('createDraftModal').classList.remove('show');
}

// Submit create draft
async function submitCreateDraft(event) {
  event.preventDefault();

  const payload = {
    year: parseInt(document.getElementById('draftYear').value),
    window_size: parseInt(document.getElementById('windowSize').value),
    hours_per_slot: parseInt(document.getElementById('hoursPerSlot').value)
  };

  if (!payload.year) {
    alert('Please select a year');
    return;
  }

  try {
    const response = await fetch('/api/draft/admin/rounds', {
      credentials: 'same-origin',
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to create draft');
    }

    showAlert('draftAlert', 'Draft created successfully! Click "Start Draft" to begin.', 'success');
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

    if (result.advanced_slots > 0) {
      showAlert('draftAlert', 'Advanced ' + result.advanced_slots + ' expired slot(s)', 'success');
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
    const allRounds = data.rounds || [];
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
