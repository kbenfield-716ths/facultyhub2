/**
 * Wave-Based Draft Admin Module
 * Manage staggered-start availability request system
 */

let currentConfigId = null;
let currentConfigStatus = null;
let waveDraftAllFaculty = [];

// Note: Module initialization is handled by admin/index.html triggerModuleInit()
// which calls loadConfigs() and loadFacultyForWaves() after the module is loaded

// ===== Load Data =====

async function loadConfigs() {
  try {
    showAlert('waveDraftAlert', '', 'clear');

    const response = await fetch('/api/draft-waves/admin/configs', {
      credentials: 'same-origin'
    });

    if (!response.ok) throw new Error('Failed to load configs');

    const configs = await response.json();

    // Find active config, or if none, find the most recent pending config
    let currentConfig = configs.find(c => c.status === 'active');

    if (!currentConfig) {
      // No active config, find most recent pending
      const pendingConfigs = configs.filter(c => c.status === 'pending');
      if (pendingConfigs.length > 0) {
        // Sort by year descending and take the first
        pendingConfigs.sort((a, b) => b.year - a.year);
        currentConfig = pendingConfigs[0];
      }
    }

    if (currentConfig) {
      currentConfigId = currentConfig.id;
      currentConfigStatus = currentConfig.status;
      await displayActiveConfig(currentConfig);
    } else {
      currentConfigId = null;
      currentConfigStatus = null;
      document.getElementById('activeConfigSection').style.display = 'none';
      document.getElementById('noActiveConfig').style.display = 'block';
    }

    displayAllConfigs(configs);

  } catch (error) {
    console.error('Error loading configs:', error);
    showAlert('waveDraftAlert', 'Failed to load configurations: ' + error.message, 'error');
  }
}

async function displayActiveConfig(config) {
  document.getElementById('activeConfigSection').style.display = 'block';
  document.getElementById('noActiveConfig').style.display = 'none';

  document.getElementById('activeConfigYear').textContent = config.year;
  document.getElementById('activeConfigCloseDate').textContent =
    new Date(config.close_date).toLocaleString();
  document.getElementById('activeConfigStatus').textContent = config.status.toUpperCase();

  // Update header based on status
  const headerCard = document.getElementById('configHeaderCard');
  const headerTitle = document.getElementById('configHeaderTitle');

  if (config.status === 'pending') {
    headerCard.style.background = 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)';
    headerTitle.textContent = '⚙️ Draft Configuration (Pending)';
    document.getElementById('activateBtn').style.display = 'inline-block';
    document.getElementById('notifyBtn').style.display = 'none';
    document.getElementById('resetToPendingBtn').style.display = 'none';
    document.getElementById('addWaveBtn').style.display = 'inline-block';
  } else if (config.status === 'active') {
    headerCard.style.background = 'linear-gradient(135deg, #06b6d4 0%, #0891b2 100%)';
    headerTitle.textContent = '🎯 Active Wave Draft';
    document.getElementById('activateBtn').style.display = 'none';
    document.getElementById('notifyBtn').style.display = 'inline-block';
    document.getElementById('resetToPendingBtn').style.display = 'inline-block';
    document.getElementById('addWaveBtn').style.display = 'none';
  }

  // Load waves
  await loadWaves(config.id);
}

async function loadWaves(configId) {
  try {
    const response = await fetch(`/api/draft-waves/admin/configs/${configId}/waves`, {
      credentials: 'same-origin'
    });

    if (!response.ok) throw new Error('Failed to load waves');

    const waves = await response.json();

    document.getElementById('activeConfigWaveCount').textContent = waves.length;

    displayWaves(waves);

  } catch (error) {
    console.error('Error loading waves:', error);
    showAlert('waveDraftAlert', 'Failed to load waves: ' + error.message, 'error');
  }
}

