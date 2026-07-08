/**
 * HR Q&A Agent — API Communication Layer
 * Defines: window.HrApi
 * Centralized HTTP + SSE streaming. Token-aware. Auth header auto-attached.
 */

(function () {
  'use strict';

  var accessToken = null;

  // Auto-detect base URL: nginx proxy uses /api; local dev uses direct backend URL.
  var BASE_URL = (function () {
    var host = window.location.host;
    // If served via nginx (port 80 or no port) or same origin, use /api proxy
    if (host.indexOf(':8501') === -1 && host.indexOf(':8000') === -1) {
      return '/api';
    }
    // Local dev: python http.server on 8501, backend on 8000
    return 'http://localhost:8000';
  })();

  // ---- Error Class ----

  function HrApiError(status, detail, code) {
    this.name = 'HrApiError';
    this.status = status;
    this.detail = detail || 'An unknown error occurred';
    this.code = code || null;
    this.message = this.detail;
  }
  HrApiError.prototype = Object.create(Error.prototype);
  HrApiError.prototype.constructor = HrApiError;

  // ---- Token Management ----

  function setToken(token) {
    accessToken = token;
  }

  function getToken() {
    return accessToken;
  }

  // ---- Internal Fetch Wrapper ----

  function _buildHeaders(extraHeaders) {
    var headers = extraHeaders || {};
    if (accessToken) {
      headers['Authorization'] = 'Bearer ' + accessToken;
    }
    return headers;
  }

  async function _request(method, endpoint, body, extraHeaders) {
    var url = BASE_URL + endpoint;
    var options = {
      method: method,
      headers: _buildHeaders(extraHeaders)
    };

    if (body !== undefined && body !== null) {
      options.headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(body);
    }

    try {
      var response = await fetch(url, options);

      if (response.status === 401) {
        // Dispatch event for app.js to handle token refresh
        document.dispatchEvent(new CustomEvent('app:auth-unauthorized', {
          detail: { url: url, options: options }
        }));
      }

      if (!response.ok) {
        var errorData = null;
        try {
          errorData = await response.json();
        } catch (e) {
          // ignore parse errors
        }
        var detail = (errorData && errorData.detail) ? errorData.detail : 'Request failed';
        throw new HrApiError(response.status, detail, null);
      }

      // 204 No Content
      if (response.status === 204) {
        return null;
      }

      return await response.json();
    } catch (e) {
      if (e instanceof HrApiError) {
        throw e;
      }
      // Network errors
      throw new HrApiError(0, 'Network error — unable to reach server. Check your connection.', 'network_error');
    }
  }

  // ---- Public API Methods ----

  function apiGet(endpoint, params) {
    var queryString = '';
    if (params) {
      var filtered = {};
      Object.keys(params).forEach(function (key) {
        if (params[key] !== null && params[key] !== undefined && params[key] !== '') {
          filtered[key] = params[key];
        }
      });
      var qs = new URLSearchParams(filtered).toString();
      if (qs) queryString = '?' + qs;
    }
    return _request('GET', endpoint + queryString, undefined, { 'Accept': 'application/json' });
  }

  function apiPost(endpoint, body) {
    return _request('POST', endpoint, body, { 'Accept': 'application/json' });
  }

  function apiPatch(endpoint, body) {
    return _request('PATCH', endpoint, body, { 'Accept': 'application/json' });
  }

  function apiDelete(endpoint) {
    return _request('DELETE', endpoint, undefined, { 'Accept': 'application/json' });
  }

  // ---- SSE Streaming ----

  /**
   * Stream SSE events from the backend.
   *
   * @param {string} endpoint — API endpoint (e.g. '/query/')
   * @param {object} body — JSON request body
   * @param {object} callbacks — { onToken, onSources, onDone, onError }
   * @returns {AbortController} — call .abort() to cancel the stream
   */
  function apiStream(endpoint, body, callbacks) {
    var controller = new AbortController();
    var url = BASE_URL + endpoint;

    var headers = _buildHeaders({
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream'
    });

    fetch(url, {
      method: 'POST',
      headers: headers,
      body: JSON.stringify(body),
      signal: controller.signal
    }).then(function (response) {
      if (!response.ok) {
        return response.json().then(function (err) {
          var detail = (err && err.detail) ? err.detail : 'Stream request failed';
          if (callbacks.onError) {
            callbacks.onError({ error: 'Stream error', detail: detail, error_type: 'stream_error' });
          }
        }).catch(function () {
          if (callbacks.onError) {
            callbacks.onError({ error: 'Stream error', detail: 'Failed to connect', error_type: 'stream_error' });
          }
        });
        return;
      }

      var reader = response.body.getReader();
      var decoder = new TextDecoder('utf-8');
      var buffer = '';

      function processEvents() {
        reader.read().then(function (result) {
          if (result.done) {
            // Stream ended naturally — flush remaining buffer
            if (buffer.trim()) {
              _parseSSEEvents(buffer, callbacks);
            }
            return;
          }

          // Decode chunk with stream:true to handle UTF-8 multi-byte chars
          buffer += decoder.decode(result.value, { stream: true });

          // Normalize line endings: CRLF → LF (HTTP may use either)
          buffer = buffer.replace(/\r\n/g, '\n').replace(/\r/g, '\n');

          // Split by double newline (SSE event delimiter)
          var parts = buffer.split('\n\n');
          // Last element is incomplete — keep in buffer
          buffer = parts.pop();

          // Process complete events
          for (var i = 0; i < parts.length; i++) {
            var block = parts[i].trim();
            if (block) {
              _parseSSEEvents(block, callbacks);
            }
          }

          // Continue reading
          processEvents();
        }).catch(function (err) {
          if (err.name === 'AbortError') {
            // User cancelled — clean, no action needed
            return;
          }
          // Network error or other failure
          if (callbacks.onError) {
            callbacks.onError({
              error: 'Connection lost',
              detail: 'The connection to the server was interrupted. Please try again.',
              error_type: 'network_error'
            });
          }
        });
      }

      processEvents();
    }).catch(function (err) {
      if (err.name === 'AbortError') {
        return; // clean cancel
      }
      if (callbacks.onError) {
        callbacks.onError({
          error: 'Connection error',
          detail: 'Unable to reach the server. Please check your connection.',
          error_type: 'network_error'
        });
      }
    });

    return controller;
  }

  /**
   * Parse one or more SSE events from a text block.
   * Each event has: event: <type>\n data: <json>
   * Multiple events in one block are separated by finding each "event:" line.
   */
  function _parseSSEEvents(block, callbacks) {
    // Split the block into individual events by finding "event:" or "data:" lines
    // that start a new event. Handle both named events and unnamed (default "message").
    var lines = block.split('\n');
    var currentEventType = 'message';
    var currentDataLines = [];

    function _flushEvent() {
      if (currentDataLines.length > 0) {
        var dataStr = currentDataLines.join('\n');
        try {
          var data = JSON.parse(dataStr);
          _dispatchEvent(currentEventType, data, callbacks);
        } catch (e) {
          console.warn('SSE: failed to parse JSON:', dataStr.substring(0, 100));
        }
      }
      // Reset for next event
      currentEventType = 'message';
      currentDataLines = [];
    }

    for (var i = 0; i < lines.length; i++) {
      var line = lines[i];

      // Skip comment lines (start with :)
      if (line[0] === ':') continue;

      // New event type starts — flush previous event first
      if (line.indexOf('event:') === 0) {
        _flushEvent();
        currentEventType = line.substring(6).trim() || 'message';
      } else if (line.indexOf('data:') === 0) {
        currentDataLines.push(line.substring(5).trim());
      }
      // Ignore other fields (id:, retry:)
    }

    // Flush the last event
    _flushEvent();
  }

  function _dispatchEvent(eventType, data, callbacks) {
    switch (eventType) {
      case 'token':
        if (callbacks.onToken && data.token !== undefined) {
          callbacks.onToken(data.token);
        }
        break;
      case 'sources':
        if (callbacks.onSources) {
          callbacks.onSources(data.sources || []);
        }
        break;
      case 'done':
        if (callbacks.onDone) {
          callbacks.onDone(data);
        }
        break;
      case 'error':
        if (callbacks.onError) {
          callbacks.onError(data);
        }
        break;
      case 'route':
        if (callbacks.onRoute) {
          callbacks.onRoute(data);
        }
        break;
      default:
        // Unknown event type — ignore gracefully
        break;
    }
  }

  // ---- Expose Module ----

  window.HrApi = {
    setToken: setToken,
    getToken: getToken,
    apiGet: apiGet,
    apiPost: apiPost,
    apiPatch: apiPatch,
    apiDelete: apiDelete,
    apiStream: apiStream,
    HrApiError: HrApiError,
    BASE_URL: BASE_URL
  };
})();
