/**
 * AniPulse Component Library v1.0
 * Reusable JS components for premium UX
 */

(function() {
  'use strict';

  // ─── 1. Theme Manager ──────────────────────────────
  const ThemeManager = {
    init() {
      this.html = document.documentElement;
      this.toggle = document.getElementById('themeToggle');
      this.saved = localStorage.getItem('anipulse-theme');
      if (this.saved) this.set(this.saved, false);
      if (this.toggle) {
        this.toggle.addEventListener('click', () => {
          const next = this.html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
          this.set(next, true);
        });
      }
    },
    set(theme, persist) {
      this.html.setAttribute('data-theme', theme);
      if (this.toggle) this.toggle.textContent = theme === 'dark' ? '\uD83C\uDF19' : '\u2600\uFE0F';
      if (persist) localStorage.setItem('anipulse-theme', theme);
    },
    get current() { return this.html.getAttribute('data-theme'); }
  };

  // ─── 2. Toast Notifications ────────────────────────
  const Toast = {
    init() {
      this.container = document.getElementById('toastContainer');
      if (!this.container) {
        this.container = document.createElement('div');
        this.container.id = 'toastContainer';
        this.container.className = 'toast-container';
        document.body.appendChild(this.container);
      }
    },
    show(title, message, type, duration) {
      type = type || 'info';
      duration = duration || 5000;
      const icons = {
        success: 'check-circle', error: 'exclamation-circle',
        info: 'info-circle', warning: 'exclamation-triangle'
      };
      const el = document.createElement('div');
      el.className = 'toast-item animate-slide-in';
      el.innerHTML =
        '<div class="toast-icon ' + type + '"><i class="fas fa-' + (icons[type] || icons.info) + '"></i></div>' +
        '<div class="toast-body">' +
        (title ? '<div class="toast-title">' + this._esc(title) + '</div>' : '') +
        (message ? '<div class="toast-message">' + this._esc(message) + '</div>' : '') +
        '</div>' +
        '<button class="toast-close" onclick="this.closest(\'.toast-item\').remove()">&times;</button>';
      this.container.appendChild(el);
      if (duration > 0) {
        setTimeout(() => {
          if (el.isConnected) {
            el.classList.add('removing');
            setTimeout(() => { if (el.isConnected) el.remove(); }, 300);
          }
        }, duration);
      }
      return el;
    },
    success(title, msg, dur) { return this.show(title, msg, 'success', dur); },
    error(title, msg, dur) { return this.show(title, msg, 'error', dur); },
    info(title, msg, dur) { return this.show(title, msg, 'info', dur); },
    warning(title, msg, dur) { return this.show(title, msg, 'warning', dur); },
    _esc(s) {
      const d = document.createElement('div');
      d.textContent = s;
      return d.innerHTML;
    }
  };

  // ─── 3. Infinite Scroll ─────────────────────────────
  const InfiniteScroll = {
    observers: [],
    init(selector, options) {
      const targets = document.querySelectorAll(selector || '[data-infinite]');
      targets.forEach(el => this.observe(el, options));
    },
    observe(el, options) {
      const opts = Object.assign({
        rootMargin: '200px',
        threshold: 0.01,
        container: null,
        loadingClass: 'is-loading',
        loader: null,
      }, options || {});

      if (!('IntersectionObserver' in window)) return;

      const container = opts.container || el;
      const loader = opts.loader || container.querySelector('[data-loader]');

      const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
          if (!entry.isIntersecting) return;
          const page = parseInt(container.getAttribute('data-page') || '1');
          const total = parseInt(container.getAttribute('data-total') || '999');
          if (page >= total) { observer.unobserve(el); return; }

          if (loader) loader.classList.add(opts.loadingClass);
          container.dispatchEvent(new CustomEvent('infinite:load', {
            detail: { page, container, observer: this }
          }));
        });
      }, { rootMargin: opts.rootMargin, threshold: opts.threshold });

      this.observers.push(observer);
      observer.observe(el);
    },
    disconnect() {
      this.observers.forEach(o => o.disconnect());
      this.observers = [];
    }
  };

  // ─── 4. Lazy Images ────────────────────────────────
  const LazyImages = {
    init(selector) {
      const images = document.querySelectorAll(selector || 'img[data-src]');
      if ('IntersectionObserver' in window) {
        const observer = new IntersectionObserver((entries) => {
          entries.forEach(entry => {
            if (!entry.isIntersecting) return;
            const img = entry.target;
            if (img.dataset.src) img.src = img.dataset.src;
            if (img.dataset.srcset) img.srcset = img.dataset.srcset;
            img.removeAttribute('data-src');
            img.removeAttribute('data-srcset');
            observer.unobserve(img);
          });
        }, { rootMargin: '200px' });
        images.forEach(img => observer.observe(img));
      } else {
        images.forEach(img => {
          if (img.dataset.src) img.src = img.dataset.src;
          img.removeAttribute('data-src');
        });
      }
    }
  };

  // ─── 5. Clipboard ──────────────────────────────────
  const Clipboard = {
    copy(text, successMsg) {
      if (navigator.clipboard) {
        navigator.clipboard.writeText(text).then(() => {
          Toast.info('', successMsg || 'Copied to clipboard!');
        }).catch(() => {
          this._fallback(text, successMsg);
        });
      } else {
        this._fallback(text, successMsg);
      }
    },
    _fallback(text, successMsg) {
      const ta = document.createElement('textarea');
      ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); Toast.info('', successMsg || 'Copied!'); }
      catch (e) { Toast.error('', 'Failed to copy'); }
      document.body.removeChild(ta);
    }
  };

  // ─── 6. Smooth Scroll ──────────────────────────────
  const SmoothScroll = {
    init() {
      document.querySelectorAll('a[href^="#"]').forEach(a => {
        a.addEventListener('click', (e) => {
          const id = a.getAttribute('href');
          if (id === '#') return;
          const target = document.querySelector(id);
          if (target) {
            e.preventDefault();
            target.scrollIntoView({ behavior: 'smooth', block: 'start' });
          }
        });
      });
    }
  };

  // ─── 7. AJAX Form Handler ──────────────────────────
  const AjaxForms = {
    init(selector) {
      document.querySelectorAll(selector || 'form[data-ajax]').forEach(form => {
        form.addEventListener('submit', (e) => {
          e.preventDefault();
          const btn = form.querySelector('[type="submit"]');
          if (btn) { btn.disabled = true; btn.dataset.orig = btn.innerHTML; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>'; }

          const data = new FormData(form);
          fetch(form.action, {
            method: form.method || 'POST',
            body: data,
            headers: { 'X-CSRFToken': data.get('csrfmiddlewaretoken') || '' },
          })
          .then(r => r.json().catch(() => r.text()))
          .then(resp => {
            if (btn) { btn.disabled = false; btn.innerHTML = btn.dataset.orig || 'Submit'; }
            form.dispatchEvent(new CustomEvent('ajax:done', { detail: resp }));
            if (resp.success) {
              Toast.success(resp.title || 'Success!', resp.message || '');
              if (resp.redirect) setTimeout(() => { window.location.href = resp.redirect; }, 500);
            } else {
              Toast.error(resp.title || 'Error', resp.message || resp.error || 'Something went wrong.');
            }
          })
          .catch(err => {
            if (btn) { btn.disabled = false; btn.innerHTML = btn.dataset.orig || 'Submit'; }
            Toast.error('Network error', err.message);
          });
        });
      });
    }
  };

  // ─── 8. Mobile Nav Highlight ───────────────────────
  const MobileNav = {
    init() {
      const nav = document.getElementById('mobileBottomNav');
      if (!nav) return;
      const path = window.location.pathname;
      nav.querySelectorAll('.nav-item').forEach(a => {
        const href = a.getAttribute('href');
        if (path === href || (href !== '/' && path.startsWith(href))) {
          a.classList.add('active');
        }
      });
    }
  };

  // ─── 9. Notification Poller ────────────────────────
  const Notifications = {
    init() {
      if (!window._anipulseUserAuthed) return;
      this.fetch();
      setInterval(() => this.fetch(), 30000);
      const btn = document.getElementById('notifDropdown');
      if (btn) {
        btn.addEventListener('click', () => {
          fetch('/notifications/read-all/', {
            method: 'POST',
            headers: { 'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]')?.value || '' }
          });
          setTimeout(() => this.fetch(), 500);
        });
      }
    },
    fetch() {
      fetch('/notifications/json/')
        .then(r => r.json())
        .then(d => {
          const badge = document.getElementById('notifBadge');
          const menu = document.getElementById('notifMenu');
          const empty = document.getElementById('notifEmpty');
          if (!badge || !menu) return;
          if (d.unread_count > 0) {
            badge.style.display = 'inline';
            badge.textContent = d.unread_count;
          } else {
            badge.style.display = 'none';
          }
          if (empty) {
            if (d.notifications && d.notifications.length) {
              empty.style.display = 'none';
              menu.querySelectorAll('.notif-item').forEach(el => el.remove());
              d.notifications.forEach(n => {
                const el = document.createElement('a');
                el.className = 'dropdown-item notif-item' + (n.is_read ? '' : ' fw-bold');
                el.href = n.url || '#';
                el.style.cssText = 'white-space:normal;padding:10px 14px;border-bottom:1px solid var(--border);font-size:0.85rem';
                el.innerHTML = '<div>' + n.title + '</div>' +
                  (n.message ? '<div class="text-secondary" style="font-size:0.75rem">' + n.message + '</div>' : '') +
                  '<div class="text-secondary" style="font-size:0.65rem;margin-top:2px">' + new Date(n.created_at).toLocaleDateString() + '</div>';
                menu.appendChild(el);
              });
            } else {
              empty.style.display = 'block';
            }
          }
        });
    }
  };

  // ─── 10. Fade-up Observer ──────────────────────────
  const FadeUp = {
    init() {
      if ('IntersectionObserver' in window) {
        const observer = new IntersectionObserver((entries) => {
          entries.forEach(entry => {
            if (entry.isIntersecting) {
              entry.target.classList.add('visible');
              observer.unobserve(entry.target);
            }
          });
        }, { threshold: 0.1 });
        document.querySelectorAll('.fade-up').forEach(el => observer.observe(el));
      } else {
        document.querySelectorAll('.fade-up').forEach(el => el.classList.add('visible'));
      }
    }
  };

  // ─── 11. Star Rating ───────────────────────────────
  const StarRating = {
    init(selector) {
      document.querySelectorAll(selector || '[data-rating]').forEach(el => {
        const max = parseInt(el.getAttribute('data-max') || '10');
        const val = parseFloat(el.getAttribute('data-value') || '0');
        const interactive = el.hasAttribute('data-interactive');
        const name = el.getAttribute('data-name') || 'score';
        const half = max <= 10;

        el.innerHTML = '';
        el.style.cssText = 'display:flex;gap:2px;';

        for (let i = 1; i <= max; i++) {
          const star = document.createElement('span');
          star.style.cssText = 'cursor:' + (interactive ? 'pointer' : 'default') + ';font-size:1.2rem;transition:transform 0.15s;color:' + (i <= val ? '#fbbf24' : '#374151') + ';';
          star.textContent = i <= val ? '\u2605' : '\u2606';
          star.dataset.value = i;

          if (interactive) {
            star.addEventListener('click', () => {
              el.querySelectorAll('span').forEach(s => {
                s.textContent = parseInt(s.dataset.value) <= i ? '\u2605' : '\u2606';
                s.style.color = parseInt(s.dataset.value) <= i ? '#fbbf24' : '#374151';
              });
              const input = document.querySelector('input[name="' + name + '"]');
              if (input) input.value = i;
              el.dispatchEvent(new CustomEvent('rating:change', { detail: { value: i } }));
            });
            star.addEventListener('mouseenter', () => star.style.transform = 'scale(1.2)');
            star.addEventListener('mouseleave', () => star.style.transform = 'scale(1)');
          }

          el.appendChild(star);
        }
      });
    }
  };

  // ─── 12. Modal System ──────────────────────────────
  const Modal = {
    stack: [],
    open(content, options) {
      const opts = Object.assign({ title: '', size: 'md', closable: true, onClose: null }, options || {});
      const overlay = document.createElement('div');
      overlay.className = 'modal-overlay';
      overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.6);z-index:10000;display:flex;align-items:center;justify-content:center;padding:20px;animation:fadeIn 0.2s ease-out;';

      const dialog = document.createElement('div');
      const widthMap = { sm: '400px', md: '560px', lg: '720px', xl: '900px' };
      dialog.style.cssText = 'background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-xl);width:100%;max-width:' + (widthMap[opts.size] || widthMap.md) + ';max-height:90vh;overflow-y:auto;animation:fadeInUp 0.3s ease-out;';

      dialog.innerHTML =
        '<div style="display:flex;align-items:center;justify-content:space-between;padding:20px 24px;border-bottom:1px solid var(--border)">' +
        '<h3 style="margin:0;font-size:1.1rem;font-weight:700">' + opts.title + '</h3>' +
        (opts.closable ? '<button class="btn-icon" onclick="this.closest(\'.modal-overlay\').close()" style="width:32px;height:32px">&times;</button>' : '') +
        '</div>' +
        '<div class="modal-body" style="padding:24px">' +
        (typeof content === 'string' ? content : '') +
        '</div>';

      if (typeof content === 'object' && content.nodeType) {
        dialog.querySelector('.modal-body').appendChild(content);
      }

      overlay.appendChild(dialog);
      overlay.close = () => {
        overlay.style.opacity = '0';
        setTimeout(() => { overlay.remove(); this.stack.pop(); document.body.style.overflow = this.stack.length > 0 ? 'hidden' : ''; }, 200);
        if (opts.onClose) opts.onClose();
      };
      overlay.addEventListener('click', (e) => {
        if (e.target === overlay && opts.closable) overlay.close();
      });

      document.body.appendChild(overlay);
      document.body.style.overflow = 'hidden';
      this.stack.push(overlay);
      return overlay;
    },
    closeAll() {
      while (this.stack.length) this.stack.pop().close();
    }
  };

  // ─── INIT ──────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', function() {
    ThemeManager.init();
    Toast.init();
    MobileNav.init();
    SmoothScroll.init();
    FadeUp.init();
    LazyImages.init();
    Notifications.init();
    InfiniteScroll.init();

    // Convert flash messages to toasts
    document.querySelectorAll('.alert-dismissible').forEach(el => {
      const text = el.textContent.replace('\u00d7', '').trim();
      const cls = el.classList.contains('alert-success') ? 'success' :
                  el.classList.contains('alert-danger') ? 'error' :
                  el.classList.contains('alert-warning') ? 'warning' : 'info';
      if (text) setTimeout(() => Toast.show('', text, cls), 100);
      el.style.display = 'none';
    });
  });

  // ─── EXPOSE GLOBALS ────────────────────────────────
  window.AniPulse = {
    Toast,
    Modal,
    Clipboard,
    InfiniteScroll,
    LazyImages,
    StarRating,
    AjaxForms,
    ThemeManager,
  };

})();
