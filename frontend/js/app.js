/**
 * HR Q&A Agent — Application Orchestrator
 * Defines: window.HrApp
 * Initialization, page routing, global state, event coordination.
 * Must be loaded LAST (after all other modules).
 */

(function () {
  'use strict';

  // ---- Application State ----

  var state = {
    auth: {
      user: null,
      isAuthenticated: false
    },
    chat: {
      activeSessionId: null,
      sessions: [],
      messages: [],
      isStreaming: false,
      activeAgent: null
    },
    ui: {
      currentPage: 'login',
      sidebarOpen: true,
      isLoading: false
    }
  };

  // ---- State Management ----

  function getState(path) {
    var parts = path.split('.');
    var obj = state;
    for (var i = 0; i < parts.length; i++) {
      if (obj === undefined || obj === null) return undefined;
      obj = obj[parts[i]];
    }
    return obj;
  }

  function setState(path, value) {
    var parts = path.split('.');
    var obj = state;
    for (var i = 0; i < parts.length - 1; i++) {
      if (!obj[parts[i]]) obj[parts[i]] = {};
      obj = obj[parts[i]];
    }
    obj[parts[parts.length - 1]] = value;
  }

  // ---- Initialization ----

  async function init() {
    var stored = window.HrAuth.getStoredAuth();

    if (stored.token) {
      // Token exists — validate it
      window.HrApi.setToken(stored.token);

      try {
        var user = await window.HrApi.apiGet('/auth/me');
        setState('auth', {
          user: user,
          isAuthenticated: true
        });
        setState('chat.activeSessionId', null);

        window.HrAuth.scheduleTokenRefresh();
        showChatPage();

        // Restore active session if one was persisted
        var savedSessionId = localStorage.getItem('hr_active_session');
        if (savedSessionId) {
          window.HrSessions.switchSession(savedSessionId);
        }

      } catch (e) {
        // Token invalid — try refresh
        var newToken = await window.HrAuth.refreshAccessToken();
        if (newToken) {
          // Retry with new token
          try {
            var user2 = await window.HrApi.apiGet('/auth/me');
            setState('auth', {
              user: user2,
              isAuthenticated: true
            });
            showChatPage();
            window.HrAuth.scheduleTokenRefresh();
            return;
          } catch (e2) {
            // Refresh also failed
            window.HrAuth.handleLogout();
          }
        } else {
          window.HrAuth.handleLogout();
        }
      }
    } else {
      // No token — show login
      showLoginPage();
    }

    // Listen for unauthorized events from API layer
    document.addEventListener('app:auth-unauthorized', _handleUnauthorized);

    // Listen for online/offline events
    window.addEventListener('online', hideOfflineBanner);
    window.addEventListener('offline', showOfflineBanner);

    // Initial online check
    if (!navigator.onLine) {
      showOfflineBanner();
    }
  }

  // ---- Page Routing ----

  function showLoginPage() {
    var loginPage = document.getElementById('login-page');
    var chatPage = document.getElementById('chat-page');

    if (loginPage) loginPage.classList.remove('hidden');
    if (chatPage) chatPage.classList.add('hidden');

    setState('ui.currentPage', 'login');
    document.title = 'Company Assistant — Sign In';

    // Focus email input
    setTimeout(function () {
      var emailInput = document.getElementById('login-email');
      if (emailInput) emailInput.focus();
    }, 100);
  }

  function showChatPage() {
    var loginPage = document.getElementById('login-page');
    var chatPage = document.getElementById('chat-page');

    if (loginPage) loginPage.classList.add('hidden');
    if (chatPage) chatPage.classList.remove('hidden');

    setState('ui.currentPage', 'chat');

    // Update sidebar user info
    _updateSidebarUserInfo();

    // Load sessions
    if (window.HrSessions) {
      window.HrSessions.loadSessions();
    }

    // Show welcome message
    var user = getState('auth.user');
    if (window.HrChat) {
      window.HrChat.showWelcomeMessage(user ? user.full_name : 'there');
    }

    document.title = 'Company Assistant';

    // Focus chat input
    setTimeout(function () {
      var chatInput = document.getElementById('chat-input');
      if (chatInput) chatInput.focus();
    }, 200);
  }

  function _updateSidebarUserInfo() {
    var user = getState('auth.user');
    if (!user) return;

    var avatarEl = document.getElementById('user-avatar');
    var nameEl = document.getElementById('user-name');
    var roleEl = document.getElementById('user-role-badge');
    var deptEl = document.getElementById('user-dept');

    if (avatarEl && user.full_name) {
      avatarEl.textContent = user.full_name.charAt(0).toUpperCase();
    }
    if (nameEl) {
      nameEl.textContent = window.HrUtils.escapeHtml(user.full_name || 'User');
    }
    if (roleEl) {
      roleEl.textContent = window.HrUtils.getRoleBadge(user.role);
      roleEl.className = 'user-role-badge ' + window.HrUtils.getRoleClass(user.role);
    }
    if (deptEl) {
      deptEl.textContent = window.HrUtils.escapeHtml(user.department || '');
    }
  }

  // ---- Auth Unauthorized Handler ----

  async function _handleUnauthorized() {
    // Prevent multiple simultaneous refreshes
    if (_handleUnauthorized.refreshing) return;
    _handleUnauthorized.refreshing = true;

    try {
      var newToken = await window.HrAuth.refreshAccessToken();
      if (!newToken) {
        // Refresh failed — force logout
        window.HrAuth.clearAuth();
        window.HrApi.setToken(null);
        setState('auth', { user: null, isAuthenticated: false });
        showLoginPage();
        showToast('Session expired. Please sign in again.', 'warning');
      }
      // If refresh succeeded, the API call that triggered this will be retried
      // by the user on their next action
    } finally {
      _handleUnauthorized.refreshing = false;
    }
  }
  _handleUnauthorized.refreshing = false;

  // ---- Toast Notifications ----

  function showToast(message, type, duration) {
    type = type || 'info';
    duration = duration || (type === 'error' ? 0 : 3000);

    var container = document.getElementById('toast-container');
    if (!container) return;

    var toast = document.createElement('div');
    toast.className = 'toast toast-' + type;

    // Icon
    var iconMap = {
      success: '✓',
      error: '✕',
      warning: '⚠',
      info: 'ℹ'
    };
    var icon = document.createElement('span');
    icon.className = 'toast-icon';
    icon.textContent = iconMap[type] || 'ℹ';

    // Message
    var msg = document.createElement('span');
    msg.className = 'toast-message';
    msg.textContent = message;

    toast.appendChild(icon);
    toast.appendChild(msg);

    // Dismiss button (always shown for errors, optional for others)
    if (type === 'error' || duration === 0) {
      var dismiss = document.createElement('button');
      dismiss.className = 'toast-dismiss';
      dismiss.innerHTML = '&times;';
      dismiss.setAttribute('aria-label', 'Dismiss notification');
      dismiss.addEventListener('click', function () {
        _removeToast(toast);
      });
      toast.appendChild(dismiss);
    }

    container.appendChild(toast);

    // Auto-dismiss
    if (duration > 0) {
      setTimeout(function () {
        _removeToast(toast);
      }, duration);
    }
  }

  function _removeToast(toast) {
    if (!toast || !toast.parentNode) return;
    toast.classList.add('toast-removing');
    setTimeout(function () {
      if (toast.parentNode) {
        toast.parentNode.removeChild(toast);
      }
    }, 200);
  }

  // ---- Sidebar Toggle (Mobile) ----

  function toggleSidebar() {
    var sidebar = document.getElementById('sidebar');
    var overlay = document.getElementById('sidebar-overlay');
    var hamburger = document.getElementById('hamburger-btn');

    var isOpen = sidebar && sidebar.classList.contains('open');

    if (sidebar) sidebar.classList.toggle('open', !isOpen);
    if (overlay) overlay.classList.toggle('visible', !isOpen);
    if (hamburger) hamburger.setAttribute('aria-expanded', !isOpen);

    setState('ui.sidebarOpen', !isOpen);
  }

  function closeSidebar() {
    var sidebar = document.getElementById('sidebar');
    var overlay = document.getElementById('sidebar-overlay');
    var hamburger = document.getElementById('hamburger-btn');

    if (sidebar) sidebar.classList.remove('open');
    if (overlay) overlay.classList.remove('visible');
    if (hamburger) hamburger.setAttribute('aria-expanded', 'false');

    setState('ui.sidebarOpen', false);
  }

  // ---- Offline Banner ----

  function showOfflineBanner() {
    var banner = document.getElementById('offline-banner');
    if (banner) banner.classList.remove('hidden');
  }

  function hideOfflineBanner() {
    var banner = document.getElementById('offline-banner');
    if (banner) banner.classList.add('hidden');
    showToast('Connection restored', 'success', 3000);
  }

  // ---- DOM Content Loaded ----

  document.addEventListener('DOMContentLoaded', function () {
    // Bind auth forms
    window.HrAuth.bindLoginForm(document.getElementById('login-form'));
    window.HrAuth.bindRegisterForm(document.getElementById('register-form'));

    // Toggle between login and register
    var showRegister = document.getElementById('show-register');
    var showLogin = document.getElementById('show-login');
    if (showRegister) {
      showRegister.addEventListener('click', function (e) {
        e.preventDefault();
        window.HrAuth.showRegisterForm();
      });
    }
    if (showLogin) {
      showLogin.addEventListener('click', function (e) {
        e.preventDefault();
        window.HrAuth.showLoginForm();
      });
    }

    // Sidebar actions
    var newChatBtn = document.getElementById('new-chat-btn');
    var logoutBtn = document.getElementById('logout-btn');
    if (newChatBtn) {
      newChatBtn.addEventListener('click', function () {
        window.HrSessions.createNewChat();
      });
    }
    if (logoutBtn) {
      logoutBtn.addEventListener('click', function () {
        window.HrAuth.handleLogout();
      });
    }

    // Mobile hamburger
    var hamburgerBtn = document.getElementById('hamburger-btn');
    if (hamburgerBtn) {
      hamburgerBtn.addEventListener('click', toggleSidebar);
    }

    // Sidebar overlay (close sidebar on tap)
    var overlay = document.getElementById('sidebar-overlay');
    if (overlay) {
      overlay.addEventListener('click', closeSidebar);
    }

    // Chat input bindings
    window.HrChat.bindInputBar(document.getElementById('input-bar'));

    // Init
    init();
  });

  // ---- Expose Module ----

  window.HrApp = {
    init: init,
    getState: getState,
    setState: setState,
    showLoginPage: showLoginPage,
    showChatPage: showChatPage,
    showToast: showToast,
    toggleSidebar: toggleSidebar,
    closeSidebar: closeSidebar
  };
})();
