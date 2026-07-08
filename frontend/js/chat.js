/**
 * HR Q&A Agent — Chat Interface Module
 * Defines: window.HrChat
 * Message display, streaming UI, sources, confidence, feedback, input handling.
 */

(function () {
  'use strict';

  var currentBotMessageEl = null;
  var currentBotContentEl = null;
  var currentBotContentText = '';
  var messagesContainer = null;
  var chatInput = null;
  var sendBtn = null;
  var charCount = null;

  // ---- Send Message ----

  function sendMessage(text) {
    try {
      text = (text || '').trim();
      if (!text) return;

      // Don't send while streaming
      if (window.HrApp && window.HrApp.getState('chat.isStreaming')) {
        console.log('[chat] sendMessage blocked — isStreaming=true');
        return;
      }

      // Clear welcome message if present
      _removeWelcomeMessage();

      // Add user bubble
      addUserMessage(text);

      // Clear input
      if (chatInput) {
        chatInput.value = '';
        _autoResizeTextarea();
        _updateSendButton();
      }

      // Disable input
      _setInputEnabled(false);

      // Start streaming
      var sessionId = null;
      if (window.HrApp) {
        sessionId = window.HrApp.getState('chat.activeSessionId');
      }

      if (window.HrStream) {
        window.HrStream.startStream(text, sessionId);
      }
    } catch (e) {
      console.error('[chat] sendMessage error:', e);
      // Force re-enable input on any error
      _setInputEnabled(true);
    }
  }

  // ---- User Message ----

  function addUserMessage(text) {
    var container = _getMessagesContainer();
    if (!container) return;

    var messageEl = document.createElement('div');
    messageEl.className = 'message message-user';

    // Avatar
    var avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.textContent = _getUserInitial();
    avatar.setAttribute('aria-hidden', 'true');

    // Body
    var body = document.createElement('div');
    body.className = 'message-body';

    var bubble = document.createElement('div');
    bubble.className = 'message-bubble';

    var content = document.createElement('div');
    content.className = 'message-content';
    content.textContent = text; // textContent is safe — no XSS

    bubble.appendChild(content);
    body.appendChild(bubble);

    // Timestamp
    var time = document.createElement('span');
    time.className = 'message-time';
    time.textContent = _formatTimeNow();

    var footer = document.createElement('div');
    footer.className = 'message-footer';
    footer.appendChild(time);
    body.appendChild(footer);

    messageEl.appendChild(avatar);
    messageEl.appendChild(body);

    container.appendChild(messageEl);
    scrollToBottom();
  }

  // ---- Bot Message Placeholder (before first token) ----

  function addBotMessagePlaceholder(agentName) {
    var container = _getMessagesContainer();
    if (!container) return;

    // Remove any existing placeholder (safety)
    _removeBotPlaceholder();

    var messageEl = document.createElement('div');
    messageEl.className = 'message message-bot streaming';

    // Store agent name on element for later use (badge applied after streaming)
    if (agentName) {
      messageEl.setAttribute('data-agent', agentName);
    }

    // Avatar
    var avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.innerHTML = _botIconSVG();
    avatar.setAttribute('aria-hidden', 'true');

    // Body
    var body = document.createElement('div');
    body.className = 'message-body';

    var bubble = document.createElement('div');
    bubble.className = 'message-bubble';

    // Content area (will be filled with tokens)
    var content = document.createElement('div');
    content.className = 'message-content';

    // Typing indicator
    var typing = document.createElement('div');
    typing.className = 'typing-indicator';
    typing.setAttribute('aria-label', 'Assistant is typing...');
    typing.innerHTML = '<span></span><span></span><span></span>';

    content.appendChild(typing);
    bubble.appendChild(content);
    body.appendChild(bubble);
    messageEl.appendChild(avatar);
    messageEl.appendChild(body);

    container.appendChild(messageEl);
    scrollToBottom();

    // Store references
    currentBotMessageEl = messageEl;
    currentBotContentEl = content;
    currentBotContentText = '';
  }

  // ---- Append Token (streaming) ----

  function appendToken(token) {
    if (!currentBotMessageEl && !currentBotContentEl) {
      // No placeholder yet — create one
      addBotMessagePlaceholder();
    }

    if (!currentBotContentEl) return;

    // Remove typing indicator
    var typingIndicator = currentBotContentEl.querySelector('.typing-indicator');
    if (typingIndicator) {
      typingIndicator.remove();
    }

    // Accumulate text
    currentBotContentText += token;

    // Render markdown
    currentBotContentEl.innerHTML = window.HrUtils.simpleMarkdown(currentBotContentText);

    scrollToBottom();
  }

  // ---- Finalize Bot Message (after stream completes) ----

  function finalizeBotMessage(messageId, sources, confidence, agentName) {
    if (!currentBotMessageEl) return;

    // Read agent name from parameter or fall back to data-agent attribute
    if (!agentName) {
      agentName = currentBotMessageEl.getAttribute('data-agent') || null;
    }

    // Remove streaming class
    currentBotMessageEl.classList.remove('streaming');

    // Add message ID as data attribute
    if (messageId) {
      currentBotMessageEl.setAttribute('data-message-id', messageId);
    }

    // Add agent badge (only after streaming completes)
    if (agentName) {
      _addAgentBadge(currentBotMessageEl, agentName);
      var agentClass = (window.HrUtils && window.HrUtils.getAgentConfig)
        ? window.HrUtils.getAgentConfig(agentName).cssClass
        : 'hr';
      currentBotMessageEl.classList.add('message-' + agentClass);
    }

    // Build footer
    var footer = document.createElement('div');
    footer.className = 'message-footer';

    // Confidence badge
    if (confidence) {
      var badge = _createConfidenceBadge(confidence);
      footer.appendChild(badge);
    }

    // Timestamp
    var time = document.createElement('span');
    time.className = 'message-time';
    time.textContent = _formatTimeNow();
    footer.appendChild(time);

    // Append footer to body
    var body = currentBotMessageEl.querySelector('.message-body');
    if (body) {
      body.appendChild(footer);
    }

    // Add source citations (below the message)
    if (sources && sources.length > 0) {
      var sourcesSection = _createSourcesSection(sources);
      if (body) {
        body.appendChild(sourcesSection);
      }
    }

    // Add feedback buttons
    if (messageId) {
      var feedbackEl = _createFeedbackButtons(messageId, null);
      if (body) {
        body.appendChild(feedbackEl);
      }
    }

    // Clear references
    currentBotMessageEl = null;
    currentBotContentEl = null;
    currentBotContentText = '';

    // Re-enable input
    _setInputEnabled(true);

    scrollToBottom();
  }

  // ---- Agent Badge ----

  function _addAgentBadge(messageEl, agentName) {
    var config = window.HrUtils.getAgentConfig(agentName);
    var badge = document.createElement('div');
    badge.className = 'agent-badge agent-badge-' + config.cssClass;
    badge.textContent = config.icon + ' ' + config.label;
    var body = messageEl.querySelector('.message-body');
    if (body) {
      body.insertBefore(badge, body.firstChild);
    }
    return badge;
  }

  // ---- Agent Transition ----

  function showAgentTransition(agentName) {
    var container = _getMessagesContainer();
    if (!container) return;
    var config = window.HrUtils.getAgentConfig(agentName);
    var transitionEl = document.createElement('div');
    transitionEl.className = 'agent-transition';
    transitionEl.textContent = '\u{1F504} Switched to ' + config.icon + ' ' + config.label;
    container.appendChild(transitionEl);
    scrollToBottom();
  }

  // ---- Active Agent Indicator ----

  function showActiveAgentIndicator(agentName) {
    var indicator = document.getElementById('active-agent-indicator');
    if (!indicator) return;
    if (!agentName) {
      indicator.classList.add('hidden');
      indicator.className = 'active-agent-indicator hidden';
      return;
    }
    var config = window.HrUtils.getAgentConfig(agentName);
    indicator.classList.remove('hidden');
    indicator.className = 'active-agent-indicator active-agent-' + config.cssClass;
    indicator.innerHTML = 'Currently talking to: ' + config.icon + ' <strong>' +
      window.HrUtils.escapeHtml(config.label) + '</strong>';
  }

  // ---- Sources Section ----

  function _createSourcesSection(sources) {
    var section = document.createElement('div');
    section.className = 'sources-section';

    // Toggle header
    var toggle = document.createElement('button');
    toggle.className = 'sources-toggle';
    toggle.setAttribute('aria-expanded', 'false');
    toggle.innerHTML = '<span>&#x1F4C4; Sources (' + sources.length + ')</span>' +
      '<span class="sources-toggle-icon">&#x25BC;</span>';

    // Sources list (collapsed by default)
    var list = document.createElement('div');
    list.className = 'sources-list';

    for (var i = 0; i < sources.length; i++) {
      var src = sources[i];
      var item = document.createElement('div');
      item.className = 'source-item';

      var header = document.createElement('div');
      header.className = 'source-item-header';

      var num = document.createElement('span');
      num.className = 'source-number';
      num.textContent = (i + 1) + '.';

      var doc = document.createElement('span');
      doc.className = 'source-doc';
      doc.textContent = window.HrUtils.escapeHtml(src.document || 'Unknown Document');

      header.appendChild(num);
      header.appendChild(doc);
      item.appendChild(header);

      // Location
      if (src.page || src.section) {
        var location = document.createElement('div');
        location.className = 'source-location';
        var locParts = [];
        if (src.page) locParts.push('Page ' + src.page);
        if (src.section) locParts.push(src.section);
        location.textContent = locParts.join(', ');
        item.appendChild(location);
      }

      // Excerpt
      if (src.excerpt) {
        var excerpt = document.createElement('div');
        excerpt.className = 'source-excerpt';
        excerpt.textContent = window.HrUtils.truncateText(src.excerpt, 300);
        item.appendChild(excerpt);
      }

      list.appendChild(item);
    }

    // Toggle behavior
    toggle.addEventListener('click', function () {
      var expanded = section.classList.toggle('expanded');
      toggle.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    });

    section.appendChild(toggle);
    section.appendChild(list);

    return section;
  }

  // ---- Confidence Badge ----

  function _createConfidenceBadge(confidence) {
    var badge = document.createElement('span');
    badge.className = 'badge-confidence ' + window.HrUtils.getConfidenceColor(confidence);
    badge.textContent = window.HrUtils.getConfidenceLabel(confidence);
    return badge;
  }

  // ---- Feedback Buttons (Feature 11) ----

  function _createFeedbackButtons(messageId, existingFeedback) {
    var container = document.createElement('div');
    container.className = 'feedback-buttons';

    var currentRating = existingFeedback ? existingFeedback.rating : null;

    var thumbsUp = document.createElement('button');
    thumbsUp.className = 'feedback-btn';
    thumbsUp.innerHTML = '&#x1F44D;';
    thumbsUp.setAttribute('aria-label', 'Thumbs up — helpful response');
    thumbsUp.setAttribute('title', 'Helpful');

    var thumbsDown = document.createElement('button');
    thumbsDown.className = 'feedback-btn';
    thumbsDown.innerHTML = '&#x1F44E;';
    thumbsDown.setAttribute('aria-label', 'Thumbs down — not helpful');
    thumbsDown.setAttribute('title', 'Not helpful');

    // Restore existing state
    if (currentRating === 'positive') {
      thumbsUp.classList.add('active', 'positive');
      thumbsDown.disabled = true;
    } else if (currentRating === 'negative') {
      thumbsDown.classList.add('active', 'negative');
      thumbsUp.disabled = true;
    }

    // ---- Vote handlers ----

    function clearState() {
      currentRating = null;
      thumbsUp.classList.remove('active', 'positive');
      thumbsDown.classList.remove('active', 'negative');
      thumbsUp.disabled = false;
      thumbsDown.disabled = false;
      // Remove any reason panel
      var panel = container.querySelector('.feedback-reason-panel');
      if (panel) { panel.remove(); }
    }

    function setState(rating) {
      currentRating = rating;
      if (rating === 'positive') {
        thumbsUp.classList.add('active', 'positive');
        thumbsDown.classList.remove('active', 'negative');
        thumbsDown.disabled = true;
        thumbsUp.disabled = false;
      } else if (rating === 'negative') {
        thumbsDown.classList.add('active', 'negative');
        thumbsUp.classList.remove('active', 'positive');
        thumbsUp.disabled = true;
        thumbsDown.disabled = false;
      }
    }

    async function handleThumbsUp() {
      if (currentRating === 'positive') {
        // Toggle off — resubmit as clear (no-op: re-submit as positive again,
        // but visually it has no effect on server)
        clearState();
        await _submitFeedback(messageId, 'positive', null, null);
        window.HrApp.showToast('Feedback removed', 'info');
      } else {
        // Switch from negative or submit new
        setState('positive');
        // Remove any open reason panel
        var panel = container.querySelector('.feedback-reason-panel');
        if (panel) { panel.remove(); }
        try {
          await _submitFeedback(messageId, 'positive', null, null);
          window.HrApp.showToast('Thank you for your feedback!', 'success');
        } catch (e) {
          // Revert on failure
          clearState();
          window.HrApp.showToast('Failed to submit feedback', 'error');
        }
      }
    }

    async function handleThumbsDown() {
      if (currentRating === 'negative') {
        // Toggle off
        clearState();
        await _submitFeedback(messageId, 'negative', null, null);
        window.HrApp.showToast('Feedback removed', 'info');
      } else {
        // Show reason panel before submitting
        _createNegativeReasonPanel(container, async function (reason, comment) {
          setState('negative');
          try {
            await _submitFeedback(messageId, 'negative', reason, comment);
            window.HrApp.showToast(
              'Thank you! Your feedback helps us improve.', 'success'
            );
          } catch (e) {
            clearState();
            window.HrApp.showToast('Failed to submit feedback', 'error');
          }
        }, function () {
          // Cancelled — revert if was switching from positive
          if (currentRating === 'positive') {
            // leave as-is
          }
        });
      }
    }

    thumbsUp.addEventListener('click', handleThumbsUp);
    thumbsDown.addEventListener('click', handleThumbsDown);

    container.appendChild(thumbsUp);
    container.appendChild(thumbsDown);

    return container;
  }

  // ---- Negative feedback reason panel ----

  function _createNegativeReasonPanel(container, onSubmit, onCancel) {
    // Remove any existing panel
    var existing = container.querySelector('.feedback-reason-panel');
    if (existing) { existing.remove(); }

    var reasons = [
      { value: 'incorrect_information', label: 'Incorrect information' },
      { value: 'incomplete_answer', label: 'Incomplete answer' },
      { value: 'unclear_response', label: 'Unclear response' },
      { value: 'irrelevant_sources', label: 'Irrelevant sources' },
      { value: 'outdated_information', label: 'Outdated information' },
      { value: 'other', label: 'Other' }
    ];

    var panel = document.createElement('div');
    panel.className = 'feedback-reason-panel';

    var header = document.createElement('div');
    header.className = 'feedback-reason-header';
    header.textContent = 'What was wrong with this answer?';
    panel.appendChild(header);

    var optionsDiv = document.createElement('div');
    optionsDiv.className = 'feedback-reason-options';

    var selectedReason = null;
    for (var i = 0; i < reasons.length; i++) {
      (function (reason) {
        var label = document.createElement('label');
        label.className = 'feedback-reason-option';
        var radio = document.createElement('input');
        radio.type = 'radio';
        radio.name = 'feedback-reason-' + Date.now();
        radio.value = reason.value;
        radio.addEventListener('change', function () {
          selectedReason = reason.value;
        });
        label.appendChild(radio);
        label.appendChild(document.createTextNode(' ' + reason.label));
        optionsDiv.appendChild(label);
      })(reasons[i]);
    }
    panel.appendChild(optionsDiv);

    var textarea = document.createElement('textarea');
    textarea.className = 'feedback-comment';
    textarea.placeholder = 'Optional: provide more detail...';
    textarea.maxLength = 500;
    textarea.rows = 2;
    panel.appendChild(textarea);

    var actions = document.createElement('div');
    actions.className = 'feedback-reason-actions';

    var submitBtn = document.createElement('button');
    submitBtn.className = 'feedback-submit-btn';
    submitBtn.textContent = 'Submit';
    submitBtn.addEventListener('click', function () {
      if (!selectedReason) {
        window.HrApp.showToast('Please select a reason', 'warning');
        return;
      }
      var comment = textarea.value.trim() || null;
      panel.remove();
      onSubmit(selectedReason, comment);
    });
    actions.appendChild(submitBtn);

    var cancelBtn = document.createElement('button');
    cancelBtn.className = 'feedback-cancel-btn';
    cancelBtn.textContent = 'Cancel';
    cancelBtn.addEventListener('click', function () {
      panel.remove();
      if (onCancel) { onCancel(); }
    });
    actions.appendChild(cancelBtn);

    panel.appendChild(actions);
    container.appendChild(panel);
  }

  async function _submitFeedback(messageId, rating, reason, comment) {
    var body = {
      message_id: messageId,
      rating: rating
    };
    if (reason) { body.reason = reason; }
    if (comment) { body.comment = comment; }
    await window.HrApi.apiPost('/feedback', body);
  }

  // ---- Render Messages (history, non-streaming) ----

  function renderMessages(messages) {
    var container = _getMessagesContainer();
    if (!container) return;

    clearChat();

    if (!messages || messages.length === 0) {
      return;
    }

    for (var i = 0; i < messages.length; i++) {
      var msg = messages[i];
      var el = _createMessageElement(msg);
      container.appendChild(el);
    }

    scrollToBottom();
  }

  function _createMessageElement(msg) {
    var isUser = msg.role === 'user';
    var messageEl = document.createElement('div');
    messageEl.className = 'message ' + (isUser ? 'message-user' : 'message-bot');
    if (msg.id) {
      messageEl.setAttribute('data-message-id', msg.id);
    }

    // Avatar
    var avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    if (isUser) {
      avatar.textContent = _getUserInitial();
    } else {
      avatar.innerHTML = _botIconSVG();
    }
    avatar.setAttribute('aria-hidden', 'true');

    // Body
    var body = document.createElement('div');
    body.className = 'message-body';

    var bubble = document.createElement('div');
    bubble.className = 'message-bubble';

    var content = document.createElement('div');
    content.className = 'message-content';
    if (isUser) {
      content.textContent = msg.content;
    } else {
      content.innerHTML = window.HrUtils.simpleMarkdown(msg.content);
    }

    bubble.appendChild(content);
    body.appendChild(bubble);

    // Footer
    var footer = document.createElement('div');
    footer.className = 'message-footer';

    // Confidence (bot only)
    if (!isUser && msg.confidence) {
      var badge = _createConfidenceBadge(msg.confidence);
      footer.appendChild(badge);
    }

    // Timestamp
    var time = document.createElement('span');
    time.className = 'message-time';
    time.textContent = window.HrUtils.formatDate(msg.created_at);
    footer.appendChild(time);

    body.appendChild(footer);

    // Sources (bot only, shown below message)
    if (!isUser && msg.sources && msg.sources.length > 0) {
      var sourcesSection = _createSourcesSection(msg.sources);
      body.appendChild(sourcesSection);
    }

    // Feedback (bot only)
    if (!isUser && msg.id) {
      var feedbackEl = _createFeedbackButtons(msg.id, msg.feedback || null);
      body.appendChild(feedbackEl);
    }

    // Agent badge (bot only, for message history)
    if (!isUser && msg.agent_name) {
      _addAgentBadge(messageEl, msg.agent_name);
      var agentClass2 = (window.HrUtils && window.HrUtils.getAgentConfig)
        ? window.HrUtils.getAgentConfig(msg.agent_name).cssClass
        : 'hr';
      messageEl.classList.add('message-' + agentClass2);
    }

    messageEl.appendChild(avatar);
    messageEl.appendChild(body);

    return messageEl;
  }

  // ---- Welcome Message ----

  function showWelcomeMessage(userName) {
    var container = _getMessagesContainer();
    if (!container) return;

    clearChat();

    var card = document.createElement('div');
    card.className = 'welcome-card';

    var greeting = document.createElement('h2');
    greeting.textContent = 'Hello ' + window.HrUtils.escapeHtml(userName || 'there') + '! \u{1F44B}';

    var sub = document.createElement('p');
    sub.className = 'welcome-greeting';
    sub.textContent = 'I\'m your company assistant. I can connect you with:';

    // Agent introduction cards
    var agentList = document.createElement('div');
    agentList.className = 'welcome-agent-list';

    var hrCard = document.createElement('div');
    hrCard.className = 'welcome-agent-card welcome-agent-hr';
    hrCard.innerHTML = '<div class="welcome-agent-header">\u{1F4CB} <strong>HR Agent</strong></div>' +
      '<p>Policies, leave, benefits, payroll, remote work</p>';

    var itCard = document.createElement('div');
    itCard.className = 'welcome-agent-card welcome-agent-it';
    itCard.innerHTML = '<div class="welcome-agent-header">\u{1F4BB} <strong>IT Support</strong></div>' +
      '<p>Laptops, VPN, software, passwords, network issues</p>';

    agentList.appendChild(hrCard);
    agentList.appendChild(itCard);

    card.appendChild(greeting);
    card.appendChild(sub);
    card.appendChild(agentList);

    // Suggestion chips
    var chipsContainer = _createSuggestionChips();
    card.appendChild(chipsContainer);

    container.appendChild(card);

    // Hide active agent indicator on new chat
    showActiveAgentIndicator(null);
  }

  // ---- Suggestion Chips ----

  var SUGGESTION_CHIPS = [
    { text: "What's the remote work policy?", agent: "hr" },
    { text: "How many leave days do I get?", agent: "hr" },
    { text: "Tell me about health benefits", agent: "hr" },
    { text: "VPN not connecting", agent: "it" },
    { text: "Reset my password", agent: "it" },
    { text: "Laptop won't turn on", agent: "it" }
  ];

  function _createSuggestionChips() {
    var container = document.createElement('div');
    container.className = 'suggestion-chips';

    var label = document.createElement('p');
    label.className = 'suggestion-label';
    label.textContent = 'Try asking:';
    container.appendChild(label);

    var chipsRow = document.createElement('div');
    chipsRow.className = 'suggestion-chips-row';

    for (var i = 0; i < SUGGESTION_CHIPS.length; i++) {
      var chip = SUGGESTION_CHIPS[i];
      var chipEl = document.createElement('button');
      chipEl.className = 'suggestion-chip suggestion-chip-' + chip.agent;
      chipEl.textContent = chip.text;
      chipEl.addEventListener('click', (function (text) {
        return function () {
          if (chatInput) {
            chatInput.value = text;
            _autoResizeTextarea();
            _updateSendButton();
          }
          sendMessage(text);
        };
      })(chip.text));
      chipsRow.appendChild(chipEl);
    }

    container.appendChild(chipsRow);
    return container;
  }

  // ---- Stream Error ----

  function showStreamError(errorText) {
    if (!currentBotMessageEl && !currentBotContentEl) {
      addBotMessagePlaceholder();
    }

    if (currentBotMessageEl) {
      currentBotMessageEl.classList.remove('streaming');
    }

    if (currentBotContentEl) {
      var typingIndicator = currentBotContentEl.querySelector('.typing-indicator');
      if (typingIndicator) typingIndicator.remove();

      currentBotContentEl.innerHTML = '<span style="color: var(--error);">' +
        window.HrUtils.escapeHtml(errorText || 'Something went wrong. Please try again.') +
        '</span>';
    }

    // Reset
    currentBotMessageEl = null;
    currentBotContentEl = null;
    currentBotContentText = '';

    // Re-enable input
    _setInputEnabled(true);
  }

  // ---- Chat Management ----

  function clearChat() {
    var container = _getMessagesContainer();
    if (!container) return;
    container.innerHTML = '';
    _removeBotPlaceholder();
  }

  function showLoadingIndicator() {
    var container = _getMessagesContainer();
    if (!container) return;

    clearChat();

    var overlay = document.createElement('div');
    overlay.className = 'loading-overlay';
    overlay.innerHTML = '<div class="spinner"></div><span>Loading messages...</span>';
    container.appendChild(overlay);
  }

  // ---- Scroll ----

  function scrollToBottom() {
    var container = _getMessagesContainer();
    if (!container) return;
    // Use requestAnimationFrame to let DOM settle
    requestAnimationFrame(function () {
      container.scrollTop = container.scrollHeight;
    });
  }

  // ---- Input Bar ----

  function bindInputBar(containerEl) {
    if (!containerEl) return;

    chatInput = containerEl.querySelector('#chat-input');
    sendBtn = containerEl.querySelector('#send-btn');
    charCount = containerEl.querySelector('#char-count');
    var chatForm = containerEl.querySelector('#chat-form');

    if (chatInput) {
      // Auto-resize on input
      chatInput.addEventListener('input', function () {
        _autoResizeTextarea();
        _updateSendButton();
        _updateCharCount();
      });

      // Keyboard: Enter to send, Shift+Enter for newline
      chatInput.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          sendMessage(chatInput.value);
        }
      });
    }

    if (chatForm) {
      chatForm.addEventListener('submit', function (e) {
        e.preventDefault();
        if (chatInput) {
          sendMessage(chatInput.value);
        }
      });
    }

    if (sendBtn) {
      sendBtn.addEventListener('click', function () {
        if (chatInput) {
          sendMessage(chatInput.value);
        }
      });
    }
  }

  function _autoResizeTextarea() {
    if (!chatInput) return;
    chatInput.style.height = 'auto';
    var maxHeight = 120;
    var newHeight = Math.min(chatInput.scrollHeight, maxHeight);
    chatInput.style.height = newHeight + 'px';
  }

  function _updateSendButton() {
    if (!sendBtn) return;
    var hasText = chatInput && chatInput.value.trim().length > 0;
    var isStreaming = false;
    if (window.HrApp) {
      isStreaming = window.HrApp.getState('chat.isStreaming');
    }
    sendBtn.disabled = !hasText || isStreaming;
  }

  function _updateCharCount() {
    if (!charCount || !chatInput) return;
    var len = chatInput.value.length;
    charCount.textContent = len + ' / 2000';
    charCount.classList.toggle('over-limit', len > 2000);
  }

  function _setInputEnabled(enabled) {
    if (chatInput) {
      chatInput.disabled = !enabled;
      chatInput.placeholder = enabled
        ? 'Ask about HR policies or IT support...'
        : 'Waiting for response...';
    }
    if (sendBtn) {
      sendBtn.disabled = !enabled || (chatInput ? chatInput.value.trim().length === 0 : true);
    }
    // Update button state
    _updateSendButton();
  }

  function enableInput() {
    _setInputEnabled(true);
    if (chatInput) {
      chatInput.focus();
    }
  }

  // ---- Helpers ----

  function _getMessagesContainer() {
    if (!messagesContainer) {
      messagesContainer = document.getElementById('chat-messages');
    }
    return messagesContainer;
  }

  function _getUserInitial() {
    if (window.HrApp) {
      var user = window.HrApp.getState('auth.user');
      if (user && user.full_name) {
        return user.full_name.charAt(0).toUpperCase();
      }
    }
    return 'U';
  }

  function _formatTimeNow() {
    return new Date().toLocaleTimeString('en-US', {
      hour: 'numeric',
      minute: '2-digit',
      hour12: true
    });
  }

  function _removeBotPlaceholder() {
    if (currentBotMessageEl && currentBotMessageEl.parentNode) {
      currentBotMessageEl.parentNode.removeChild(currentBotMessageEl);
    }
    currentBotMessageEl = null;
    currentBotContentEl = null;
    currentBotContentText = '';
  }

  function _removeWelcomeMessage() {
    var container = _getMessagesContainer();
    if (!container) return;
    var welcome = container.querySelector('.welcome-card');
    if (welcome) {
      welcome.remove();
    }
  }

  function _botIconSVG() {
    return '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="%232563EB" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      '<path d="M12 2a4 4 0 014 4c0 2.21-1.79 4-4 4s-4-1.79-4-4a4 4 0 014-4z"/>' +
      '<path d="M12 14c-5 0-8 3-8 6v2h16v-2c0-3-3-6-8-6z"/>' +
      '<circle cx="8" cy="20" r="2" fill="%232563EB"/>' +
      '<circle cx="16" cy="20" r="2" fill="%232563EB"/>' +
      '</svg>';
  }

  // ---- Expose Module ----

  window.HrChat = {
    sendMessage: sendMessage,
    addUserMessage: addUserMessage,
    addBotMessagePlaceholder: addBotMessagePlaceholder,
    appendToken: appendToken,
    finalizeBotMessage: finalizeBotMessage,
    renderMessages: renderMessages,
    showWelcomeMessage: showWelcomeMessage,
    showStreamError: showStreamError,
    clearChat: clearChat,
    showLoadingIndicator: showLoadingIndicator,
    scrollToBottom: scrollToBottom,
    bindInputBar: bindInputBar,
    enableInput: enableInput,
    showAgentTransition: showAgentTransition,
    showActiveAgentIndicator: showActiveAgentIndicator
  };
})();
