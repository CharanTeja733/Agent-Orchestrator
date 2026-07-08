/**
 * HR Q&A Agent — Streaming Module
 * Defines: window.HrStream
 * Bridges SSE events from HrApi.apiStream to HrChat UI updates.
 */

(function () {
  'use strict';

  var currentController = null;
  var pendingSources = [];
  var safetyTimer = null;
  var lastKnownAgent = null;

  /**
   * Start a streaming query.
   * @param {string} query — user's question
   * @param {string|null} sessionId — active session ID or null for new
   * @returns {AbortController}
   */
  function startStream(query, sessionId) {
    // Stop any existing stream
    if (currentController) {
      stopStream(currentController);
    }

    // Clear any existing safety timer
    _clearSafetyTimer();

    // Set streaming state
    if (window.HrApp) {
      window.HrApp.setState('chat.isStreaming', true);
    }

    // Show bot placeholder in chat
    if (window.HrChat) {
      window.HrChat.addBotMessagePlaceholder(lastKnownAgent);
    }

    // Reset pending sources
    pendingSources = [];

    // Reset agent tracking for new stream
    lastKnownAgent = null;

    // Start the SSE stream (orchestrator endpoint for multi-agent routing)
    currentController = window.HrApi.apiStream('/orchestrator/query', {
      query: query,
      session_id: sessionId || null
    }, {
      onRoute: function (data) {
        var agentName = data.agent_name || null;
        // Detect agent transition (different agent than last message)
        if (lastKnownAgent && agentName && agentName !== lastKnownAgent) {
          if (window.HrChat && window.HrChat.showAgentTransition) {
            window.HrChat.showAgentTransition(agentName);
          }
        }
        lastKnownAgent = agentName;
        // Update active agent indicator
        if (window.HrApp) {
          window.HrApp.setState('chat.activeAgent', agentName);
        }
        if (window.HrChat && window.HrChat.showActiveAgentIndicator) {
          window.HrChat.showActiveAgentIndicator(agentName);
        }
      },
      onToken: function (token) {
        if (window.HrChat) {
          window.HrChat.appendToken(token);
        }
      },
      onSources: function (sources) {
        pendingSources = sources || [];
      },
      onDone: function (data) {
        _clearSafetyTimer();
        _handleDone(data);
      },
      onError: function (errorData) {
        _clearSafetyTimer();
        _handleError(errorData);
      }
    });

    // Safety timeout: force-reset after 60s no matter what
    safetyTimer = setTimeout(function () {
      console.warn('[stream] Safety timeout — forcing stream reset');
      if (currentController) {
        try { currentController.abort(); } catch (e) {}
      }
      currentController = null;
      pendingSources = [];
      lastKnownAgent = null;
      if (window.HrApp) {
        window.HrApp.setState('chat.isStreaming', false);
      }
      if (window.HrChat) {
        window.HrChat.showStreamError('Response timed out. Please try again.');
        window.HrChat.enableInput();
      }
    }, 60000);

    return currentController;
  }

  function _clearSafetyTimer() {
    if (safetyTimer) {
      clearTimeout(safetyTimer);
      safetyTimer = null;
    }
  }

  /**
   * Stop an active stream.
   */
  function stopStream(controller) {
    _clearSafetyTimer();
    if (controller) {
      try {
        controller.abort();
      } catch (e) {
        // ignore
      }
    }
    currentController = null;
    pendingSources = [];
    lastKnownAgent = null;

    if (window.HrApp) {
      window.HrApp.setState('chat.isStreaming', false);
    }

    // Re-enable input
    if (window.HrChat) {
      window.HrChat.enableInput();
    }
  }

  /**
   * Handle successful stream completion.
   */
  function _handleDone(data) {
    // Use agent_name from done event, falling back to route event
    var agentName = data.agent_name || lastKnownAgent || null;

    // Finalize the bot message
    if (window.HrChat) {
      window.HrChat.finalizeBotMessage(
        data.message_id,
        pendingSources,
        data.confidence,
        agentName
      );
      // Safety net — re-enable input even if finalizeBotMessage bailed early
      window.HrChat.enableInput();
    }

    // If this was a new session, update active session ID
    if (data.session_id && window.HrApp) {
      var currentSessionId = window.HrApp.getState('chat.activeSessionId');
      if (currentSessionId !== data.session_id) {
        window.HrApp.setState('chat.activeSessionId', data.session_id);
        localStorage.setItem('hr_active_session', data.session_id);

        // Reload sessions to show new session in sidebar
        if (window.HrSessions) {
          window.HrSessions.loadSessions();
        }
      } else {
        // Just update the preview for the existing session
        if (window.HrSessions) {
          window.HrSessions.updateSessionInList(data.session_id);
        }
      }
    }

    // Reset state
    currentController = null;
    pendingSources = [];
    lastKnownAgent = null;

    if (window.HrApp) {
      window.HrApp.setState('chat.isStreaming', false);
    }
  }

  /**
   * Handle stream error.
   */
  function _handleError(errorData) {
    if (window.HrChat) {
      window.HrChat.showStreamError(errorData.detail || 'An error occurred while generating a response.');
      window.HrChat.enableInput();
    }

    currentController = null;
    pendingSources = [];
    lastKnownAgent = null;

    if (window.HrApp) {
      window.HrApp.setState('chat.isStreaming', false);
    }
  }

  /**
   * Check if a stream is currently active.
   */
  function isStreaming() {
    return currentController !== null;
  }

  // Expose module
  window.HrStream = {
    startStream: startStream,
    stopStream: stopStream,
    isStreaming: isStreaming
  };
})();
