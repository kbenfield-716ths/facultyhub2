/**
 * Database Viewer Module
 * View database tables, schema, and data
 */

let currentTable = null;
let currentOffset = 0;
let currentLimit = 50;
let totalRows = 0;

// Load module on init
document.addEventListener('DOMContentLoaded', function() {
  if (document.getElementById('tablesList')) {
    loadTables();
  }
});

// Load all tables
async function loadTables() {
  try {
    showAlert('dbAlert', '', 'clear');

    const response = await fetch('/api/admin/database/tables', {
      credentials: 'same-origin'
    });

    if (!response.ok) throw new Error('Failed to load tables');

    const data = await response.json();
    renderTablesList(data.tables);

  } catch (error) {
    console.error('Error loading tables:', error);
    showAlert('dbAlert', 'Failed to load tables: ' + error.message, 'error');
  }
}

// Render tables list
function renderTablesList(tables) {
  const container = document.getElementById('tablesList');

  if (!tables || tables.length === 0) {
    container.innerHTML = '<p style="color: #6b7280;">No tables found</p>';
    return;
  }

  let html = '';
  tables.forEach(table => {
    const rowCount = table.row_count !== null ? table.row_count : 'N/A';
    html += '<div class="table-row" onclick="viewTable(\'' + table.name + '\')">' +
              '<div>' +
                '<strong style="color: #1f2937;">' + table.name + '</strong>' +
              '</div>' +
              '<div>' +
                '<span class="table-badge">' + rowCount + ' rows</span>' +
              '</div>' +
            '</div>';
  });

  container.innerHTML = html;
}

// View a specific table
async function viewTable(tableName) {
  try {
    currentTable = tableName;
    currentOffset = 0;
    showAlert('dbAlert', '', 'clear');

    // Load schema and data
    await Promise.all([
      loadTableSchema(tableName),
      loadTableData(tableName, 0)
    ]);

    // Show viewer
    document.getElementById('currentTableName').textContent = tableName;
    document.getElementById('tableViewer').style.display = 'block';

    // Scroll to viewer
    document.getElementById('tableViewer').scrollIntoView({ behavior: 'smooth' });

  } catch (error) {
    console.error('Error viewing table:', error);
    showAlert('dbAlert', 'Failed to load table: ' + error.message, 'error');
  }
}

// Load table schema
async function loadTableSchema(tableName) {
  const response = await fetch('/api/admin/database/tables/' + tableName + '/schema', {
    credentials: 'same-origin'
  });

  if (!response.ok) throw new Error('Failed to load schema');

  const data = await response.json();
  renderTableSchema(data);
}

// Render table schema
function renderTableSchema(schema) {
  const container = document.getElementById('tableSchema');

  let html = '<table class="data-table">' +
             '<thead><tr>' +
             '<th>Column</th>' +
             '<th>Type</th>' +
             '<th>Nullable</th>' +
             '<th>Constraints</th>' +
             '</tr></thead><tbody>';

  schema.columns.forEach(col => {
    const constraints = [];
    if (col.primary_key) constraints.push('PRIMARY KEY');
    if (col.default) constraints.push('DEFAULT: ' + col.default);

    html += '<tr>' +
            '<td style="font-family: monospace; font-weight: 600;">' + col.name + '</td>' +
            '<td style="font-family: monospace; color: #6b7280;">' + col.type + '</td>' +
            '<td style="text-align: center;">' + (col.nullable ? '✓' : '✗') + '</td>' +
            '<td style="font-size: 12px;">' + (constraints.length > 0 ? constraints.join(', ') : '-') + '</td>' +
            '</tr>';
  });

  html += '</tbody></table>';

  // Add additional constraints info
  if (schema.unique_constraints.length > 0) {
    html += '<div style="margin-top: 12px; padding: 12px; background: #fef3c7; border-radius: 6px; font-size: 13px;">' +
            '<strong>Unique Constraints:</strong> ' +
            schema.unique_constraints.map(uc => uc.column_names ? uc.column_names.join(', ') : uc.name).join('; ') +
            '</div>';
  }

  if (schema.foreign_keys.length > 0) {
    html += '<div style="margin-top: 8px; padding: 12px; background: #dbeafe; border-radius: 6px; font-size: 13px;">' +
            '<strong>Foreign Keys:</strong> ';
    schema.foreign_keys.forEach(fk => {
      html += fk.constrained_columns.join(', ') + ' → ' + fk.referred_table + '(' + fk.referred_columns.join(', ') + '); ';
    });
    html += '</div>';
  }

  container.innerHTML = html;
}

