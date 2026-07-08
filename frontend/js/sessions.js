/**
 * HR Q&A Agent — Session Management Module
 * Defines: window.HrSessions
 * Session list sidebar, create/switch/delete sessions.
 */

(function () {
  'use strict';

  // ---- Load Sessions ----

  async function loadSessions() {
    try {
      var res = await window.HrApi.apiGet('/sessions', {
        limit: 50,
        sort_by: 'last_active',
        sort_order: 'desc'
      });

      if (window.HrApp) {
        window.HrApp.setState('chat.sessions', res.sessions || []);
      }

      renderSessionList(res.sessions || []);
    } catch (e) {
      console.error('Failed to load sessions:', e);
      if (window.HrApp) {
        window.HrApp.showToast('Failed to load conversations', 'error');
      }
    }
  }

  // ---- Render Session List ----

  function renderSessionList(sessions) {
    var container = document.getElementById('session-list');
    if (!container) return;

    container.innerHTML = '';

    if (!sessions || sessions.length === 0) {
      var emptyEl = document.createElement('div');
      emptyEl.className = 'session-empty';
      emptyEl.textContent = 'No conversations yet.\nStart a new chat to begin!';
      container.appendChild(emptyEl);
      return;
    }

    var activeId = null;
    if (window.HrApp) {
      activeId = window.HrApp.getState('chat.activeSessionId');
    }

    for (var i = 0; i < sessions.length; i++) {
      var session = sessions[i];
      var item = _createSessionItem(session, session.id === activeId);
      container.appendChild(item);
    }
  }

  function _createSessionItem(session, isActive) {
    var item = document.createElement('div');
    item.className = 'session-item' + (isActive ? ' active' : '');
    item.setAttribute('data-session-id', session.id);
    item.setAttribute('role', 'button');
    item.setAttribute('tabindex', '0');
    item.setAttribute('aria-label', 'Switch to session: ' + (session.title || 'New Conversation'));

    // Content area
    var content = document.createElement('div');
    content.className = 'session-item-content';

    var title = document.createElement('div');
    title.className = 'session-title';
    title.textContent = session.title || 'New Conversation';

    var preview = document.createElement('div');
    preview.className = 'session-preview';
    preview.textContent = session.last_message_preview || '';

    var meta = document.createElement('div');
    meta.className = 'session-meta';

    var time = document.createElement('span');
    time.className = 'session-time';
    time.textContent = window.HrUtils.formatRelativeTime(session.last_active);

    var count = document.createElement('span');
    count.className = 'session-count';
    count.textContent = session.message_count || 0;

    meta.appendChild(time);
    meta.appendChild(count);

    content.appendChild(title);
    content.appendChild(preview);
    content.appendChild(meta);

    // Delete button
    var deleteBtn = document.createElement('button');
    deleteBtn.className = 'session-delete';
    deleteBtn.innerHTML = '&times;';
    deleteBtn.setAttribute('aria-label', 'Delete session: ' + (session.title || 'New Conversation'));
    deleteBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      deleteSession(session.id);
    });

    item.appendChild(content);
    item.appendChild(deleteBtn);

    // Click to switch session
    item.addEventListener('click', function () {
      switchSession(session.id);
    });

    // Keyboard support
    item.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        switchSession(session.id);
      }
    });

    return item;
  }

  // ---- Switch Session ----

  async function switchSession(sessionId) {
    if (!sessionId) return;

    var currentActive = null;
    if (window.HrApp) {
      currentActive = window.HrApp.getState('chat.activeSessionId');
    }

    if (sessionId === currentActive) return;

    // Stop any active stream
    if (window.HrStream && window.HrStream.isStreaming()) {
      window.HrStream.stopStream();
    }

    // Update state
    if (window.HrApp) {
      window.HrApp.setState('chat.activeSessionId', sessionId);
      window.HrApp.setState('chat.messages', []);
      window.HrApp.setState('ui.isLoading', true);
    }

    // Clear chat and show loading
    if (window.HrChat) {
      window.HrChat.clearChat();
      window.HrChat.showLoadingIndicator();
    }

    try {
      var res = await window.HrApi.apiGet('/sessions/' + sessionId + '/messages', { limit: 100 });

      if (window.HrApp) {
        window.HrApp.setState('chat.messages', res.messages || []);
      }

      // Update chat header with session title
      _updateChatHeader(sessionId);

      // Render messages
      if (window.HrChat) {
        window.HrChat.renderMessages(res.messages || []);
      }

      // Determine current agent from loaded messages
      var agentName = null;
      if (res.messages && res.messages.length > 0) {
        for (var i2 = res.messages.length - 1; i2 >= 0; i2--) {
          if (res.messages[i2].role === 'assistant') {
            agentName = res.messages[i2].agent_name || null;
            break;
          }
        }
      }
      if (window.HrApp) {
        window.HrApp.setState('chat.activeAgent', agentName);
      }
      if (window.HrChat && window.HrChat.showActiveAgentIndicator) {
        window.HrChat.showActiveAgentIndicator(agentName);
      }

    } catch (e) {
      console.error('Failed to load messages:', e);
      if (window.HrApp) {
        window.HrApp.showToast('Failed to load messages', 'error');
      }
    } finally {
      if (window.HrApp) {
        window.HrApp.setState('ui.isLoading', false);
      }
    }

    // Highlight active session
    highlightActiveSession(sessionId);

    // Persist
    localStorage.setItem('hr_active_session', sessionId);
  }

  function _updateChatHeader(sessionId) {
    var sessions = [];
    if (window.HrApp) {
      sessions = window.HrApp.getState('chat.sessions') || [];
    }
    var session = null;
    for (var i = 0; i < sessions.length; i++) {
      if (sessions[i].id === sessionId) {
        session = sessions[i];
        break;
      }
    }

    var headerEl = document.getElementById('chat-header-title');
    if (headerEl) {
      headerEl.textContent = (session && session.title) ? session.title : 'Company Assistant';
    }
  }

  // ---- Create New Chat ----

  function createNewChat() {
    // Stop active stream
    if (window.HrStream && window.HrStream.isStreaming()) {
      window.HrStream.stopStream();
    }

    // Reset state
    if (window.HrApp) {
      window.HrApp.setState('chat.activeSessionId', null);
      window.HrApp.setState('chat.messages', []);
      window.HrApp.setState('chat.activeAgent', null);
    }

    // Clear chat and show welcome
    if (window.HrChat) {
      window.HrChat.clearChat();
      var user = null;
      if (window.HrApp) {
        user = window.HrApp.getState('auth.user');
      }
      window.HrChat.showWelcomeMessage(user ? user.full_name : 'there');
    }

    // Update header
    var headerEl = document.getElementById('chat-header-title');
    if (headerEl) {
      headerEl.textContent = 'Company Assistant';
    }

    // Remove all active highlights
    highlightActiveSession(null);

    // Clear persisted active session
    localStorage.removeItem('hr_active_session');
  }

  // ---- Delete Session ----

  async function deleteSession(sessionId) {
    if (!confirm('Delete this conversation? This cannot be undone.')) {
      return;
    }

    try {
      await window.HrApi.apiDelete('/sessions/' + sessionId);

      // If this was the active session, switch to new chat
      var activeId = null;
      if (window.HrApp) {
        activeId = window.HrApp.getState('chat.activeSessionId');
      }

      if (activeId === sessionId) {
        createNewChat();
      }

      // Reload session list
      await loadSessions();

      if (window.HrApp) {
        window.HrApp.showToast('Conversation deleted', 'success');
      }

    } catch (e) {
      console.error('Failed to delete session:', e);
      if (window.HrApp) {
        window.HrApp.showToast('Failed to delete conversation', 'error');
      }
    }
  }

  // ---- Highlight Active Session ----

  function highlightActiveSession(sessionId) {
    var items = document.querySelectorAll('.session-item');
    for (var i = 0; i < items.length; i++) {
      var item = items[i];
      var itemId = item.getAttribute('data-session-id');
      if (itemId === sessionId) {
        item.classList.add('active');
        // Scroll into view
        item.scrollIntoView({ block: 'nearest' });
      } else {
        item.classList.remove('active');
      }
    }
  }

  // ---- Update Session in List ----

  /**
   * Refresh a single session's preview in the sidebar.
   * Called after a new message is received.
   */
  async function updateSessionInList(sessionId) {
    try {
      var session = await window.HrApi.apiGet('/sessions/' + sessionId);
      if (!session) return;

      // Update in app state
      if (window.HrApp) {
        var sessions = window.HrApp.getState('chat.sessions') || [];
        var found = false;
        for (var i = 0; i < sessions.length; i++) {
          if (sessions[i].id === sessionId) {
            sessions[i] = session;
            found = true;
            break;
          }
        }
        if (!found) {
          sessions.unshift(session);
        }
        window.HrApp.setState('chat.sessions', sessions);
      }

      // Re-render
      if (window.HrApp) {
        var currentSessions = window.HrApp.getState('chat.sessions') || [];
        renderSessionList(currentSessions);
      }

      // Update chat header
      _updateChatHeader(sessionId);

    } catch (e) {
      // Silently fail — the full reload on next action will catch up
      console.warn('Failed to update session in list:', e);
    }
  }

  // ---- Expose Module ----

  window.HrSessions = {
    loadSessions: loadSessions,
    renderSessionList: renderSessionList,
    switchSession: switchSession,
    createNewChat: createNewChat,
    deleteSession: deleteSession,
    highlightActiveSession: highlightActiveSession,
    updateSessionInList: updateSessionInList
  };
})();