function displayWaves(waves) {
  const container = document.getElementById('wavesList');

  if (waves.length === 0) {
    container.innerHTML =
      '<div style="text-align: center; padding: 40px; color: #6b7280;">' +
      '<div style="font-size: 48px; margin-bottom: 12px;">🌊</div>' +
      '<p>No waves configured yet. Click "Add Wave" to create your first wave.</p>' +
      '</div>';
    return;
  }

  const now = new Date();
  let html = '';

  waves.forEach(wave => {
    const openDate = new Date(wave.open_date);
    const isOpen = openDate <= now;
    const isPending = openDate > now;

    let badgeClass = 'future';
    let badgeText = 'FUTURE';

    if (isOpen) {
      badgeClass = 'open';
      badgeText = 'OPEN';
    }

    // Show delete button only if config is pending
    const canDelete = currentConfigStatus === 'pending';
    const deleteBtn = canDelete ?
      '<button class="btn-sm btn-danger" onclick="deleteWave(\'' + wave.id + '\', \'' + wave.name + '\')" style="margin-top: 12px;">🗑️ Delete Wave</button>' : '';

    html +=
      '<div class="wave-card">' +
      '<div class="wave-header">' +
      '<div class="wave-name">🌊 Wave ' + wave.wave_order + ': ' + wave.name + '</div>' +
      '<span class="wave-badge ' + badgeClass + '">' + badgeText + '</span>' +
      '</div>' +
      '<div class="wave-info">' +
      '<div class="wave-info-item">' +
      '<div class="wave-info-label">Opens</div>' +
      '<div class="wave-info-value">' + openDate.toLocaleString() + '</div>' +
      '</div>' +
      '<div class="wave-info-item">' +
      '<div class="wave-info-label">Faculty Count</div>' +
      '<div class="wave-info-value">' + wave.faculty_count + ' members</div>' +
      '</div>' +
      '<div class="wave-info-item">' +
      '<div class="wave-info-label">Wave Order</div>' +
      '<div class="wave-info-value">#' + wave.wave_order + '</div>' +
      '</div>' +
      '</div>' +
      deleteBtn +
      '</div>';
  });

  container.innerHTML = html;
}

function displayAllConfigs(configs) {
  const container = document.getElementById('allConfigsList');

  if (configs.length === 0) {
    container.innerHTML = '<p style="color: #6b7280; text-align: center; padding: 20px;">No configurations created yet.</p>';
    return;
  }

  let html = '';

  configs.forEach(config => {
    const isActive = config.status === 'active';
    const activeClass = isActive ? 'active' : '';

    html +=
      '<div class="config-list-item ' + activeClass + '">' +
      '<div>' +
      '<strong style="font-size: 16px;">Year ' + config.year + '</strong>' +
      '<div style="font-size: 13px; color: #6b7280; margin-top: 4px;">' +
      'Closes: ' + new Date(config.close_date).toLocaleString() + ' | ' +
      'Status: <span style="text-transform: uppercase; font-weight: 600;">' + config.status + '</span>' +
      '</div>' +
      '</div>' +
      '<div>' +
      (isActive ? '<span style="color: #06b6d4; font-weight: 600;">● ACTIVE</span>' : '') +
      '</div>' +
      '</div>';
  });

  container.innerHTML = html;
}

async function loadFacultyForWaves() {
  try {
    const response = await fetch('/api/admin/faculty', {
      credentials: 'same-origin'
    });

    if (!response.ok) throw new Error('Failed to load faculty');

    const data = await response.json();
    waveDraftAllFaculty = Array.isArray(data) ? data : (data.faculty || []);

  } catch (error) {
    console.error('Error loading faculty:', error);
  }
}

// ===== Create Config =====

function showCreateConfigModal() {
  document.getElementById('createConfigModal').classList.add('show');
}

function closeCreateConfigModal() {
  document.getElementById('createConfigModal').classList.remove('show');
  document.getElementById('createConfigForm').reset();
}

async function submitCreateConfig(event) {
  event.preventDefault();

  const year = parseInt(document.getElementById('configYear').value);
  const closeDateStr = document.getElementById('configCloseDate').value;

  if (!closeDateStr) {
    showAlert('waveDraftAlert', 'Please select a close date and time', 'error');
    return;
  }

  const closeDate = new Date(closeDateStr).toISOString();

  try {
    const response = await fetch('/api/draft-waves/admin/configs', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        year: year,
        close_date: closeDate
      })
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to create config');
    }

    showAlert('waveDraftAlert', 'Configuration created successfully!', 'success');
    closeCreateConfigModal();
    await loadConfigs();

  } catch (error) {
    console.error('Error creating config:', error);
    showAlert('waveDraftAlert', 'Failed to create configuration: ' + error.message, 'error');
  }
}

// ===== Add Wave =====

function showAddWaveModal() {
  if (!currentConfigId) {
    showAlert('waveDraftAlert', 'No active configuration', 'error');
    return;
  }

  // Populate faculty checkboxes
  const container = document.getElementById('facultyCheckboxes');

  if (waveDraftAllFaculty.length === 0) {
    container.innerHTML = '<p style="color: #6b7280;">No faculty available</p>';
  } else {
    let html = '';
    waveDraftAllFaculty.forEach(faculty => {
      if (faculty.active && !faculty.draft_exempt) {
        html +=
          '<div class="faculty-checkbox-item">' +
          '<label style="display: flex; align-items: center; cursor: pointer;">' +
          '<input type="checkbox" name="facultySelect" value="' + faculty.id + '">' +
          '<span><strong>' + faculty.name + '</strong> (' + faculty.id + ')</span>' +
          '</label>' +
          '</div>';
      }
    });
    container.innerHTML = html;
  }

  document.getElementById('addWaveModal').classList.add('show');
}

