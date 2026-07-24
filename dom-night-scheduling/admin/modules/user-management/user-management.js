/**
 * User Management Module
 * Search, password reset, unlock, username change, database queries, service weeks
 */

let userMgmtCurrentYear = new Date().getFullYear();
let currentUserDetails = null;

// Initialize module
function initUserManagement() {
  console.log('User Management module initialized');

  // Add enter key listeners
  const searchInput = document.getElementById('umSearchQuery');
  if (searchInput) {
    searchInput.addEventListener('keypress', function(e) {
      if (e.key === 'Enter') searchUsers();
    });
  }

  // Auto-load all users on open
  searchUsers();
}

// Tab switching
function showUserMgmtTab(tabName) {
  // Hide all tabs
  const tabs = document.querySelectorAll('.um-tab-content');
  tabs.forEach(tab => tab.classList.remove('active'));

  // Hide all tab buttons active state
  const tabBtns = document.querySelectorAll('.um-tab-btn');
  tabBtns.forEach(btn => btn.classList.remove('active'));

  // Show selected tab
  const selectedTab = document.getElementById('um-tab-' + tabName);
  if (selectedTab) {
    selectedTab.classList.add('active');
  }

  // Activate button
  const buttons = document.querySelectorAll('.um-tab-btn');
  buttons.forEach(btn => {
    if (btn.textContent.toLowerCase().includes(tabName) ||
        (tabName === 'query' && btn.textContent.includes('Query'))) {
      btn.classList.add('active');
    }
  });

  // Clear alerts when switching tabs
  clearAllUserMgmtAlerts();
}

// Clear all alerts
function clearAllUserMgmtAlerts() {
  const alertIds = ['umSearchAlert', 'umResetAlert', 'umUnlockAlert', 'umUsernameAlert', 'umQueryAlert'];
  alertIds.forEach(id => {
    const alert = document.getElementById(id);
    if (alert) {
      alert.className = 'alert';
      alert.textContent = '';
    }
  });
}

// Show alert
function showUserMgmtAlert(elementId, message, type) {
  const alert = document.getElementById(elementId);
  if (!alert) return;

  alert.className = 'alert show';

  if (type === 'success') {
    alert.classList.add('alert-success');
  } else if (type === 'error') {
    alert.classList.add('alert-error');
  } else if (type === 'info') {
    alert.classList.add('alert-info');
  } else {
    alert.className = 'alert';
  }

  alert.textContent = message;

  // Auto-hide after 5 seconds for success messages
  if (type === 'success') {
    setTimeout(() => {
      alert.className = 'alert';
      alert.textContent = '';
    }, 5000);
  }
}

// Search users
async function searchUsers() {
  const query = document.getElementById('umSearchQuery').value.trim();
  const resultsDiv = document.getElementById('umSearchResults');

  showUserMgmtAlert('umSearchAlert', '', 'clear');
  resultsDiv.innerHTML = '<div class="loading">Searching...</div>';

  try {
    const response = await fetch('/api/admin/faculty', {
      credentials: 'same-origin'
    });

    if (!response.ok) {
      throw new Error('Failed to fetch users');
    }

    let users = await response.json();
    users = Array.isArray(users) ? users : (users.faculty || []);

    // Filter by query if provided
    if (query) {
      const queryLower = query.toLowerCase();
      users = users.filter(u =>
        (u.id && u.id.toLowerCase().includes(queryLower)) ||
        (u.name && u.name.toLowerCase().includes(queryLower)) ||
        (u.email && u.email.toLowerCase().includes(queryLower))
      );
    }

    if (users.length === 0) {
      resultsDiv.innerHTML = '<div class="loading">No users found</div>';
      return;
    }

    // Render user cards
    resultsDiv.innerHTML = '';
    users.forEach(user => {
      const card = document.createElement('div');
      card.className = 'user-card';
      card.onclick = () => viewUserDetails(user.id);

      // Build badges
      let badges = '';
      if (user.is_admin) {
        badges += '<span class="badge badge-info">Admin</span>';
      }
      if (user.active) {
        badges += '<span class="badge badge-success">Active</span>';
      } else {
        badges += '<span class="badge badge-danger">Inactive</span>';
      }
      if (user.locked) {
        badges += '<span class="badge badge-warning">🔒 Locked</span>';
      }
      if (user.moonlighter) {
        badges += '<span class="badge badge-warning">🌙 Moonlighter</span>';
      }

      const totalPoints = (user.base_points || 0) + (user.bonus_points || 0);

      card.innerHTML = `
        <div class="user-card-header">
          <div>
            <div class="user-card-id">${user.name || 'No name set'}</div>
            <div class="user-card-name" style="font-size: 12px; color: #9ca3af; margin-top: 2px; font-family: monospace;">${user.id || 'N/A'}</div>
          </div>
          <div style="display: flex; align-items: center; gap: 8px;">
            <div class="user-card-badges">${badges}</div>
            <button class="btn-primary btn-sm" onclick="event.stopPropagation(); editUserFromHere('${user.id}')" style="white-space: nowrap;">✏️ Edit</button>
          </div>
        </div>
        <div class="user-card-details" style="margin-top: 8px; flex-wrap: wrap; gap: 8px;">
          <span>📧 ${user.email || 'No email'}</span>
          <span title="Base + Bonus points">📊 Points: ${totalPoints}</span>
          <span>MICU: ${user.micu_weeks || 0}</span>
          <span>APP-ICU: ${user.app_icu_weeks || 0}</span>
          <span>Procedures: ${user.procedure_weeks || 0}</span>
          <span>Consults: ${user.consult_weeks || 0}</span>
          <span>Backup: ${user.backup_weeks || 0}</span>
        </div>
      `;

      resultsDiv.appendChild(card);
    });

    showUserMgmtAlert('umSearchAlert', `Found ${users.length} user(s)`, 'info');

  } catch (error) {
    console.error('Error searching users:', error);
    resultsDiv.innerHTML = '';
    showUserMgmtAlert('umSearchAlert', 'Error: ' + error.message, 'error');
  }
}

