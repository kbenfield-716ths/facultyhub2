/**
 * Knowledge Base Management Module
 * CRUD for knowledge base articles with Markdown support
 */

let kbArticles = [];
let kbCategoryFilter = 'all';
let kbEditingId = null;

// Load articles on init
document.addEventListener('DOMContentLoaded', function() {
  if (document.getElementById('kbTableBody')) {
    loadKBArticles();
  }
});

// Load all articles (admin endpoint - includes unpublished)
async function loadKBArticles() {
  try {
    showKBAlert('', 'clear');

    const response = await fetch('/api/knowledge-base/admin/articles', {
      credentials: 'same-origin'
    });
    if (!response.ok) throw new Error('Failed to load articles');

    kbArticles = await response.json();
    renderKBTable();
    updateKBStats();

  } catch (error) {
    console.error('Error loading articles:', error);
    showKBAlert('Failed to load articles: ' + error.message, 'error');
  }
}

// Render articles table
function renderKBTable() {
  const tbody = document.getElementById('kbTableBody');

  let filtered = kbArticles;
  if (kbCategoryFilter !== 'all') {
    filtered = kbArticles.filter(function(a) { return a.category === kbCategoryFilter; });
  }

  if (filtered.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="empty-state">' +
      '<div class="empty-state-icon"></div>' +
      '<div class="empty-state-title">No Articles</div>' +
      '<div class="empty-state-description">Create your first knowledge base article</div>' +
      '</td></tr>';
    return;
  }

  tbody.innerHTML = '';

  filtered.forEach(function(article) {
    var row = document.createElement('tr');

    var statusBadge = article.is_published
      ? '<span class="badge badge-success">Published</span>'
      : '<span class="badge badge-warning">Draft</span>';

    row.innerHTML = '<td style="font-weight: 600;">' + article.title + '<br><small style="color: #6b7280; font-weight: 400;">' + truncate(article.description, 80) + '</small></td>' +
                    '<td><span class="badge">' + article.category + '</span></td>' +
                    '<td>' + statusBadge + '</td>' +
                    '<td>' + (article.author_name || 'Unknown') + '</td>' +
                    '<td>' + formatDate(article.updated_at) + '</td>' +
                    '<td><div class="action-buttons">' +
                      '<button class="btn-primary btn-sm" onclick="editKBArticle(\'' + article.id + '\')">Edit</button>' +
                      '<button class="btn-secondary btn-sm" onclick="toggleKBPublish(\'' + article.id + '\')">' + (article.is_published ? 'Unpublish' : 'Publish') + '</button>' +
                      '<button class="btn-danger btn-sm" onclick="deleteKBArticle(\'' + article.id + '\')">Delete</button>' +
                    '</div></td>';

    tbody.appendChild(row);
  });
}

// Update stats
function updateKBStats() {
  var published = kbArticles.filter(function(a) { return a.is_published; }).length;
  var drafts = kbArticles.filter(function(a) { return !a.is_published; }).length;

  document.getElementById('kbTotalCount').textContent = kbArticles.length;
  document.getElementById('kbPublishedCount').textContent = published;
  document.getElementById('kbDraftCount').textContent = drafts;
}

// Filter by category
function filterKBCategory(category) {
  kbCategoryFilter = category;

  document.querySelectorAll('.kb-cat-btn').forEach(function(btn) {
    btn.classList.remove('active');
  });
  event.target.classList.add('active');

  renderKBTable();
}

// Show create modal
function showCreateArticleModal() {
  kbEditingId = null;
  document.getElementById('articleModalTitle').textContent = 'New Article';
  document.getElementById('articleSubmitBtn').textContent = 'Create Article';
  document.getElementById('articleEditId').value = '';
  document.getElementById('articleForm').reset();
  document.getElementById('articlePublished').checked = true;
  document.getElementById('kbPreviewPane').style.display = 'none';
  document.getElementById('kbPreviewToggle').textContent = 'Show Preview';
  document.getElementById('articleModal').classList.add('show');
}

// Edit article
function editKBArticle(articleId) {
  var article = kbArticles.find(function(a) { return a.id === articleId; });
  if (!article) return;

  kbEditingId = articleId;
  document.getElementById('articleModalTitle').textContent = 'Edit Article';
  document.getElementById('articleSubmitBtn').textContent = 'Save Changes';
  document.getElementById('articleEditId').value = articleId;
  document.getElementById('articleTitle').value = article.title;
  document.getElementById('articleDescription').value = article.description;
  document.getElementById('articleCategory').value = article.category;
  document.getElementById('articleOrder').value = article.display_order || 0;
  document.getElementById('articlePublished').checked = article.is_published;
  document.getElementById('articleContent').value = article.content;
  document.getElementById('kbPreviewPane').style.display = 'none';
  document.getElementById('kbPreviewToggle').textContent = 'Show Preview';
  document.getElementById('articleModal').classList.add('show');
}

// Close modal
function closeArticleModal() {
  document.getElementById('articleModal').classList.remove('show');
  kbEditingId = null;
}

