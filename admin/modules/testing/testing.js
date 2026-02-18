/**
 * Enhanced Testing Tools Module
 * Separate controls for service weeks vs moonlighting
 */

async function resetPoints() {
  const confirmed = confirm(
    '⚠️ RESET ALL FACULTY BONUS POINTS?\n\n' +
    'This will reset bonus_points to 0 for all faculty.\n' +
    'Base points will remain intact.\n\n' +
    'Continue?'
  );

  if (!confirmed) return;

  try {
    showTestingAlert('Resetting points...', 'info');

    const response = await fetch('/api/admin/testing/reset-points', {
      method: 'POST',
      credentials: 'same-origin'
    });

    if (!response.ok) throw new Error('Reset failed');

    const result = await response.json();
    showTestingAlert('✅ Reset ' + result.faculty_count + ' faculty bonus points to 0', 'success');

  } catch (error) {
    showTestingAlert('Error: ' + error.message, 'error');
  }
}

async function clearServiceRequests() {
  const year = document.getElementById('clearServiceYear').value;

  // Get preview count first
  try {
    const previewResponse = await fetch('/api/admin/testing/preview-service-requests?year=' + year, {
      credentials: 'same-origin'
    });
    const preview = await previewResponse.json();

    const confirmed = confirm(
      '⚠️ CLEAR SERVICE AVAILABILITY REQUESTS?\n\n' +
      'This will delete ' + preview.count + ' unavailability requests for SERVICE WEEKS.\n' +
      'Year: ' + (year === 'all' ? 'All' : year) + '\n\n' +
      'Moonlighting signups will NOT be affected.\n\n' +
      'Continue?'
    );

    if (!confirmed) return;

    showTestingAlert('Clearing service requests...', 'info');

    const response = await fetch('/api/admin/testing/clear-service-requests', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ year: year })
    });

    if (!response.ok) throw new Error('Clear failed');

    const result = await response.json();
    showTestingAlert('✅ Deleted ' + result.deleted_count + ' service availability requests', 'success');

  } catch (error) {
    showTestingAlert('Error: ' + error.message, 'error');
  }
}

async function clearMoonlightingSignups() {
  const month = document.getElementById('clearMoonlightMonth').value;

  // Get preview count first
  try {
    const previewResponse = await fetch('/api/admin/testing/preview-moonlighting?month=' + month, {
      credentials: 'same-origin'
    });
    const preview = await previewResponse.json();

    const confirmed = confirm(
      '⚠️ CLEAR MOONLIGHTING SIGNUPS?\n\n' +
      'This will delete ' + preview.count + ' moonlighting signups.\n' +
      'Filter: ' + (month === 'all' ? 'All Months' : month) + '\n\n' +
      'Service availability requests will NOT be affected.\n\n' +
      'Continue?'
    );

    if (!confirmed) return;

    showTestingAlert('Clearing moonlighting signups...', 'info');

    const response = await fetch('/api/admin/testing/clear-moonlighting', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ month: month })
    });

    if (!response.ok) throw new Error('Clear failed');

    const result = await response.json();
    showTestingAlert('✅ Deleted ' + result.deleted_count + ' moonlighting signups', 'success');

  } catch (error) {
    showTestingAlert('Error: ' + error.message, 'error');
  }
}

async function clearServiceAssignments() {
  const year = document.getElementById('clearAssignmentsYear').value;

  // Get preview count first
  try {
    const previewResponse = await fetch('/api/admin/testing/preview-assignments?year=' + year, {
      credentials: 'same-origin'
    });
    const preview = await previewResponse.json();

    const confirmed = confirm(
      '⚠️ CLEAR SERVICE WEEK ASSIGNMENTS?\n\n' +
      'This will delete ' + preview.count + ' generated service assignments.\n' +
      'Year: ' + year + '\n\n' +
      'This clears the GENERATED SCHEDULE (MICU, APP-ICU, etc).\n' +
      'Unavailability requests will NOT be deleted.\n\n' +
      'Continue?'
    );

    if (!confirmed) return;

    showTestingAlert('Clearing service assignments...', 'info');

    const response = await fetch('/api/admin/testing/clear-assignments', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ year: year })
    });

    if (!response.ok) throw new Error('Clear failed');

    const result = await response.json();
    showTestingAlert('✅ Deleted ' + result.deleted_count + ' service week assignments', 'success');

  } catch (error) {
    showTestingAlert('Error: ' + error.message, 'error');
  }
}

async function resetAll() {
  const year = document.getElementById('resetAllYear').value;

  const confirmed = confirm(
    '💣 COMPLETE RESET - ARE YOU SURE?\n\n' +
    'This will:\n' +
    '• Reset all faculty bonus points to 0\n' +
    '• Delete all service availability requests\n' +
    '• Delete all moonlighting signups\n' +
    '• Delete all service week assignments\n\n' +
    'Year: ' + (year === 'all' ? 'ALL YEARS' : year) + '\n\n' +
    'This action cannot be undone. Continue?'
  );

  if (!confirmed) return;

  const doubleCheck = prompt('Type "RESET" to confirm complete reset:');
  if (doubleCheck !== 'RESET') {
    showTestingAlert('Reset cancelled', 'info');
    return;
  }

  try {
    showTestingAlert('Performing complete reset...', 'info');

    const response = await fetch('/api/admin/testing/reset-all', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ year: year })
    });

    if (!response.ok) throw new Error('Reset failed');

    const result = await response.json();
    showTestingAlert(
      '✅ Complete reset finished:\n' +
      '• ' + result.points_reset + ' faculty points reset\n' +
      '• ' + result.requests_deleted + ' service requests deleted\n' +
      '• ' + result.signups_deleted + ' moonlighting signups deleted\n' +
      '• ' + result.assignments_deleted + ' assignments deleted',
      'success'
    );

  } catch (error) {
    showTestingAlert('Error: ' + error.message, 'error');
  }
}

function showTestingAlert(message, type) {
  const alert = document.getElementById('testingAlert');
  if (type === 'clear') {
    alert.style.display = 'none';
    return;
  }

  alert.textContent = message;
  alert.className = 'alert alert-' + type;
  alert.style.display = 'block';

  if (type === 'success' || type === 'info') {
    setTimeout(function() { showTestingAlert('', 'clear'); }, 5000);
  }
}

// ==================== GLOBAL FUNCTION EXPORTS ====================
// Make functions globally accessible for inline onclick handlers

window.resetPoints = resetPoints;
window.clearServiceRequests = clearServiceRequests;
window.clearMoonlightingSignups = clearMoonlightingSignups;
window.clearServiceAssignments = clearServiceAssignments;
window.resetAll = resetAll;