// View user details with service weeks
async function viewUserDetails(facultyId) {
  currentUserDetails = facultyId;

  const modal = document.getElementById('userDetailsModal');
  const content = document.getElementById('userDetailsContent');

  modal.classList.add('show');
  content.innerHTML = '<div class="loading">Loading user details...</div>';

  try {
    // Fetch user details
    const userResponse = await fetch(`/api/admin/faculty`, {
      credentials: 'same-origin'
    });

    if (!userResponse.ok) throw new Error('Failed to fetch user');

    let users = await userResponse.json();
    users = Array.isArray(users) ? users : (users.faculty || []);
    const user = users.find(u => u.id === facultyId);

    if (!user) {
      content.innerHTML = '<div class="alert alert-error">User not found</div>';
      return;
    }

    // Fetch service weeks for current year
    let serviceWeeks = [];
    try {
      const weeksResponse = await fetch(`/api/admin/faculty/${facultyId}/service-weeks?year=${userMgmtCurrentYear}`, {
        credentials: 'same-origin'
      });

      if (weeksResponse.ok) {
        serviceWeeks = await weeksResponse.json();
      }
    } catch (err) {
      console.warn('Could not load service weeks:', err);
    }

    // Render user details
    let html = `
      <div class="detail-grid">
        <div class="detail-item">
          <div class="detail-label">Faculty ID</div>
          <div class="detail-value">${user.id || 'N/A'}</div>
        </div>
        <div class="detail-item">
          <div class="detail-label">Name</div>
          <div class="detail-value">${user.name || 'N/A'}</div>
        </div>
        <div class="detail-item">
          <div class="detail-label">Email</div>
          <div class="detail-value">${user.email || 'N/A'}</div>
        </div>
        <div class="detail-item">
          <div class="detail-label">Rank</div>
          <div class="detail-value">${user.rank || 'Not set'}</div>
        </div>
        <div class="detail-item">
          <div class="detail-label">Effort %</div>
          <div class="detail-value">${user.clinical_effort_pct || 0}%</div>
        </div>
        <div class="detail-item">
          <div class="detail-label">Bonus Points</div>
          <div class="detail-value">${user.bonus_points || 0}</div>
        </div>
        <div class="detail-item">
          <div class="detail-label">Status</div>
          <div class="detail-value">
            ${user.active ? '<span class="badge badge-success">Active</span>' : '<span class="badge badge-danger">Inactive</span>'}
            ${user.locked ? '<span class="badge badge-warning">🔒 Locked</span>' : ''}
          </div>
        </div>
        <div class="detail-item">
          <div class="detail-label">Privileges</div>
          <div class="detail-value">
            ${user.is_admin ? '<span class="badge badge-info">Admin</span>' : ''}
            ${user.moonlighter ? '<span class="badge badge-warning">🌙 Moonlighter</span>' : ''}
          </div>
        </div>
      </div>

      <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 20px 0;">
        <div style="background: #fee2e2; padding: 12px; border-radius: 8px; text-align: center;">
          <div style="font-size: 24px; font-weight: 700; color: #991b1b;">${user.micu_weeks || 0}</div>
          <div style="font-size: 12px; color: #6b7280; margin-top: 4px;">MICU Weeks</div>
        </div>
        <div style="background: #fed7aa; padding: 12px; border-radius: 8px; text-align: center;">
          <div style="font-size: 24px; font-weight: 700; color: #92400e;">${user.app_icu_weeks || 0}</div>
          <div style="font-size: 12px; color: #6b7280; margin-top: 4px;">APP-ICU Weeks</div>
        </div>
        <div style="background: #d1fae5; padding: 12px; border-radius: 8px; text-align: center;">
          <div style="font-size: 24px; font-weight: 700; color: #065f46;">${user.procedure_weeks || 0}</div>
          <div style="font-size: 12px; color: #6b7280; margin-top: 4px;">Procedures</div>
        </div>
        <div style="background: #dbeafe; padding: 12px; border-radius: 8px; text-align: center;">
          <div style="font-size: 24px; font-weight: 700; color: #1e40af;">${user.consult_weeks || 0}</div>
          <div style="font-size: 12px; color: #6b7280; margin-top: 4px;">Consults</div>
        </div>
      </div>
    `;

    // Add service weeks section
    if (serviceWeeks.length > 0) {
      html += `
        <div class="service-weeks-section">
          <div class="service-weeks-header">
            <h3 class="service-weeks-title">📅 Service Weeks ${userMgmtCurrentYear}</h3>
            <span style="color: #6b7280; font-size: 14px;">${serviceWeeks.length} assignments</span>
          </div>
      `;

      serviceWeeks.forEach(week => {
        const serviceClass = 'service-week-' + week.service_type.toLowerCase().replace('_', '-');
        html += `
          <div class="service-week-item ${serviceClass}">
            <div class="service-week-info">
              <div class="service-week-label">
                Week ${week.week_number}: ${week.service_type}
                <span style="color: #6b7280; font-weight: 400; margin-left: 8px;">${week.points_value} pts</span>
              </div>
              <div class="service-week-dates">${week.start_date} to ${week.end_date}</div>
            </div>
          </div>
        `;
      });

      html += '</div>';
    } else {
      html += `
        <div style="background: #f9fafb; padding: 20px; border-radius: 8px; text-align: center; color: #6b7280; margin-top: 20px;">
          <div style="font-size: 48px; margin-bottom: 12px;">📅</div>
          <div style="font-weight: 600; margin-bottom: 4px;">No Service Weeks Assigned</div>
          <div style="font-size: 14px;">This faculty member has no service weeks for ${userMgmtCurrentYear}</div>
        </div>
      `;
    }

    content.innerHTML = html;

  } catch (error) {
    console.error('Error loading user details:', error);
    content.innerHTML = `<div class="alert alert-error">Error: ${error.message}</div>`;
  }
}

