/**
 * API Helper Functions
 * Centralized API communication for admin modules
 */

// ==================== AUTH CHECK ====================

function handleAuthFailure(status) {
  if (status === 401 || status === 403) {
    // Session expired or invalid (e.g. after redeploy) — force re-login
    window.location.href = '/?session_expired=1';
    return true;
  }
  return false;
}

// ==================== BASE API FUNCTIONS ====================

async function apiGet(endpoint) {
  try {
    const response = await fetch(endpoint, {
      method: 'GET',
      credentials: 'same-origin',
      headers: {
        'Accept': 'application/json'
      }
    });

    if (!response.ok) {
      if (handleAuthFailure(response.status)) return;
      const errorText = await response.text();
      throw new Error('API Error: ' + response.status + ' - ' + errorText);
    }

    return await response.json();
  } catch (error) {
    console.error('API GET Error:', error);
    throw error;
  }
}

async function apiPost(endpoint, data) {
  try {
    const response = await fetch(endpoint, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
      body: JSON.stringify(data)
    });

    if (!response.ok) {
      if (handleAuthFailure(response.status)) return;
      const errorText = await response.text();
      throw new Error('API Error: ' + response.status + ' - ' + errorText);
    }

    return await response.json();
  } catch (error) {
    console.error('API POST Error:', error);
    throw error;
  }
}

async function apiPut(endpoint, data) {
  try {
    const response = await fetch(endpoint, {
      method: 'PUT',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
      body: JSON.stringify(data)
    });

    if (!response.ok) {
      if (handleAuthFailure(response.status)) return;
      const errorText = await response.text();
      throw new Error('API Error: ' + response.status + ' - ' + errorText);
    }

    return await response.json();
  } catch (error) {
    console.error('API PUT Error:', error);
    throw error;
  }
}

async function apiDelete(endpoint) {
  try {
    const response = await fetch(endpoint, {
      method: 'DELETE',
      credentials: 'same-origin',
      headers: {
        'Accept': 'application/json'
      }
    });

    if (!response.ok) {
      if (handleAuthFailure(response.status)) return;
      const errorText = await response.text();
      throw new Error('API Error: ' + response.status + ' - ' + errorText);
    }

    return await response.json();
  } catch (error) {
    console.error('API DELETE Error:', error);
    throw error;
  }
}

// ==================== DATA MANAGEMENT APIs ====================

async function getUnavailabilityRequests(filters) {
  const params = new URLSearchParams(filters || {});
  return await apiGet('/api/admin/data-management/unavailability-requests?' + params.toString());
}

async function deleteUnavailabilityRequests(requestIds) {
  return await apiPost('/api/admin/data-management/delete-unavailability', {
    request_ids: requestIds
  });
}

async function getMoonlightingSignups(filters) {
  const params = new URLSearchParams(filters || {});
  return await apiGet('/api/admin/data-management/moonlighting-signups?' + params.toString());
}

async function deleteMoonlightingSignups(signupIds) {
  return await apiPost('/api/admin/data-management/delete-moonlighting', {
    signup_ids: signupIds
  });
}

// ==================== SERVICE WEEK OVERRIDE APIs ====================

async function getBlocks(year) {
  return await apiGet('/api/admin/service-weeks/blocks?year=' + (year || '2026'));
}

async function createBlock(facultyId, weekId, reason) {
  return await apiPost('/api/admin/service-weeks/create-block', {
    faculty_id: facultyId,
    week_id: weekId,
    reason: reason
  });
}

async function deleteBlock(blockId) {
  return await apiDelete('/api/admin/service-weeks/blocks/' + blockId);
}

async function getManualAssignments(year) {
  return await apiGet('/api/admin/service-weeks/manual-assignments?year=' + (year || '2026'));
}

async function createManualAssignment(facultyId, weekId, serviceType, reason) {
  return await apiPost('/api/admin/service-weeks/create-assignment', {
    faculty_id: facultyId,
    week_id: weekId,
    service_type: serviceType,
    reason: reason
  });
}

async function deleteManualAssignment(assignmentId) {
  return await apiDelete('/api/admin/service-weeks/manual-assignments/' + assignmentId);
}

// ==================== TESTING APIs ====================

async function resetBonusPoints() {
  return await apiPost('/api/admin/testing/reset-points', {});
}

async function previewServiceRequests(year) {
  return await apiGet('/api/admin/testing/preview-service-requests?year=' + (year || 'all'));
}

async function clearServiceRequests(year) {
  return await apiPost('/api/admin/testing/clear-service-requests', {
    year: year || 'all'
  });
}

async function previewMoonlightingSignups(month) {
  return await apiGet('/api/admin/testing/preview-moonlighting?month=' + (month || 'all'));
}

async function clearMoonlightingSignups(month) {
  return await apiPost('/api/admin/testing/clear-moonlighting', {
    month: month || 'all'
  });
}

async function previewServiceAssignments(year) {
  return await apiGet('/api/admin/testing/preview-assignments?year=' + year);
}

async function clearServiceAssignments(year) {
  return await apiPost('/api/admin/testing/clear-assignments', {
    year: year
  });
}

async function resetAll(year) {
  return await apiPost('/api/admin/testing/reset-all', {
    year: year || 'all'
  });
}

// ==================== REFERENCE DATA APIs ====================

async function getFaculty() {
  return await apiGet('/api/admin/faculty');
}

async function getServiceWeeks(year) {
  return await apiGet('/api/admin/service-weeks?year=' + (year || '2026'));
}

async function getMonths() {
  return await apiGet('/api/admin/months');
}

async function getProviders() {
  return await apiGet('/api/admin/providers');
}

// ==================== ERROR HANDLING ====================

function handleApiError(error, alertElementId) {
  const message = error.message || 'An unexpected error occurred';

  // Log to console for debugging
  console.error('API Error:', error);

  // Show user-friendly message
  if (alertElementId) {
    showAlert(alertElementId, 'Error: ' + message, 'error');
  } else {
    alert('Error: ' + message);
  }
}

function showAlert(elementId, message, type) {
  const alert = document.getElementById(elementId);
  if (!alert) return;

  if (type === 'clear') {
    alert.style.display = 'none';
    return;
  }

  alert.textContent = message;
  alert.className = 'alert alert-' + type;
  alert.style.display = 'block';

  // Auto-hide success/info messages
  if (type === 'success' || type === 'info') {
    setTimeout(function() {
      showAlert(elementId, '', 'clear');
    }, 5000);
  }
}
