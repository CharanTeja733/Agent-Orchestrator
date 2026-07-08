/**
 * HR Q&A Agent — Utility Functions
 * Defines: window.HrUtils
 * Pure functions only — no DOM access, no side effects.
 */

(function () {
  'use strict';

  /**
   * Escape HTML entities to prevent XSS.
   */
  function escapeHtml(str) {
    if (!str) return '';
    const map = {
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;'
    };
    return String(str).replace(/[&<>"']/g, function (ch) { return map[ch]; });
  }

  /**
   * Format ISO timestamp to human-readable date.
   * e.g. "Jul 1, 2026 10:30 AM"
   */
  function formatDate(isoString) {
    if (!isoString) return '';
    try {
      var d = new Date(isoString);
      return d.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
        hour12: true
      });
    } catch (e) {
      return isoString;
    }
  }

  /**
   * Format ISO timestamp to relative time.
   * "Just now", "5 min ago", "2 hr ago", "Yesterday", "3 days ago", or date.
   */
  function formatRelativeTime(isoString) {
    if (!isoString) return '';
    try {
      var now = new Date();
      var then = new Date(isoString);
      var diffMs = now - then;
      var diffSec = Math.floor(diffMs / 1000);
      var diffMin = Math.floor(diffSec / 60);
      var diffHr = Math.floor(diffMin / 60);
      var diffDays = Math.floor(diffHr / 24);

      if (diffSec < 60) return 'Just now';
      if (diffMin < 60) return diffMin + ' min ago';
      if (diffHr < 24) return diffHr + ' hr ago';
      if (diffDays === 1) return 'Yesterday';
      if (diffDays < 7) return diffDays + ' days ago';
      return formatDate(isoString);
    } catch (e) {
      return isoString;
    }
  }

  /**
   * Truncate text at word boundary with ellipsis.
   */
  function truncateText(text, maxLength) {
    if (!text) return '';
    if (text.length <= maxLength) return text;
    var truncated = text.substring(0, maxLength);
    var lastSpace = truncated.lastIndexOf(' ');
    if (lastSpace > maxLength * 0.7) {
      truncated = truncated.substring(0, lastSpace);
    }
    return truncated + '...';
  }

  /**
   * Convert basic markdown to safe HTML.
   * Escapes HTML first, then applies formatting — safe for innerHTML.
   */
  function simpleMarkdown(text) {
    if (!text) return '';
    var html = escapeHtml(text);

    // Inline code (must be before bold/italic)
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

    // Bold
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

    // Italic
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');

    // Split into blocks by double newline
    var blocks = html.split(/\n\n+/);
    var result = [];

    for (var i = 0; i < blocks.length; i++) {
      var block = blocks[i].trim();
      if (!block) continue;

      var lines = block.split('\n');

      // Check for unordered list (lines starting with • or -)
      var isUnordered = lines.every(function (l) {
        return /^[•\-]\s/.test(l.trim());
      });

      // Check for ordered list
      var isOrdered = lines.every(function (l) {
        return /^\d+[.)]\s/.test(l.trim());
      });

      if (isUnordered && lines.length > 0) {
        var items = lines.map(function (l) {
          return '<li>' + l.trim().replace(/^[•\-]\s*/, '') + '</li>';
        }).join('');
        result.push('<ul>' + items + '</ul>');
      } else if (isOrdered && lines.length > 0) {
        var items2 = lines.map(function (l) {
          return '<li>' + l.trim().replace(/^\d+[.)]\s*/, '') + '</li>';
        }).join('');
        result.push('<ol>' + items2 + '</ol>');
      } else {
        // Regular paragraph with inline line breaks
        var para = lines.join('<br>');
        result.push('<p>' + para + '</p>');
      }
    }

    return result.join('');
  }

  /**
   * Debounce function calls (trailing edge).
   */
  function debounce(fn, delay) {
    var timer = null;
    return function () {
      var context = this;
      var args = arguments;
      if (timer) clearTimeout(timer);
      timer = setTimeout(function () {
        fn.apply(context, args);
      }, delay);
    };
  }

  /**
   * Generate a temporary unique ID for UI elements.
   */
  function generateId() {
    return 'el-' + Math.random().toString(36).substring(2, 10);
  }

  /**
   * Return CSS class for confidence level.
   */
  function getConfidenceColor(confidence) {
    switch (confidence) {
      case 'high': return 'badge-high';
      case 'medium': return 'badge-medium';
      case 'low': return 'badge-low';
      default: return 'badge-no-match';
    }
  }

  /**
   * Return human-readable confidence label.
   */
  function getConfidenceLabel(confidence) {
    switch (confidence) {
      case 'high': return 'High Confidence';
      case 'medium': return 'Medium Confidence';
      case 'low': return 'Low Confidence';
      case 'no_match': return 'No Match';
      default: return 'Unknown';
    }
  }

  /**
   * Return formatted role display text.
   */
  function getRoleBadge(role) {
    switch (role) {
      case 'hr_admin': return 'HR Admin';
      case 'manager': return 'Manager';
      case 'employee': return 'Employee';
      default: return role || 'User';
    }
  }

  /**
   * Return CSS class for role badge.
   */
  function getRoleClass(role) {
    switch (role) {
      case 'hr_admin': return 'role-hr_admin';
      case 'manager': return 'role-manager';
      case 'employee': return 'role-employee';
      default: return 'role-employee';
    }
  }

  // ---- Agent Configuration ----

  var AGENT_CONFIG = {
    hr: { icon: '\u{1F4CB}', label: 'HR Agent', cssClass: 'hr', color: '#2563EB' },
    it: { icon: '\u{1F4BB}', label: 'IT Support', cssClass: 'it', color: '#059669' },
    orchestrator: { icon: '\u{1F916}', label: 'Assistant', cssClass: 'orchestrator', color: '#6B7280' }
  };

  var AGENT_DEFAULT = AGENT_CONFIG.orchestrator;

  function getAgentConfig(agentName) {
    if (!agentName) return AGENT_DEFAULT;
    return AGENT_CONFIG[agentName] || AGENT_DEFAULT;
  }

  // Expose module
  window.HrUtils = {
    escapeHtml: escapeHtml,
    formatDate: formatDate,
    formatRelativeTime: formatRelativeTime,
    truncateText: truncateText,
    simpleMarkdown: simpleMarkdown,
    debounce: debounce,
    generateId: generateId,
    getConfidenceColor: getConfidenceColor,
    getConfidenceLabel: getConfidenceLabel,
    getRoleBadge: getRoleBadge,
    getRoleClass: getRoleClass,
    getAgentConfig: getAgentConfig,
    AGENT_CONFIG: AGENT_CONFIG
  };
})();
