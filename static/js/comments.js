function CommentSystem(threadEl) {
  const ctype = threadEl.dataset.ctype;
  const oid = threadEl.dataset.oid;
  const listEl = document.getElementById('comment-list-' + oid);
  const loadingEl = document.getElementById('comment-loading-' + oid);
  const countEl = document.getElementById('comment-count-' + oid);
  const inputEl = document.getElementById('comment-input-' + oid);
  const spoilerCheck = document.getElementById('spoiler-check-' + oid);
  const submitBtn = threadEl.querySelector('.comment-submit-btn');

  let csrfToken = document.querySelector('[name=csrfmiddlewaretoken]');
  csrfToken = csrfToken ? csrfToken.value : '';

  function getCookie(name) {
    let c = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return c ? c.pop() : '';
  }
  if (!csrfToken) csrfToken = getCookie('csrftoken');

  function esc(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  }

  function renderComment(c, depth) {
    const d = depth || 0;
    const indent = Math.min(d * 24, 72);
    const spoilerClass = c.is_spoiler ? ' comment-spoiler' : '';
    const likedClass = c.liked ? ' liked' : '';
    const deletedClass = c.body === '[deleted]' ? ' comment-deleted' : '';

    let html = '<div class="comment-item' + deletedClass + '" data-id="' + c.id + '" style="margin-left:' + indent + 'px">';
    html += '<div class="d-flex gap-2 align-items-start">';
    if (c.avatar) {
      html += '<img src="' + esc(c.avatar) + '" alt="" class="comment-avatar rounded-circle flex-shrink-0" width="28" height="28">';
    } else {
      html += '<div class="comment-avatar rounded-circle bg-secondary flex-shrink-0 d-flex align-items-center justify-content-center" style="width:28px;height:28px;font-size:12px;color:#fff">' + esc(c.user.charAt(0).toUpperCase()) + '</div>';
    }
    html += '<div class="flex-grow-1 min-width-0">';
    html += '<div class="d-flex align-items-center gap-2 flex-wrap"><strong class="small">' + esc(c.user) + '</strong>';
    html += '<span class="text-muted" style="font-size:11px">' + timeAgo(c.created_at) + '</span>';
    if (c.is_spoiler) html += '<span class="badge" style="background:var(--spoiler, #dc3545);font-size:10px">Spoiler</span>';
    if (c.is_edited && c.body !== '[deleted]') html += '<span class="text-muted" style="font-size:10px">(edited)</span>';
    html += '</div>';
    html += '<div class="comment-body' + spoilerClass + ' mt-1" style="font-size:14px;line-height:1.5">' + esc(c.body) + '</div>';
    html += '<div class="d-flex align-items-center gap-3 mt-1">';
    html += '<button class="comment-like-btn btn btn-sm" data-id="' + c.id + '" style="font-size:12px;padding:0;border:none;background:none;color:' + (c.liked ? 'var(--primary)' : 'var(--text-muted)') + '"><i class="fa' + (c.liked ? 's' : 'r') + ' fa-heart"></i> <span class="like-count">' + c.likes + '</span></button>';
    html += '<button class="comment-reply-btn btn btn-sm text-muted" data-id="' + c.id + '" style="font-size:12px;padding:0;border:none;background:none">Reply</button>';
    if (c.can_edit && c.body !== '[deleted]') {
      html += '<button class="comment-edit-btn btn btn-sm text-muted" data-id="' + c.id + '" style="font-size:12px;padding:0;border:none;background:none">Edit</button>';
      html += '<button class="comment-delete-btn btn btn-sm text-danger" data-id="' + c.id + '" style="font-size:12px;padding:0;border:none;background:none">Delete</button>';
    }
    html += '</div>';

    html += '<div class="reply-form-wrap mt-2" id="reply-form-' + c.id + '" style="display:none">';
    html += '<div class="d-flex gap-2"><textarea class="form-control form-control-sm reply-textarea" rows="1" placeholder="Write a reply..." maxlength="2000" style="font-size:13px;resize:none"></textarea>';
    html += '<button class="btn btn-sm reply-submit-btn" data-parent="' + c.id + '" style="background:var(--primary);color:#fff;border:none;border-radius:6px;padding:4px 12px;font-size:12px">Reply</button></div></div>';

    html += '<div class="edit-form-wrap mt-2" id="edit-form-' + c.id + '" style="display:none">';
    html += '<div class="d-flex gap-2"><textarea class="form-control form-control-sm edit-textarea" rows="2" maxlength="2000" style="font-size:13px;resize:none">' + esc(c.body) + '</textarea>';
    html += '<button class="btn btn-sm edit-submit-btn btn-sm" data-id="' + c.id + '" style="background:var(--primary);color:#fff;border:none;border-radius:6px;padding:4px 12px;font-size:12px">Save</button></div></div>';

    html += '</div></div>';

    if (c.replies && c.replies.length > 0) {
      c.replies.forEach(function(r) {
        html += renderComment(r, d + 1);
      });
    }
    if (c.has_more) {
      html += '<button class="btn btn-sm text-muted load-more-btn" data-id="' + c.id + '" style="margin-left:' + (indent + 28) + 'px;font-size:12px;border:none;background:none">Show more replies</button>';
    }
    html += '</div>';
    return html;
  }

  function timeAgo(iso) {
    const diff = Date.now() - new Date(iso).getTime();
    const sec = Math.floor(diff / 1000);
    if (sec < 60) return 'just now';
    const min = Math.floor(sec / 60);
    if (min < 60) return min + 'm';
    const hr = Math.floor(min / 60);
    if (hr < 24) return hr + 'h';
    const day = Math.floor(hr / 24);
    if (day < 30) return day + 'd';
    return Math.floor(day / 30) + 'mo';
  }

  this.load = function() {
    fetch('/comments/json/?ctype=' + encodeURIComponent(ctype) + '&oid=' + encodeURIComponent(oid))
      .then(function(r) { return r.json(); })
      .then(function(data) {
        loadingEl.style.display = 'none';
        if (data.comments && data.comments.length > 0) {
          listEl.innerHTML = data.comments.map(function(c) { return renderComment(c); }).join('');
          countEl.textContent = data.comments.length;
        } else {
          listEl.innerHTML = '<p class="text-muted small text-center py-3">No comments yet. Be the first!</p>';
          countEl.textContent = '0';
        }
      })
      .catch(function() {
        loadingEl.style.display = 'none';
        listEl.innerHTML = '<p class="text-muted small text-center py-3">Failed to load comments.</p>';
      });
  };

  function addComment(body, parentId, spoiler) {
    var formData = new FormData();
    formData.append('body', body);
    formData.append('ctype', ctype);
    formData.append('oid', oid);
    if (parentId) formData.append('parent', parentId);
    if (spoiler) formData.append('spoiler', '1');

    return fetch('/comments/create/', { method: 'POST', headers: { 'X-CSRFToken': csrfToken }, body: formData })
      .then(function(r) { return r.json(); });
  }

  if (submitBtn) {
    submitBtn.addEventListener('click', function() {
      var body = inputEl.value.trim();
      if (!body || body.length < 2) return;
      submitBtn.disabled = true;
      submitBtn.textContent = 'Posting...';
      var spoiler = spoilerCheck ? spoilerCheck.checked : false;

      addComment(body, null, spoiler).then(function(data) {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Post';
        if (data.error) { alert(data.error); return; }
        inputEl.value = '';
        if (spoilerCheck) spoilerCheck.checked = false;
        var emptyMsg = listEl.querySelector('.text-center.py-3');
        if (emptyMsg) emptyMsg.remove();
        listEl.insertAdjacentHTML('afterbegin', renderComment(data));
        var cur = parseInt(countEl.textContent) || 0;
        countEl.textContent = cur + 1;
      }).catch(function() {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Post';
        alert('Failed to post comment');
      });
    });
  }

  listEl.addEventListener('click', function(e) {
    var target = e.target.closest('button');
    if (!target) return;

    if (target.classList.contains('comment-like-btn')) {
      e.preventDefault();
      var id = target.dataset.id;
      var countSpan = target.querySelector('.like-count');
      var icon = target.querySelector('i');

      if (target.dataset.optimistic !== '1') {
        var wasLiked = icon.classList.contains('fas');
        icon.className = wasLiked ? 'far fa-heart' : 'fas fa-heart';
        target.style.color = wasLiked ? 'var(--text-muted)' : 'var(--primary)';
        countSpan.textContent = parseInt(countSpan.textContent) + (wasLiked ? -1 : 1);
        target.dataset.optimistic = '1';
      }

      fetch('/comments/' + id + '/like/', { method: 'POST', headers: { 'X-CSRFToken': csrfToken } })
        .then(function(r) { return r.json(); })
        .then(function(data) {
          icon.className = data.liked ? 'fas fa-heart' : 'far fa-heart';
          target.style.color = data.liked ? 'var(--primary)' : 'var(--text-muted)';
          countSpan.textContent = data.likes;
          target.dataset.optimistic = '';
        }).catch(function() {
          var reverted = icon.classList.contains('far');
          icon.className = reverted ? 'fas fa-heart' : 'far fa-heart';
          target.style.color = reverted ? 'var(--primary)' : 'var(--text-muted)';
          countSpan.textContent = parseInt(countSpan.textContent) + (reverted ? 1 : -1);
          target.dataset.optimistic = '';
        });
    }

    if (target.classList.contains('comment-reply-btn')) {
      e.preventDefault();
      var wrap = document.getElementById('reply-form-' + target.dataset.id);
      if (wrap) wrap.style.display = wrap.style.display === 'none' ? 'block' : 'none';
    }

    if (target.classList.contains('comment-delete-btn')) {
      e.preventDefault();
      var id = target.dataset.id;
      if (!confirm('Delete this comment?')) return;
      fetch('/comments/' + id + '/delete/', { method: 'POST', headers: { 'X-CSRFToken': csrfToken } })
        .then(function(r) { return r.json(); })
        .then(function(data) {
          if (data.ok) {
            var item = listEl.querySelector('.comment-item[data-id="' + id + '"]');
            if (item) {
              item.querySelector('.comment-body').textContent = '[deleted]';
              item.classList.add('comment-deleted');
              var btns = item.querySelectorAll('.comment-edit-btn, .comment-delete-btn, .comment-reply-btn');
              btns.forEach(function(b) { b.style.display = 'none'; });
            }
          } else {
            alert(data.error || 'Delete failed');
          }
        });
    }

    if (target.classList.contains('comment-edit-btn')) {
      e.preventDefault();
      var id = target.dataset.id;
      var editWrap = document.getElementById('edit-form-' + id);
      if (editWrap) {
        editWrap.style.display = editWrap.style.display === 'none' ? 'block' : 'none';
        editWrap.querySelector('.edit-textarea').focus();
      }
    }
  });

  listEl.addEventListener('click', function(e) {
    var target = e.target.closest('button');
    if (!target) return;

    if (target.classList.contains('reply-submit-btn')) {
      e.preventDefault();
      var parentId = target.dataset.parent;
      var wrap = document.getElementById('reply-form-' + parentId);
      var textarea = wrap.querySelector('.reply-textarea');
      var body = textarea.value.trim();
      if (!body || body.length < 2) return;
      target.disabled = true;
      target.textContent = '...';

      addComment(body, parentId, false).then(function(data) {
        target.disabled = false;
        target.textContent = 'Reply';
        if (data.error) { alert(data.error); return; }
        textarea.value = '';
        wrap.style.display = 'none';
        var parentItem = listEl.querySelector('.comment-item[data-id="' + parentId + '"]');
        if (parentItem) {
          var hasMore = parentItem.querySelector('.load-more-btn');
          if (hasMore) hasMore.remove();
          parentItem.insertAdjacentHTML('beforeend', renderComment(data, parentItem.querySelector('.comment-item') ? (parseInt(parentItem.style.marginLeft) / 24 + 1) : 1));
        }
        var cur = parseInt(countEl.textContent) || 0;
        countEl.textContent = cur + 1;
      }).catch(function() {
        target.disabled = false;
        target.textContent = 'Reply';
        alert('Failed to post reply');
      });
    }

    if (target.classList.contains('edit-submit-btn')) {
      e.preventDefault();
      var id = target.dataset.id;
      var editWrap = document.getElementById('edit-form-' + id);
      var textarea = editWrap.querySelector('.edit-textarea');
      var body = textarea.value.trim();
      if (!body || body.length < 2) return;
      target.disabled = true;
      target.textContent = '...';

      fetch('/comments/' + id + '/edit/', {
        method: 'POST',
        headers: { 'X-CSRFToken': csrfToken },
        body: new URLSearchParams({ 'body': body })
      })
        .then(function(r) { return r.json(); })
        .then(function(data) {
          target.disabled = false;
          target.textContent = 'Save';
          if (data.error) { alert(data.error); return; }
          editWrap.style.display = 'none';
          var item = listEl.querySelector('.comment-item[data-id="' + id + '"]');
          if (item) {
            item.querySelector('.comment-body').textContent = data.body;
            var editedSpan = item.querySelector('.text-muted');
            if (data.is_edited && !editedSpan.textContent.includes('(edited)')) {
              editedSpan.insertAdjacentHTML('beforeend', ' <span class="text-muted" style="font-size:10px">(edited)</span>');
            }
          }
        }).catch(function() {
          target.disabled = false;
          target.textContent = 'Save';
          alert('Failed to edit comment');
        });
    }
  });

  listEl.addEventListener('click', function(e) {
    var spoilerEl = e.target.closest('.comment-spoiler');
    if (spoilerEl) {
      spoilerEl.classList.toggle('revealed');
    }
  });

  if (threadEl.dataset.lazy === '1') return;

  this.load();
}

document.addEventListener('DOMContentLoaded', function() {
  document.querySelectorAll('.comment-thread:not([data-lazy])').forEach(function(el) {
    new CommentSystem(el);
  });
});

window.CommentSystem = CommentSystem;