function closeAddWaveModal() {
  document.getElementById('addWaveModal').classList.remove('show');
  document.getElementById('addWaveForm').reset();
}

async function submitAddWave(event) {
  event.preventDefault();

  const name = document.getElementById('waveName').value.trim();
  const openDateStr = document.getElementById('waveOpenDate').value;

  if (!openDateStr) {
    showAlert('waveDraftAlert', 'Please select an open date and time', 'error');
    return;
  }

  const openDate = new Date(openDateStr).toISOString();

  // Get selected faculty
  const checkboxes = document.querySelectorAll('input[name="facultySelect"]:checked');
  const facultyIds = Array.from(checkboxes).map(cb => cb.value);

  if (facultyIds.length === 0) {
    showAlert('waveDraftAlert', 'Please select at least one faculty member', 'error');
    return;
  }

  try {
    const response = await fetch(`/api/draft-waves/admin/configs/${currentConfigId}/waves`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: name,
        open_date: openDate,
        faculty_ids: facultyIds
      })
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to create wave');
    }

    showAlert('waveDraftAlert', `Wave "${name}" created with ${facultyIds.length} faculty members!`, 'success');
    closeAddWaveModal();
    await loadWaves(currentConfigId);

  } catch (error) {
    console.error('Error creating wave:', error);
    showAlert('waveDraftAlert', 'Failed to create wave: ' + error.message, 'error');
  }
}

// ===== Activate Config =====