// Close user details modal
function closeUserDetailsModal() {
  const modal = document.getElementById('userDetailsModal');
  modal.classList.remove('show');
  currentUserDetails = null;
}

// Reset password
async function resetUserPassword() {
  const facultyId = document.getElementById('umResetFacultyId').value.trim();

  if (!facultyId) {
    showUserMgmtAlert('umResetAlert', 'Please enter a faculty ID', 'error');
    return;
  }

  if (!confirm(`Reset password for ${facultyId} to PCCM2025! ?`)) {
    return;
  }

  try {
    const response = await fetch('/api/admin/users/reset-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ faculty_id: facultyId })
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to reset password');
    }

    showUserMgmtAlert('umResetAlert', `✅ Password reset successfully for ${facultyId}`, 'success');
    document.getElementById('umResetFacultyId').value = '';

  } catch (error) {
    console.error('Error resetting password:', error);
    showUserMgmtAlert('umResetAlert', 'Error: ' + error.message, 'error');
  }
}

// Unlock account
async function unlockUserAccount() {
  const facultyId = document.getElementById('umUnlockFacultyId').value.trim();

  if (!facultyId) {
    showUserMgmtAlert('umUnlockAlert', 'Please enter a faculty ID', 'error');
    return;
  }

  if (!confirm(`Unlock account for ${facultyId}?`)) {
    return;
  }

  try {
    const response = await fetch('/api/admin/users/unlock-account', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ faculty_id: facultyId })
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to unlock account');
    }

    showUserMgmtAlert('umUnlockAlert', `✅ Account unlocked successfully for ${facultyId}`, 'success');
    document.getElementById('umUnlockFacultyId').value = '';

  } catch (error) {
    console.error('Error unlocking account:', error);
    showUserMgmtAlert('umUnlockAlert', 'Error: ' + error.message, 'error');
  }
}

