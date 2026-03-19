/**
 * Im Mesh Client - Connection Module: Login, WebSocket, heartbeat, reconnect, stats refresh
 */

Object.assign(MeshtasticClient.prototype, {

setConnectionType(type) {
    const tcpFields = document.getElementById('tcpFields');
    const serialFields = document.getElementById('serialFields');
    const tcpBtn = document.getElementById('connTypeTcp');
    const serialBtn = document.getElementById('connTypeSerial');

    if (type === 'serial') {
        if (tcpFields) tcpFields.style.display = 'none';
        if (serialFields) serialFields.style.display = 'block';
        if (tcpBtn) tcpBtn.classList.remove('conn-type-active');
        if (serialBtn) serialBtn.classList.add('conn-type-active');
        this._connectionType = 'serial';
    } else {
        if (tcpFields) tcpFields.style.display = 'block';
        if (serialFields) serialFields.style.display = 'none';
        if (tcpBtn) tcpBtn.classList.add('conn-type-active');
        if (serialBtn) serialBtn.classList.remove('conn-type-active');
        this._connectionType = 'tcp';
    }
},

async handleLogin() {

    try {
        let host, port, sessionName;

        if (this._connectionType === 'serial') {
            const serialPortEl = document.getElementById('serialPort');
            const sessionNameEl = document.getElementById('session_name_serial');
            const serialPort = serialPortEl ? serialPortEl.value.trim() : '';
            sessionName = sessionNameEl ? sessionNameEl.value.trim() : '';

            if (!serialPort) throw new Error('Serial port is required');

            // For serial: host = "serial://<port>", port = 0
            host = 'serial://' + serialPort;
            port = 0;
            sessionName = sessionName || serialPort;
        } else {
            const result = this._validateLoginForm();
            host = result.host;
            port = result.port;
            sessionName = result.sessionName;
        }

        this.showMessage('Connecting...', 'info');
        this.showStatus('Connecting to Meshtastic node...');

        const data = await this._createSessionApi(host, port, sessionName);

        if (data.success) {
            this._onLoginSuccess(data, host, port, sessionName);
        } else {
            console.error('Session creation failed:', data);
            this.showMessage('Failed to create session: ' + (data.message || 'Unknown error'), 'error');
            this.showStatus('Connection failed');
        }

    } catch (error) {
        console.error('Login error:', error);
        this.showMessage('Connection failed: ' + error.message, 'error');
        this.showStatus('Connection failed');
    }
},

/** Validate login form inputs and return { host, port, sessionName }. */
_validateLoginForm() {
    const hostElement = document.getElementById('host');
    const portElement = document.getElementById('port');
    const sessionNameElement = document.getElementById('session_name');

    if (!hostElement || !portElement) {
        throw new Error('Form elements not found');
    }

    const host = hostElement.value.trim();
    const portValue = portElement.value;
    const sessionName = sessionNameElement?.value?.trim() || 'Default';

    if (!host) throw new Error('Host is required');

    const port = parseInt(portValue);
    if (isNaN(port) || port < 1 || port > 65535) {
        throw new Error('Port must be a number between 1 and 65535');
    }

    return { host, port, sessionName };
},

/** Call POST /api/sessions, passing old session ID from localStorage for reuse. */
async _createSessionApi(host, port, sessionName) {
    let oldSessionId = null;
    try {
        const mappings = JSON.parse(localStorage.getItem('meshtastic_sessions') || '{}');
        oldSessionId = mappings[`${host}:${port}`] || null;
    } catch (e) { /* ignore */ }

    const requestBody = {
        meshtastic_host: host,
        meshtastic_port: port,
        session_name: sessionName,
        session_id: oldSessionId
    };

    const response = await fetch('/api/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody)
    });

    if (!response.ok) {
        const errorText = await response.text();
        console.error('API Response error text:', errorText);
        throw new Error(`HTTP ${response.status}: ${errorText}`);
    }

    return await response.json();
},

/** Handle successful login: store session, show app, connect WebSocket. */
_onLoginSuccess(data, host, port, sessionName) {
    this.sessionId = data.data.session_id;
    this.meshtasticHost = host;
    this.meshtasticPort = port;

    const reused = data.data.reused || false;
    const msg = reused ? 'Session restored' : 'Session created successfully!';
    this.showMessage(msg, 'success');
    this.showStatus('Establishing connection...');

    this._saveSessionMapping(host, port, this.sessionId);
    this.storage = new MeshtasticStorage(this.sessionId);
    this.showMainApp(host, port, sessionName);
    this.connectWebSocket();

    setTimeout(() => {
        if (!this._initialDataLoaded) {
            this.loadInitialData();
        }
    }, 3000);
},

connectWebSocket() {
    if (!this.sessionId) {
        console.error('Cannot connect WebSocket: No session ID');
        return;
    }

    this.logCommunication('OUT', 'Initiating WebSocket connection', 'info');

    try {
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${wsProtocol}//${window.location.host}/ws/`;

        this.ws = new WebSocket(wsUrl);

    this.ws.onopen = () => {
        this.connected = true;
        const wasReconnect = this._wsReconnectAttempts > 0;
        this._resetWsReconnect();  // Reset reconnect counter on success
        this._startHeartbeat();    // Start heartbeat pings
        this._startStatsRefresh(); // Start periodic stats refresh
        this.logCommunication('IN', 'WebSocket connection established', 'success');

        // Authenticate with session ID
        const authMessage = JSON.stringify({
            type: 'auth',
            session_id: this.sessionId
        });
        this.ws.send(authMessage);
        this.logCommunication('OUT', `Authentication sent: ${authMessage}`, 'info');

        this.showMessage('Real-time connection established', 'success');
        this.updateConnectionStatus('connected', 'Connected');
        this.showStatus('Connected to ' + this.meshtasticHost + ':' + this.meshtasticPort);
        this.addSystemMessage(`Real-time connection established to ${this.meshtasticHost}:${this.meshtasticPort}`, 'success');

        // On reconnect, fetch any messages that arrived while WS was down
        if (wasReconnect) {
            this._fetchMissedMessages();
        }
    };

        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                                    this.logCommunication('IN', `WebSocket message: ${event.data}`, 'info');
                this.handleWebSocketMessage(data);
            } catch (e) {
                console.error('WebSocket message parse error:', e);
                this.logCommunication('IN', `Parse error: ${e.message}`, 'error');
            }
        };

        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            this.logCommunication('IN', `WebSocket error: ${error}`, 'error');
            this.showMessage('WebSocket connection failed', 'error');
            this.updateConnectionStatus('error', 'Connection Error');
        };

        this.ws.onclose = (event) => {
            this.connected = false;
            this._lastWsDisconnectTime = new Date().toISOString();  // Track disconnect time for missed message retrieval
            this._stopHeartbeat();     // Stop heartbeat pings
            this._stopStatsRefresh();  // Stop stats refresh
            this.logCommunication('IN', 'WebSocket connection closed', 'warning');
            this.updateConnectionStatus('disconnected', 'Disconnected');

            // Show connection lost message in the chat/messages area
            this.addConnectionLostMessage();

            // Auto-reconnect if we have a valid session
            if (this.sessionId && event.code !== 1000) {
                // 1000 = normal close (user-initiated), don't reconnect
                this._scheduleWsReconnect();
            }
        };

    } catch (error) {
        console.error('WebSocket creation error:', error);
        this.showMessage('Failed to create WebSocket: ' + error.message, 'error');
        // Also try to reconnect on creation error
        if (this.sessionId) {
            this._scheduleWsReconnect();
        }
    }
},