async function activateConfig() {
  if (!currentConfigId) return;

  if (!confirm('Activate Wave Draft?\n\nThis will:\n• Initialize week capacity tracking\n• Send email notifications to waves that should already be open\n• Lock the configuration (no more waves can be added)\n\nContinue?')) {
    return;
  }

  try {
    const response = await fetch(`/api/draft-waves/admin/configs/${currentConfigId}/activate`, {
      method: 'POST',
      credentials: 'same-origin'
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to activate');
    }

    const result = await response.json();

    showAlert('waveDraftAlert', `Draft activated! ${result.notifications_sent} email(s) sent.`, 'success');
    await loadConfigs();

  } catch (error) {
    console.error('Error activating config:', error);
    showAlert('waveDraftAlert', 'Failed to activate: ' + error.message, 'error');
  }
}

// ===== Reset to Pending =====

async function resetToPending() {
  if (!currentConfigId) return;

  if (!confirm('Reset Draft to Pending?\n\nThis will:\n• Pause the active draft\n• Let you add more waves\n• Clear week capacity tracking (rebuilt accurately on re-activate)\n• Preserve all submitted requests\n\nFaculty who have already submitted will NOT be re-emailed.\nFaculty who haven\'t submitted yet will get a fresh notification on re-activate.\n\nContinue?')) {
    return;
  }

  try {
    const response = await fetch(`/api/draft-waves/admin/configs/${currentConfigId}/reset-to-pending`, {
      method: 'POST',
      credentials: 'same-origin'
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to reset config');
    }

    showAlert('waveDraftAlert', 'Draft reset to pending. Add your waves, then click Activate when ready.', 'success');
    await loadConfigs();

  } catch (error) {
    console.error('Error resetting config:', error);
    showAlert('waveDraftAlert', 'Failed to reset: ' + error.message, 'error');
  }
}


// ===== Notify Due Waves =====

async function notifyDueWaves() {
  if (!currentConfigId) return;

  try {
    const response = await fetch(`/api/draft-waves/admin/configs/${currentConfigId}/notify-due-waves`, {
      method: 'POST',
      credentials: 'same-origin'
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to send notifications');
    }

    const result = await response.json();

    const totalSent = result.total_sent ?? result.notifications_sent ?? 0;
    const initialSent = result.initial_notifications_sent ?? 0;
    const remindersSent = result.reminder_notifications_sent ?? 0;

    if (totalSent === 0) {
      showAlert('waveDraftAlert', 'No new notifications to send (all due waves already notified, no reminders due)', 'info');
    } else {
      let msg = `Sent ${totalSent} email(s):`;
      if (initialSent > 0) msg += ` ${initialSent} initial notification(s)`;
      if (remindersSent > 0) msg += `${initialSent > 0 ? ',' : ''} ${remindersSent} 48-hour reminder(s)`;
      showAlert('waveDraftAlert', msg, 'success');
    }

  } catch (error) {
    console.error('Error sending notifications:', error);
    showAlert('waveDraftAlert', 'Failed to send notifications: ' + error.message, 'error');
  }
}

// ===== View Week Capacity =====

async function viewWeekCapacity() {
  if (!currentConfigId) return;

  document.getElementById('weekCapacityModal').classList.add('show');
  document.getElementById('weekCapacityContent').innerHTML = '<p style="color: #6b7280; text-align: center; padding: 40px;">Loading capacity data...</p>';

  try {
    const response = await fetch('/api/draft-waves/week-status', {
      credentials: 'same-origin'
    });

    if (!response.ok) throw new Error('Failed to load week status');

    const weeks = await response.json();

    displayWeekCapacity(weeks);

  } catch (error) {
    console.error('Error loading week capacity:', error);
    document.getElementById('weekCapacityContent').innerHTML =
      '<p style="color: #ef4444; text-align: center; padding: 20px;">Failed to load: ' + error.message + '</p>';
  }
}

function displayWeekCapacity(weeks) {
  const container = document.getElementById('weekCapacityContent');

  let html = '<div class="table-container"><table class="data-table">' +
             '<thead><tr>' +
             '<th>Week</th>' +
             '<th>Dates</th>' +
             '<th>Unavailable</th>' +
             '<th>Volunteer</th>' +
             '<th>Status</th>' +
             '</tr></thead><tbody>';

  weeks.forEach(week => {
    const unavailablePercent = (week.unavailable_count / 12) * 100;
    const volunteerPercent = (week.volunteer_count / 6) * 100;

    let statusBadge = '<span style="color: #10b981;">✓ Open</span>';
    if (week.unavailable_locked || week.volunteer_locked) {
      statusBadge = '<span style="color: #ef4444;">⚠ Capacity Reached</span>';
    } else if (unavailablePercent > 75 || volunteerPercent > 75) {
      statusBadge = '<span style="color: #f59e0b;">⚠ Nearly Full</span>';
    }

    html += '<tr>' +
            '<td style="font-weight: 600;">Week ' + week.week_number + '</td>' +
            '<td style="font-size: 13px;">' + week.start_date + ' to ' + week.end_date + '</td>' +
            '<td>' +
            '<div style="font-weight: 600; margin-bottom: 4px;">' + week.unavailable_count + ' / 12</div>' +
            '<div style="background: #e5e7eb; height: 6px; border-radius: 3px; overflow: hidden;">' +
            '<div style="background: #ef4444; height: 100%; width: ' + unavailablePercent + '%;"></div>' +
            '</div>' +
            '</td>' +
            '<td>' +
            '<div style="font-weight: 600; margin-bottom: 4px;">' + week.volunteer_count + ' / 6</div>' +
            '<div style="background: #e5e7eb; height: 6px; border-radius: 3px; overflow: hidden;">' +
            '<div style="background: #10b981; height: 100%; width: ' + volunteerPercent + '%;"></div>' +
            '</div>' +
            '</td>' +
            '<td>' + statusBadge + '</td>' +
            '</tr>';
  });

  html += '</tbody></table></div>';

  container.innerHTML = html;
}

function closeWeekCapacityModal() {
  document.getElementById('weekCapacityModal').classList.remove('show');
}

// ===== Delete Wave =====

async function deleteWave(waveId, waveName) {
  if (!confirm(`Delete Wave: "${waveName}"?\n\nThis will remove the wave and unassign all faculty members.\n\nThis action cannot be undone.`)) {
    return;
  }

  try {
    const response = await fetch(`/api/draft-waves/admin/waves/${waveId}`, {
      method: 'DELETE',
      credentials: 'same-origin'
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to delete wave');
    }

    showAlert('waveDraftAlert', `Wave "${waveName}" deleted successfully`, 'success');
    await loadWaves(currentConfigId);

  } catch (error) {
    console.error('Error deleting wave:', error);
    showAlert('waveDraftAlert', 'Failed to delete wave: ' + error.message, 'error');
  }
}

// ===== Global Exports =====

window.loadConfigs = loadConfigs;
window.showCreateConfigModal = showCreateConfigModal;
window.closeCreateConfigModal = closeCreateConfigModal;
window.submitCreateConfig = submitCreateConfig;
window.showAddWaveModal = showAddWaveModal;
window.closeAddWaveModal = closeAddWaveModal;
window.submitAddWave = submitAddWave;
window.activateConfig = activateConfig;
window.resetToPending = resetToPending;
window.notifyDueWaves = notifyDueWaves;
window.viewWeekCapacity = viewWeekCapacity;
window.closeWeekCapacityModal = closeWeekCapacityModal;
window.deleteWave = deleteWave;