// Load table data
async function loadTableData(tableName, offset) {
  const response = await fetch(
    '/api/admin/database/tables/' + tableName + '/data?limit=' + currentLimit + '&offset=' + offset,
    { credentials: 'same-origin' }
  );

  if (!response.ok) throw new Error('Failed to load data');

  const data = await response.json();
  totalRows = data.total_count;
  currentOffset = offset;

  renderTableData(data);
  updatePaginationControls(data);
}

// Render table data
function renderTableData(data) {
  const container = document.getElementById('tableData');

  if (data.rows.length === 0) {
    container.innerHTML = '<p style="padding: 20px; color: #6b7280; text-align: center;">No data in this table</p>';
    return;
  }

  let html = '<table class="data-table">' +
             '<thead><tr>';

  // Headers
  data.columns.forEach(col => {
    html += '<th>' + col + '</th>';
  });

  html += '</tr></thead><tbody>';

  // Rows
  data.rows.forEach(row => {
    html += '<tr>';
    data.columns.forEach(col => {
      let value = row[col];

      // Format value
      if (value === null || value === undefined) {
        value = '<span style="color: #9ca3af; font-style: italic;">null</span>';
      } else if (typeof value === 'boolean') {
        value = value ? '✓' : '✗';
      } else if (typeof value === 'string' && value.length > 100) {
        value = value.substring(0, 100) + '...';
      }

      html += '<td>' + value + '</td>';
    });
    html += '</tr>';
  });

  html += '</tbody></table>';
  container.innerHTML = html;
}

// Update pagination controls
function updatePaginationControls(data) {
  const info = document.getElementById('dataInfo');
  const prevBtn = document.getElementById('prevBtn');
  const nextBtn = document.getElementById('nextBtn');

  const start = currentOffset + 1;
  const end = Math.min(currentOffset + currentLimit, totalRows);

  info.textContent = 'Showing ' + start + '-' + end + ' of ' + totalRows + ' rows';

  prevBtn.disabled = currentOffset === 0;
  nextBtn.disabled = !data.has_more;
}

// Pagination functions
async function nextPage() {
  if (currentTable) {
    await loadTableData(currentTable, currentOffset + currentLimit);
  }
}

async function prevPage() {
  if (currentTable && currentOffset > 0) {
    await loadTableData(currentTable, Math.max(0, currentOffset - currentLimit));
  }
}

// Close table viewer
function closeTableViewer() {
  document.getElementById('tableViewer').style.display = 'none';
  currentTable = null;
  currentOffset = 0;
}

// Find duplicate faculty members
async function findDuplicates() {
  try {
    showAlert('dbAlert', '', 'clear');
    document.getElementById('duplicatesResult').innerHTML = '<p style="color: #6b7280;">Searching for duplicates...</p>';

    const response = await fetch('/api/admin/database/duplicates/faculty', {
      credentials: 'same-origin'
    });

    if (!response.ok) throw new Error('Failed to find duplicates');

    const data = await response.json();
    renderDuplicates(data);

  } catch (error) {
    console.error('Error finding duplicates:', error);
    document.getElementById('duplicatesResult').innerHTML =
      '<p style="color: #ef4444;">Error: ' + error.message + '</p>';
  }
}

// Render duplicates
function renderDuplicates(data) {
  const container = document.getElementById('duplicatesResult');

  if (!data.has_duplicates) {
    container.innerHTML =
      '<div class="no-duplicates">' +
      '<strong>✓ No duplicates found!</strong><br>' +
      'Your database is clean - no duplicate faculty IDs or emails detected.' +
      '</div>';
    return;
  }

  let html = '';

  // Duplicate IDs
  if (data.duplicate_ids.length > 0) {
    html += '<div class="duplicate-box">' +
            '<h4 style="color: #dc2626; margin-bottom: 12px; font-size: 14px;">Duplicate IDs Found</h4>';

    data.duplicate_ids.forEach(dup => {
      html += '<div style="margin-bottom: 16px;">' +
              '<strong>ID "' + dup.id_lower + '" appears ' + dup.count + ' times:</strong>';

      dup.records.forEach(rec => {
        html += '<div class="duplicate-record">' +
                '<strong>' + rec.name + '</strong> (ID: ' + rec.id + ')<br>' +
                '<small>Email: ' + (rec.email || 'none') + ' | ' +
                'Active: ' + (rec.active ? 'Yes' : 'No') + ' | ' +
                'Admin: ' + (rec.is_admin ? 'Yes' : 'No') + ' | ' +
                'Registered: ' + (rec.registered ? 'Yes' : 'No') + '</small><br>' +
                '<button class="btn-danger btn-sm" style="margin-top: 8px;" onclick="deleteFacultyFromDB(\'' + rec.id + '\', \'' + rec.name + '\')">' +
                'Delete This Record' +
                '</button>' +
                '</div>';
      });

      html += '</div>';
    });

    html += '</div>';
  }

  // Duplicate Emails
  if (data.duplicate_emails.length > 0) {
    html += '<div class="duplicate-box" style="margin-top: 16px;">' +
            '<h4 style="color: #dc2626; margin-bottom: 12px; font-size: 14px;">Duplicate Emails Found</h4>';

    data.duplicate_emails.forEach(dup => {
      html += '<div style="margin-bottom: 16px;">' +
              '<strong>Email "' + dup.email_lower + '" appears ' + dup.count + ' times:</strong>';

      dup.records.forEach(rec => {
        html += '<div class="duplicate-record">' +
                '<strong>' + rec.name + '</strong> (ID: ' + rec.id + ')<br>' +
                '<small>Email: ' + rec.email + ' | ' +
                'Active: ' + (rec.active ? 'Yes' : 'No') + ' | ' +
                'Admin: ' + (rec.is_admin ? 'Yes' : 'No') + ' | ' +
                'Registered: ' + (rec.registered ? 'Yes' : 'No') + '</small><br>' +
                '<button class="btn-danger btn-sm" style="margin-top: 8px;" onclick="deleteFacultyFromDB(\'' + rec.id + '\', \'' + rec.name + '\')">' +
                'Delete This Record' +
                '</button>' +
                '</div>';
      });

      html += '</div>';
    });

    html += '</div>';
  }

  container.innerHTML = html;
}