_scheduleWsReconnect() {
    // Clear any existing timer
    if (this._wsReconnectTimer) {
        clearTimeout(this._wsReconnectTimer);
        this._wsReconnectTimer = null;
    }

    this._wsReconnectAttempts++;

    if (this._wsReconnectAttempts > this._wsMaxReconnectAttempts) {
        this.addSystemMessage('Connection lost. Please refresh the page to reconnect.', 'error');
        return;
    }

    const delay = this._wsReconnectDelay;
    console.log(`WebSocket reconnect attempt ${this._wsReconnectAttempts} in ${delay/1000}s`);
    this.updateConnectionStatus('connecting', `Reconnecting (${this._wsReconnectAttempts})...`);

    this._wsReconnectTimer = setTimeout(() => {
        this._wsReconnectTimer = null;
        if (this.sessionId) {
            this.logCommunication('OUT', `Reconnecting WebSocket (attempt ${this._wsReconnectAttempts})`, 'warning');
            this.connectWebSocket();
        }
    }, delay);
},

_resetWsReconnect() {
    this._wsReconnectAttempts = 0;
    if (this._wsReconnectTimer) {
        clearTimeout(this._wsReconnectTimer);
        this._wsReconnectTimer = null;
    }
},

_startHeartbeat() {
    this._stopHeartbeat();
    this._heartbeatInterval = setInterval(() => {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this._lastPingSentAt = Date.now();
            this.ws.send(JSON.stringify({ type: 'ping', timestamp: this._lastPingSentAt }));

            // Set timeout - if no pong in 10s, connection is dead
            this._heartbeatTimeout = setTimeout(() => {
                this.logCommunication('IN', 'Heartbeat timeout - no pong received', 'error');
                this._lastLatencyMs = null;
                // Force close and trigger reconnect
                if (this.ws) {
                    this.ws.close(4000, 'Heartbeat timeout');
                }
            }, this._heartbeatTimeoutMs);
        }
    }, this._heartbeatIntervalMs);
},

