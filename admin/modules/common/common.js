/**
 * Common Utilities for Admin Modules
 * Shared functions used across all admin modules
 */

// ==================== DATE FORMATTING ====================

function formatDate(dateString) {
  if (!dateString) return 'N/A';
  const date = new Date(dateString);
  return date.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric'
  });
}

function formatDateTime(dateString) {
  if (!dateString) return 'N/A';
  const date = new Date(dateString);
  return date.toLocaleString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  });
}

function formatMonthYear(year, month) {
  const date = new Date(year, month - 1, 1);
  return date.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long'
  });
}

// ==================== STRING UTILITIES ====================

function truncate(str, maxLength) {
  if (!str || str.length <= maxLength) return str;
  return str.substring(0, maxLength) + '...';
}

function capitalize(str) {
  if (!str) return '';
  return str.charAt(0).toUpperCase() + str.slice(1).toLowerCase();
}

function slugify(str) {
  return str
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '');
}

// ==================== NUMBER FORMATTING ====================

function formatNumber(num) {
  if (num === null || num === undefined) return '0';
  return num.toLocaleString('en-US');
}

function formatPercentage(value, total) {
  if (!total || total === 0) return '0%';
  return Math.round((value / total) * 100) + '%';
}

// ==================== ARRAY UTILITIES ====================

function groupBy(array, key) {
  return array.reduce(function(result, item) {
    const groupKey = item[key];
    if (!result[groupKey]) {
      result[groupKey] = [];
    }
    result[groupKey].push(item);
    return result;
  }, {});
}

function sortBy(array, key, ascending) {
  return array.sort(function(a, b) {
    const aVal = a[key];
    const bVal = b[key];

    if (aVal < bVal) return ascending ? -1 : 1;
    if (aVal > bVal) return ascending ? 1 : -1;
    return 0;
  });
}

function uniqueValues(array, key) {
  const values = array.map(function(item) { return item[key]; });
  return Array.from(new Set(values));
}

// ==================== DOM UTILITIES ====================

function createElement(tag, className, content) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (content) element.textContent = content;
  return element;
}

function clearElement(element) {
  if (typeof element === 'string') {
    element = document.getElementById(element);
  }
  if (element) {
    element.innerHTML = '';
  }
}

function showElement(element, display) {
  if (typeof element === 'string') {
    element = document.getElementById(element);
  }
  if (element) {
    element.style.display = display || 'block';
  }
}

function hideElement(element) {
  if (typeof element === 'string') {
    element = document.getElementById(element);
  }
  if (element) {
    element.style.display = 'none';
  }
}

// ==================== VALIDATION ====================

function isValidEmail(email) {
  const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return re.test(email);
}

function isValidYear(year) {
  const yearNum = parseInt(year);
  return yearNum >= 2000 && yearNum <= 2100;
}

function isEmpty(value) {
  return value === null || value === undefined || value === '';
}

// ==================== LOCAL STORAGE ====================

function saveToStorage(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
    return true;
  } catch (e) {
    console.error('Failed to save to storage:', e);
    return false;
  }
}

function loadFromStorage(key, defaultValue) {
  try {
    const value = localStorage.getItem(key);
    return value ? JSON.parse(value) : defaultValue;
  } catch (e) {
    console.error('Failed to load from storage:', e);
    return defaultValue;
  }
}

function removeFromStorage(key) {
  try {
    localStorage.removeItem(key);
  } catch (e) {
    console.error('Failed to remove from storage:', e);
  }
}

// ==================== CSV EXPORT ====================

function exportToCSV(data, filename) {
  if (!data || data.length === 0) {
    alert('No data to export');
    return;
  }

  // Get headers from first object
  const headers = Object.keys(data[0]);

  // Build CSV content
  let csv = headers.join(',') + '\n';

  data.forEach(function(row) {
    const values = headers.map(function(header) {
      const value = row[header];
      // Escape values with commas or quotes
      if (value === null || value === undefined) return '';
      const stringValue = String(value);
      if (stringValue.includes(',') || stringValue.includes('"')) {
        return '"' + stringValue.replace(/"/g, '""') + '"';
      }
      return stringValue;
    });
    csv += values.join(',') + '\n';
  });

  // Create download
  const blob = new Blob([csv], { type: 'text/csv' });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename || 'export.csv';
  link.click();
  window.URL.revokeObjectURL(url);
}

// ==================== DEBOUNCE ====================

function debounce(func, wait) {
  let timeout;
  return function executedFunction() {
    const context = this;
    const args = arguments;
    const later = function() {
      timeout = null;
      func.apply(context, args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

// ==================== CONFIRMATION ====================

function confirmAction(message, callback) {
  if (confirm(message)) {
    callback();
  }
}

function confirmDeletion(itemName, count, callback) {
  const message = count > 1
    ? 'Delete ' + count + ' ' + itemName + 's? This cannot be undone.'
    : 'Delete this ' + itemName + '? This cannot be undone.';

  confirmAction(message, callback);
}