// Delete faculty from database (reuse existing function)
async function deleteFacultyFromDB(facultyId, facultyName) {
  if (!confirm('DELETE FACULTY MEMBER?\n\nName: ' + facultyName + '\nID: ' + facultyId + '\n\nThis action cannot be undone. Continue?')) {
    return;
  }

  try {
    const response = await fetch('/api/admin/faculty/' + facultyId, {
      method: 'DELETE',
      credentials: 'same-origin'
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to delete faculty');
    }

    showAlert('dbAlert', 'Faculty member deleted successfully', 'success');

    // Refresh duplicates search
    await findDuplicates();

  } catch (error) {
    console.error('Error deleting faculty:', error);
    showAlert('dbAlert', 'Failed to delete faculty: ' + error.message, 'error');
  }
}

// Execute custom query
async function executeCustomQuery() {
  try {
    showAlert('dbAlert', '', 'clear');
    const query = document.getElementById('customQuery').value.trim();

    if (!query) {
      showAlert('dbAlert', 'Please enter a query', 'error');
      return;
    }

    document.getElementById('queryResult').innerHTML = '<p style="color: #6b7280;">Executing query...</p>';

    const response = await fetch('/api/admin/database/query', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: query })
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Query failed');
    }

    const data = await response.json();
    renderQueryResult(data);

  } catch (error) {
    console.error('Error executing query:', error);
    document.getElementById('queryResult').innerHTML =
      '<div style="background: #fef2f2; padding: 16px; border-radius: 8px; border: 2px solid #fecaca; color: #991b1b;">' +
      '<strong>Error:</strong> ' + error.message +
      '</div>';
  }
}

// Render query result
function renderQueryResult(data) {
  const container = document.getElementById('queryResult');

  if (data.rows.length === 0) {
    container.innerHTML =
      '<div style="background: #f0fdf4; padding: 16px; border-radius: 8px; color: #166534;">' +
      'Query executed successfully. No rows returned.' +
      '</div>';
    return;
  }

  let html = '<div style="background: #f0fdf4; padding: 12px; border-radius: 8px; margin-bottom: 12px; color: #166534;">' +
             '<strong>✓ Query executed successfully</strong> - ' + data.row_count + ' rows returned' +
             '</div>';

  html += '<div class="table-container"><table class="data-table">' +
          '<thead><tr>';

  // Headers
  data.columns.forEach(col => {
    html += '<th>' + col + '</th>';
  });

  html += '</tr></thead><tbody>';

  // Rows
  data.rows.forEach(row => {
    html += '<tr>';
    data.columns.forEach(col => {
      let value = row[col];

      if (value === null || value === undefined) {
        value = '<span style="color: #9ca3af; font-style: italic;">null</span>';
      } else if (typeof value === 'boolean') {
        value = value ? '✓' : '✗';
      } else if (typeof value === 'string' && value.length > 100) {
        value = value.substring(0, 100) + '...';
      }

      html += '<td>' + value + '</td>';
    });
    html += '</tr>';
  });

  html += '</tbody></table></div>';
  container.innerHTML = html;
}

// ==================== GLOBAL FUNCTION EXPORTS ====================
window.loadTables = loadTables;
window.viewTable = viewTable;
window.closeTableViewer = closeTableViewer;
window.nextPage = nextPage;
window.prevPage = prevPage;
window.findDuplicates = findDuplicates;
window.deleteFacultyFromDB = deleteFacultyFromDB;
window.executeCustomQuery = executeCustomQuery;