// Change username
async function changeUsername() {
  const oldId = document.getElementById('umOldFacultyId').value.trim();
  const newId = document.getElementById('umNewFacultyId').value.trim();

  if (!oldId || !newId) {
    showUserMgmtAlert('umUsernameAlert', 'Please enter both old and new faculty IDs', 'error');
    return;
  }

  if (!confirm(`⚠️ PERMANENT CHANGE\n\nChange username from ${oldId} to ${newId}?\n\nThis will update the user's login ID across the entire system.`)) {
    return;
  }

  try {
    const response = await fetch('/api/admin/users/change-username', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ old_faculty_id: oldId, new_faculty_id: newId })
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to change username');
    }

    showUserMgmtAlert('umUsernameAlert', `✅ Username changed from ${oldId} to ${newId}`, 'success');
    document.getElementById('umOldFacultyId').value = '';
    document.getElementById('umNewFacultyId').value = '';

  } catch (error) {
    console.error('Error changing username:', error);
    showUserMgmtAlert('umUsernameAlert', 'Error: ' + error.message, 'error');
  }
}

// Execute database query
async function executeQuery() {
  const sql = document.getElementById('umQuerySql').value.trim();
  const resultsDiv = document.getElementById('umQueryResults');

  if (!sql) {
    showUserMgmtAlert('umQueryAlert', 'Please enter a SQL query', 'error');
    return;
  }

  if (!confirm('⚠️ Execute this database query?\n\n' + sql)) {
    return;
  }

  showUserMgmtAlert('umQueryAlert', '', 'clear');
  resultsDiv.innerHTML = '<div class="loading">Executing query...</div>';

  try {
    const response = await fetch('/api/admin/users/database-query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ query: sql })
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Query failed');
    }

    const result = await response.json();

    if (result.rows && result.rows.length > 0) {
      // Render results table
      const columns = result.columns || Object.keys(result.rows[0]);

      let html = `
        <div style="margin-bottom: 12px; color: #6b7280;">
          Query returned ${result.rows.length} row(s)
        </div>
        <div style="overflow-x: auto;">
          <table class="query-results-table">
            <thead>
              <tr>${columns.map(col => `<th>${col}</th>`).join('')}</tr>
            </thead>
            <tbody>
      `;

      result.rows.forEach(row => {
        html += '<tr>';
        columns.forEach(col => {
          const value = row[col];
          html += `<td>${value !== null && value !== undefined ? value : '<span style="color: #9ca3af;">NULL</span>'}</td>`;
        });
        html += '</tr>';
      });

      html += '</tbody></table></div>';
      resultsDiv.innerHTML = html;
      showUserMgmtAlert('umQueryAlert', '✅ Query executed successfully', 'success');

    } else {
      resultsDiv.innerHTML = '<div class="loading">Query executed successfully (0 rows returned)</div>';
      showUserMgmtAlert('umQueryAlert', '✅ Query executed (0 rows)', 'info');
    }

  } catch (error) {
    console.error('Error executing query:', error);
    resultsDiv.innerHTML = '';
    showUserMgmtAlert('umQueryAlert', 'Error: ' + error.message, 'error');
  }
}

// Clear query
function clearQuery() {
  document.getElementById('umQuerySql').value = '';
  document.getElementById('umQueryResults').innerHTML = '';
  showUserMgmtAlert('umQueryAlert', '', 'clear');
}

// Navigate to Faculty Management tab and open the edit modal for this user
async function editUserFromHere(facultyId) {
  // Switch to the faculty-management module (loads its JS + HTML)
  if (typeof showModule === 'function') {
    await showModule('faculty-management');
  }
  // Wait a tick for the module to finish loading, then open the modal
  setTimeout(function() {
    if (typeof openEditFaculty === 'function') {
      openEditFaculty(facultyId);
    }
  }, 300);
}

// ==================== GLOBAL FUNCTION EXPORTS ====================
// Make functions globally accessible for inline onclick handlers

window.showUserMgmtTab = showUserMgmtTab;
window.searchUsers = searchUsers;
window.viewUserDetails = viewUserDetails;
window.closeUserDetailsModal = closeUserDetailsModal;
window.resetUserPassword = resetUserPassword;
window.unlockUserAccount = unlockUserAccount;
window.changeUsername = changeUsername;
window.executeQuery = executeQuery;
window.clearQuery = clearQuery;
window.initUserManagement = initUserManagement;
window.editUserFromHere = editUserFromHere;

// Close modal on background click
window.addEventListener('click', function(event) {
  const modal = document.getElementById('userDetailsModal');
  if (event.target === modal) {
    closeUserDetailsModal();
  }
});
