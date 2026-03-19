/**
 * Meshtastic Web Client - Sessions Module: Disconnect, session mappings, auto-restore, resume, delete
 */

Object.assign(MeshtasticClient.prototype, {

async disconnect() {

    try {
        this.logCommunication('OUT', 'Disconnecting from Meshtastic node', 'warning');

        // Stop heartbeat and stats refresh
        this._stopHeartbeat();
        this._stopStatsRefresh();

        // Close WebSocket connection only - do NOT delete the server session
        // so that session and message history are preserved for reconnection
        if (this.ws) {
            try { this.ws.close(); } catch (_e) { /* ignore */ }
            this.ws = null;
        }

        // Keep the localStorage session mapping so user can reconnect later
        // with the same session_id and restore message history.
        // The "Clear Session" (X) button on the login screen calls deleteSession()
        // which properly cleans up the server session and localStorage data.

        this.logCommunication('IN', 'Disconnected (session preserved)', 'success');

        // Reset runtime state but preserve sessionId reference for reconnection
        this.sessionId = null;
        this.connected = false;
        this.meshtasticHost = null;
        this.meshtasticPort = null;
        this._initialDataLoaded = false;
        this._titleRetried = false;

        // Update UI
        this.updateConnectionStatus('disconnected', 'Disconnected');
        this.addSystemMessage('Disconnected from Meshtastic node', 'warning');

        // Only clear ephemeral runtime data, NOT messages
        // Nodes and channels will be refreshed on reconnect
        if (this.storage) {
            this.storage.clear('nodes');
            this.storage.clear('channels');
            this.storage.clear('session_data');
            this.storage.clear('connection_status');
        }

        // Show session setup again and refresh sessions list
        document.getElementById('sessionSetup').style.display = 'flex';
        document.getElementById('mainApp').style.display = 'none';
        this.loadExistingSessions();

        // Reset browser tab title
        document.title = 'Im Mesh Client';

    } catch (error) {
        console.error('Disconnect error:', error);
        this.logCommunication('IN', `Disconnect error: ${error.message}`, 'error');
        this.showMessage('Error during disconnect: ' + error.message, 'error');
    }
},

// ---- Session Management (localStorage persistence, auto-restore, existing sessions) ----

/**
 * Save a session mapping to localStorage so we can auto-restore on page reload.
 * Key is host:port -> session_id.
 */
_saveSessionMapping(host, port, sessionId) {
    try {
        const mappings = JSON.parse(localStorage.getItem('meshtastic_sessions') || '{}');
        mappings[`${host}:${port}`] = sessionId;
        localStorage.setItem('meshtastic_sessions', JSON.stringify(mappings));
        localStorage.setItem('meshtastic_last_host', host);
        localStorage.setItem('meshtastic_last_port', String(port));
    } catch (e) {
        console.error('Failed to save session mapping:', e);
    }
},

/**
 * Remove a session mapping from localStorage.
 */
_removeSessionMapping(host, port) {
    try {
        const mappings = JSON.parse(localStorage.getItem('meshtastic_sessions') || '{}');
        delete mappings[`${host}:${port}`];
        localStorage.setItem('meshtastic_sessions', JSON.stringify(mappings));
    } catch (e) {
        console.error('Failed to remove session mapping:', e);
    }
},

/**
 * Remove a session mapping by session ID (for delete from login page).
 */
_removeSessionMappingById(sessionId) {
    try {
        const mappings = JSON.parse(localStorage.getItem('meshtastic_sessions') || '{}');
        for (const key of Object.keys(mappings)) {
            if (mappings[key] === sessionId) {
                delete mappings[key];
            }
        }
        localStorage.setItem('meshtastic_sessions', JSON.stringify(mappings));
    } catch (e) {
        console.error('Failed to remove session mapping by ID:', e);
    }
},

/**
 * Try to auto-restore the last session on page load.
 * If the server still has the session active, skip the login screen.
 */
async _tryAutoRestore() {
    try {
        const lastHost = localStorage.getItem('meshtastic_last_host');
        const lastPort = localStorage.getItem('meshtastic_last_port');
        if (!lastHost || !lastPort) return;

        const mappings = JSON.parse(localStorage.getItem('meshtastic_sessions') || '{}');
        const sessionId = mappings[`${lastHost}:${lastPort}`];
        if (!sessionId) return;

        // Check if this session is still alive on the server
        const response = await fetch(`/api/sessions/${sessionId}`);
        if (!response.ok) {
            // Session is gone from server (e.g. server restarted) - but keep
            // the localStorage mapping so the session_id is reused on next login,
            // preserving message history.
            return;
        }

        const data = await response.json();
        if (!data.success) return;

        const connected = data.data?.connection?.connected || false;
        if (!connected) return;

        // Session is alive and connected - auto-restore it
        this.sessionId = sessionId;
        this.meshtasticHost = lastHost;
        this.meshtasticPort = parseInt(lastPort);

        this.storage = new MeshtasticStorage(this.sessionId);
        this.showMainApp(lastHost, parseInt(lastPort), 'Auto-restored');
        this.connectWebSocket();

        setTimeout(() => {
            if (!this._initialDataLoaded) {
                this.loadInitialData();
            }
        }, 3000);

    } catch (e) {
        console.error('Auto-restore failed:', e);
    }
},

/**
 * Load existing sessions from the server and populate the login screen list.
 */
async loadExistingSessions() {
    const container = document.getElementById('existingSessions');
    if (!container) return;

    try {
        const serverSessions = await this._fetchServerSessions();
        const merged = this._mergeSessionSources(serverSessions);

        if (merged.length === 0) {
            container.innerHTML = '<p class="sessions-empty">No saved sessions</p>';
            return;
        }

        container.innerHTML = '';
        for (const s of merged) {
            container.appendChild(this._createSessionListItem(s));
        }

    } catch (e) {
        console.error('Failed to load existing sessions:', e);
        container.innerHTML = '<p class="sessions-empty">Error loading sessions</p>';
    }
},

/** Fetch sessions from server API, keyed by host:port. */
async _fetchServerSessions() {
    const serverSessions = {};
    try {
        const response = await fetch('/api/sessions');
        if (response.ok) {
            const data = await response.json();
            const sessions = data.data?.sessions || {};
            for (const s of Object.values(sessions)) {
                const key = `${s.meshtastic_host}:${s.meshtastic_port}`;
                serverSessions[key] = s;
            }
        }
    } catch (e) {
        console.error('Failed to fetch server sessions:', e);
    }
    return serverSessions;
},

/** Merge localStorage session mappings with server sessions. */
_mergeSessionSources(serverSessions) {
    const mappings = JSON.parse(localStorage.getItem('meshtastic_sessions') || '{}');
    const merged = [];
    const seen = new Set();

    for (const [hostPort, sessionId] of Object.entries(mappings)) {
        const [host, portStr] = hostPort.split(':');
        const port = parseInt(portStr) || 4403;
        const serverInfo = serverSessions[hostPort] || null;
        merged.push({
            id: sessionId,
            host: host,
            port: port,
            connected: serverInfo ? (serverInfo.connected || false) : false,
            lastAccessed: serverInfo?.last_accessed || null,
            fromServer: !!serverInfo
        });
        seen.add(hostPort);
    }

    for (const [hostPort, s] of Object.entries(serverSessions)) {
        if (!seen.has(hostPort)) {
            merged.push({
                id: s.id,
                host: s.meshtastic_host,
                port: s.meshtastic_port,
                connected: s.connected || false,
                lastAccessed: s.last_accessed || null,
                fromServer: true
            });
        }
    }

    return merged;
},

/** Create a DOM element for a session list item. */
_createSessionListItem(s) {
    const lastAccessedStr = s.lastAccessed
        ? new Date(s.lastAccessed).toLocaleTimeString()
        : '';
    const statusText = s.connected ? 'Connected' : (s.fromServer ? 'Disconnected' : 'Saved');

    const item = document.createElement('div');
    item.className = 'session-item';
    item.innerHTML = `
        <div class="session-item-status ${s.connected ? 'connected' : ''}"></div>
        <div class="session-item-info" data-session-id="${this.escapeHtml(s.id)}" data-host="${this.escapeHtml(s.host)}" data-port="${this.escapeHtml(String(s.port))}">
            <div class="session-item-host">${this.escapeHtml(s.host)}:${this.escapeHtml(String(s.port))}</div>
            <div class="session-item-meta">${statusText}${lastAccessedStr ? ' &middot; ' + this.escapeHtml(lastAccessedStr) : ''}</div>
        </div>
        <div class="session-item-actions">
            <button class="btn-session-delete" data-session-id="${s.id}" title="Clear session and message history">&#x2715;</button>
        </div>
    `;

    const infoEl = item.querySelector('.session-item-info');
    infoEl.addEventListener('click', () => {
        this.resumeSession(s.id, s.host, s.port);
    });

    const deleteBtn = item.querySelector('.btn-session-delete');
    deleteBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        this.deleteSession(s.id, s.host, s.port);
    });

    return item;
},