// Toggle preview pane
function toggleKBPreview() {
  var previewPane = document.getElementById('kbPreviewPane');
  var toggleBtn = document.getElementById('kbPreviewToggle');

  if (previewPane.style.display === 'none') {
    previewPane.style.display = 'block';
    toggleBtn.textContent = 'Hide Preview';

    // Render markdown if marked.js is available
    var content = document.getElementById('articleContent').value;
    if (typeof marked !== 'undefined') {
      previewPane.innerHTML = marked.parse(content);
    } else {
      previewPane.innerHTML = '<p style="color: #6b7280;">Markdown preview requires marked.js library.</p><pre style="white-space: pre-wrap;">' + content + '</pre>';
    }
  } else {
    previewPane.style.display = 'none';
    toggleBtn.textContent = 'Show Preview';
  }
}

// Submit create/edit
async function submitArticle(event) {
  event.preventDefault();

  var payload = {
    title: document.getElementById('articleTitle').value.trim(),
    description: document.getElementById('articleDescription').value.trim(),
    content: document.getElementById('articleContent').value,
    category: document.getElementById('articleCategory').value,
    is_published: document.getElementById('articlePublished').checked,
    display_order: parseInt(document.getElementById('articleOrder').value) || 0
  };

  try {
    var url, method;

    if (kbEditingId) {
      url = '/api/knowledge-base/admin/articles/' + kbEditingId;
      method = 'PUT';
    } else {
      url = '/api/knowledge-base/admin/articles';
      method = 'POST';
    }

    var response = await fetch(url, {
      method: method,
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      var error = await response.json();
      throw new Error(error.detail || 'Failed to save article');
    }

    showKBAlert(kbEditingId ? 'Article updated successfully' : 'Article created successfully', 'success');
    closeArticleModal();
    await loadKBArticles();

  } catch (error) {
    console.error('Error saving article:', error);
    showKBAlert('Error: ' + error.message, 'error');
  }
}

// Toggle publish status
async function toggleKBPublish(articleId) {
  var article = kbArticles.find(function(a) { return a.id === articleId; });
  if (!article) return;

  var newStatus = !article.is_published;
  var action = newStatus ? 'publish' : 'unpublish';

  if (!confirm('Are you sure you want to ' + action + ' "' + article.title + '"?')) return;

  try {
    var response = await fetch('/api/knowledge-base/admin/articles/' + articleId, {
      method: 'PUT',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_published: newStatus })
    });

    if (!response.ok) throw new Error('Failed to update article');

    showKBAlert('Article ' + (newStatus ? 'published' : 'unpublished'), 'success');
    await loadKBArticles();

  } catch (error) {
    showKBAlert('Error: ' + error.message, 'error');
  }
}

// Delete article
async function deleteKBArticle(articleId) {
  var article = kbArticles.find(function(a) { return a.id === articleId; });
  if (!article) return;

  if (!confirm('DELETE ARTICLE?\n\n"' + article.title + '"\n\nThis action cannot be undone.')) return;

  try {
    var response = await fetch('/api/knowledge-base/admin/articles/' + articleId, {
      method: 'DELETE',
      credentials: 'same-origin'
    });

    if (!response.ok) throw new Error('Failed to delete article');

    showKBAlert('Article deleted', 'success');
    await loadKBArticles();

  } catch (error) {
    showKBAlert('Error: ' + error.message, 'error');
  }
}

// Alert helper
function showKBAlert(message, type) {
  var alertEl = document.getElementById('kbAlert');
  if (!alertEl) return;

  if (type === 'clear') {
    alertEl.className = 'alert';
    alertEl.textContent = '';
    return;
  }

  alertEl.className = 'alert show';
  if (type === 'success') alertEl.classList.add('alert-success');
  else if (type === 'error') alertEl.classList.add('alert-error');
  else if (type === 'info') alertEl.classList.add('alert-info');

  alertEl.textContent = message;

  if (type === 'success') {
    setTimeout(function() {
      alertEl.className = 'alert';
      alertEl.textContent = '';
    }, 3000);
  }
}

// ==================== GLOBAL FUNCTION EXPORTS ====================
// Make functions globally accessible for inline onclick handlers

window.loadKBArticles = loadKBArticles;
window.filterKBCategory = filterKBCategory;
window.showCreateArticleModal = showCreateArticleModal;
window.editKBArticle = editKBArticle;
window.closeArticleModal = closeArticleModal;
window.toggleKBPreview = toggleKBPreview;
window.submitArticle = submitArticle;
window.toggleKBPublish = toggleKBPublish;
window.deleteKBArticle = deleteKBArticle;

// ==================== MODAL CLOSE FUNCTIONALITY ====================

document.addEventListener('DOMContentLoaded', function() {
  var modal = document.getElementById('articleModal');
  if (modal) {
    modal.addEventListener('click', function(event) {
      if (event.target === modal) {
        closeArticleModal();
      }
    });
  }
});

document.addEventListener('keydown', function(event) {
  if (event.key === 'Escape') {
    var modal = document.getElementById('articleModal');
    if (modal && modal.classList.contains('show')) {
      closeArticleModal();
    }
  }
});

// Auto-update preview on content change
document.addEventListener('DOMContentLoaded', function() {
  var contentArea = document.getElementById('articleContent');
  if (contentArea) {
    contentArea.addEventListener('input', function() {
      var previewPane = document.getElementById('kbPreviewPane');
      if (previewPane && previewPane.style.display !== 'none') {
        if (typeof marked !== 'undefined') {
          previewPane.innerHTML = marked.parse(contentArea.value);
        }
      }
    });
  }
});