_stopHeartbeat() {
    if (this._heartbeatInterval) {
        clearInterval(this._heartbeatInterval);
        this._heartbeatInterval = null;
    }
    if (this._heartbeatTimeout) {
        clearTimeout(this._heartbeatTimeout);
        this._heartbeatTimeout = null;
    }
},

_handlePong(data) {
    // Clear the timeout since we got a response
    if (this._heartbeatTimeout) {
        clearTimeout(this._heartbeatTimeout);
        this._heartbeatTimeout = null;
    }
    this._lastPongTime = Date.now();

    // Calculate round-trip latency
    if (this._lastPingSentAt) {
        this._lastLatencyMs = Date.now() - this._lastPingSentAt;
    }
    this._updateLatencyDisplay();
},

_updateLatencyDisplay() {
    const statusText = document.getElementById('statusText');
    if (!statusText || !this.connected) return;

    if (this._lastLatencyMs !== null && this._lastLatencyMs < 30000) {
        statusText.textContent = `Connected (${this._lastLatencyMs}ms)`;
    } else {
        statusText.textContent = 'Connected';
    }
},

_startStatsRefresh() {
    this._stopStatsRefresh();
    this._statsRefreshInterval = setInterval(() => {
        if (this.connected && this.sessionId) {
            this.updateStatistics();
        }
    }, this._statsRefreshMs);
},

_stopStatsRefresh() {
    if (this._statsRefreshInterval) {
        clearInterval(this._statsRefreshInterval);
        this._statsRefreshInterval = null;
    }
},

/**
 * Fetch messages that were received by the server while the WebSocket was disconnected.
 * Uses the last known message timestamp to request only new messages from the buffer.
 * Deduplicates against messages already in localStorage before adding.
 */
async _fetchMissedMessages() {
    if (!this.sessionId) return;

    try {
        // Determine the "since" timestamp from the last stored message
        let since = this._lastWsDisconnectTime || null;
        if (!since && this.storage) {
            // Fall back: scan stored messages for the most recent timestamp
            const prefix = `meshtastic_${this.storage.sessionId}_messages_`;
            let latestTime = '';
            for (let i = 0; i < localStorage.length; i++) {
                const key = localStorage.key(i);
                if (!key || !key.startsWith(prefix)) continue;
                try {
                    const msgs = JSON.parse(localStorage.getItem(key) || '[]');
                    for (const m of msgs) {
                        const t = m.timestamp || '';
                        if (t > latestTime) latestTime = t;
                    }
                } catch (_e) { /* ignore parse errors */ }
            }
            if (latestTime) since = latestTime;
        }

        const url = since
            ? `/api/messages/recent?since=${encodeURIComponent(since)}`
            : '/api/messages/recent';

        const response = await fetch(url, {
            headers: { 'X-Session-ID': this.sessionId }
        });

        if (!response.ok) return;

        const data = await response.json();
        if (!data.success || !data.data || !data.data.messages) return;

        const missedMessages = data.data.messages;
        if (missedMessages.length === 0) return;

        console.log(`Fetched ${missedMessages.length} missed message(s) after WS reconnect`);
        this.logCommunication('IN', `Retrieved ${missedMessages.length} missed message(s)`, 'info');

        // Process each missed message through the normal handler
        // addMessage() handles dedup via storeMessageForTarget (same timestamp + text = same msg)
        for (const msg of missedMessages) {
            this.addMessage(msg);
        }

    } catch (e) {
        console.error('Error fetching missed messages:', e);
    }
}
});