/**
 * Resume an existing session from the login page.
 * Sets the host/port fields and triggers handleLogin which will reuse the session.
 */
async resumeSession(sessionId, host, port) {
    // Set the form fields so handleLogin picks them up
    const hostEl = document.getElementById('host');
    const portEl = document.getElementById('port');
    if (hostEl) hostEl.value = host;
    if (portEl) portEl.value = port;

    // handleLogin will call POST /api/sessions which reuses the existing session
    await this.handleLogin();
},

/**
 * Delete a session from the server and clean up ALL localStorage data
 * including message history. This is the "Clear Session" action.
 */
async deleteSession(sessionId, host, port) {
    // Confirm before clearing session and all message history
    if (!confirm(`Clear session for ${host}:${port}?\n\nThis will permanently delete all message history for this node.`)) {
        return;
    }

    try {
        // Try to delete on server (may 404 if server was restarted - that's OK)
        try {
            await fetch(`/api/sessions/${sessionId}?delete_data=true`, {
                method: 'DELETE'
            });
        } catch (_fetchErr) {
            // Server unreachable - still clean up localStorage below
        }

        // Always clean up localStorage regardless of server response
        this._removeSessionMappingById(sessionId);

        // Clear last-host/port if they match the deleted session
        const lastHost = localStorage.getItem('meshtastic_last_host');
        const lastPort = localStorage.getItem('meshtastic_last_port');
        if (lastHost === host && String(lastPort) === String(port)) {
            localStorage.removeItem('meshtastic_last_host');
            localStorage.removeItem('meshtastic_last_port');
        }

        // Also clear the MeshtasticStorage data for this session
        const prefix = `meshtastic_${sessionId}_`;
        const keysToRemove = [];
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            if (key && key.startsWith(prefix)) {
                keysToRemove.push(key);
            }
        }
        keysToRemove.forEach(k => localStorage.removeItem(k));

        // Refresh the sessions list
        this.loadExistingSessions();

    } catch (e) {
        console.error('Failed to delete session:', e);
    }
}

});
