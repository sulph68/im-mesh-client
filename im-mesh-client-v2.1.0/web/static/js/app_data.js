/**
 * Meshtastic Web Client - Data Module: WS message handler, ACK, loadInitialData, loadNodes, loadChannels
 */

Object.assign(MeshtasticClient.prototype, {

handleWebSocketMessage(data) {
    switch (data.type) {
        case 'auth_success':
                            this.addSystemMessage('Authentication successful - Loading device data...', 'success');
            this.loadInitialData();
            break;

        case 'connected':
                            break;

        case 'message':
        case 'text':
        case 'binary':
            // 'message' is the primary path from subscription callbacks.
            // 'text' and 'binary' are fallback types from the broadcast path.
            this.addMessage(data.data);
            break;

        case 'node_update':
        case 'position_update':
            this.updateNode(data.data);
            break;

        case 'channel_update':
            this.updateChannels(data.data);
            this.addSystemMessage('Channel information updated', 'info');
            break;

        case 'connection_status':
            this.handleConnectionStatusUpdate(data.data);
            break;

        case 'binary_complete':
            // Fragment reassembly complete - binary message
            this.addMessage({
                ...data.data,
                decoded: { portnum: 256, payload: data.data.payload },
                type: 'received'
            });
            break;

        case 'image_complete':
            // Decoded image from fragment reassembly
            this.addMessage({
                ...data.data,
                type: 'image_complete'
            });
            break;

        case 'ack':
            // Ack/Nak received for a sent message
            this._handleAckReceived(data.data);
            break;

        case 'pong':
            // Heartbeat response - update latency display
            this._handlePong(data);
            break;

        case 'fragment_progress':
            break;

        case 'error':
            console.error('Server error:', data.message || data.data);
            const errMsg = data.message || (data.data && data.data.error_message) || 'Unknown server error';
            this.showMessage(errMsg, 'error');
            // If session not found, stop reconnecting and show login screen
            if (errMsg.includes('Session not found')) {
                this._resetWsReconnect();
                this._wsSessionLost = true;  // Flag to prevent auto-reconnect in onclose
            }
            break;

        case 'system':
            if (data.data && data.data.message) {
                this.addSystemMessage(data.data.message, data.data.level || 'info');
            }
            break;

        default:
    }
},

handleConnectionStatusUpdate(statusData) {
    if (!statusData) return;

    if (statusData.connected) {
        this.updateConnectionStatus('connected', 'Connected');
        this.addSystemMessage('Connection to Meshtastic node established', 'success');

        // Update browser tab title with node name
        this._updateConnectionTitle();

        // If this was a reconnect, data may have been refreshed
        if (statusData.reconnected) {
            this.addSystemMessage('Data refreshed after reconnection', 'info');
            // Reload data to get fresh info
            this._initialDataLoaded = false;
            this.loadInitialData();
        }
    } else {
        if (statusData.reconnecting) {
            this.updateConnectionStatus('connecting', 'Reconnecting...');
            this.addSystemMessage('Connection lost - reconnecting automatically...', 'warning');
        } else {
            this.updateConnectionStatus('disconnected', 'Disconnected');
            this.addConnectionLostMessage();
        }
    }
},

/**
 * Handle an ack/nak received from the mesh network.
 * Finds the sent message element by packet_id, updates the DOM indicator,
 * and persists the ack status into localStorage so it survives panel switches.
 */
_handleAckReceived(ackData) {
    if (!ackData || !ackData.request_id) return;

    const requestId = ackData.request_id;
    const ackOk = ackData.ack_received;
    const errorReason = ackData.error_reason || '';

    console.log(`ACK received: requestId=${requestId} ack=${ackOk} error=${errorReason}`);

    // Dispatch to image segment ACK handler if active
    if (this._imageSegmentAckHandler) {
        this._imageSegmentAckHandler(ackData);
    }

    // Persist ack status in localStorage so it survives panel switches
    this._persistAckStatus(requestId, ackOk, errorReason);

    // Find the message element with this packet_id (may not be in DOM if on different panel)
    const container = document.getElementById('messagesContainer');
    if (!container) return;

    const msgEl = container.querySelector(`[data-packet-id="${requestId}"]`);
    if (!msgEl) {
        console.log(`No message element found for packetId=${requestId} (may be on different panel)`);
        return;
    }

    const ackDiv = msgEl.querySelector('.ack-status');
    if (!ackDiv) return;

    if (ackOk) {
        ackDiv.className = 'ack-status ack-received';
        ackDiv.textContent = 'Ack received';
    } else {
        ackDiv.className = 'ack-status ack-failed';
        ackDiv.textContent = `Nak: ${errorReason}`;
    }
},

/**
 * Persist ack status into localStorage message history.
 * Scans all message_channel_* and message_node_* keys for the matching packet_id
 * and updates ack_status so it is correct when the user switches back to that panel.
 */
_persistAckStatus(packetId, ackOk, errorReason) {
    if (!this.storage || !packetId) return;

    try {
        // Scan all stored message keys for this session
        const prefix = `meshtastic_${this.storage.sessionId}_messages_`;
        for (let i = 0; i < localStorage.length; i++) {
            const fullKey = localStorage.key(i);
            if (!fullKey || !fullKey.startsWith(prefix)) continue;

            const messages = JSON.parse(localStorage.getItem(fullKey) || '[]');
            let updated = false;

            for (let j = messages.length - 1; j >= 0; j--) {
                const msg = messages[j];
                if (msg.packet_id === packetId && msg.ack_status === 'pending') {
                    msg.ack_status = ackOk ? 'received' : 'failed';
                    if (!ackOk && errorReason) {
                        msg.ack_error = errorReason;
                    }
                    updated = true;
                    break;  // packet_id is unique
                }
            }

            if (updated) {
                localStorage.setItem(fullKey, JSON.stringify(messages));
                break;  // Found and updated, no need to scan more keys
            }
        }
    } catch (e) {
        console.error('Error persisting ack status:', e);
    }
},

loadInitialData() {
    if (this._initialDataLoaded) {
        return;
    }
    this._initialDataLoaded = true;

    try {
        // Add a small delay to ensure WebSocket auth is complete
        setTimeout(async () => {

            // Update status to show loading
            this.showStatus('Loading nodes and channels...');
            this.addSystemMessage('Loading device data automatically...', 'info');

            try {
                // Load all data in parallel for efficiency
                await Promise.all([
                    this.loadNodes(),
                    this.loadChannels()
                ]);

                this.showStatus('Connected - Data loaded successfully');
                this.addSystemMessage('Device data loaded successfully', 'success');

                // Update title with connected node name
                this._updateConnectionTitle();

            } catch (error) {
                console.error('Error loading initial data:', error);
                this.showMessage('Failed to load initial data: ' + error.message, 'error');
                this.addSystemMessage('Failed to load device data: ' + error.message, 'error');
            }

        }, 2000); // 2 second delay for WebSocket stability

    } catch (error) {
        console.error('Error in loadInitialData:', error);
        this.showMessage('Error displaying main app: ' + error.message, 'error');
    }
},

/** Fetch session info and update page title with connected node name. */
async _updateConnectionTitle() {
    if (!this.sessionId) return;
    try {
        const response = await fetch(`/api/sessions/${this.sessionId}`, {
            headers: { 'X-Session-ID': this.sessionId }
        });
        if (!response.ok) return;
        const data = await response.json();
        const conn = data.data?.connection;
        if (!conn) return;

        const nodeName = conn.long_name || conn.short_name || null;
        if (nodeName && nodeName !== 'unknown') {
            document.title = `Im Mesh Client (${nodeName})`;
        } else if (!this._titleRetried) {
            // Node name not available yet - retry once after 10s
            this._titleRetried = true;
            setTimeout(() => this._updateConnectionTitle(), 10000);
        }
    } catch (e) {
        console.error('Error updating connection title:', e);
    }
},

async loadNodes() {
    if (!this.sessionId) return;

    this.logCommunication('OUT', 'Loading nodes from device', 'info');

    try {
        const response = await fetch('/api/nodes', {
            headers: {
                'X-Session-ID': this.sessionId
            }
        });

        if (response.ok) {
            const data = await response.json();
            this.logCommunication('IN', `Nodes loaded: ${data.data?.count || 0} nodes`, 'success');

            if (data.success && data.data.nodes) {
                this.updateNodesList(data.data.nodes);
            }
        } else {
            const errorText = await response.text();
            console.error('Nodes load failed:', errorText);
            this.logCommunication('IN', `Nodes load failed: HTTP ${response.status}`, 'error');
        }
    } catch (error) {
        console.error('Load nodes error:', error);
        this.logCommunication('IN', `Nodes load error: ${error.message}`, 'error');
    } finally {
        if (document.activeElement) document.activeElement.blur();
    }
},

async loadChannels() {
    if (!this.sessionId) return;

    this.logCommunication('OUT', 'Loading channels from device', 'info');

    try {
        const response = await fetch('/api/channels', {
            headers: {
                'X-Session-ID': this.sessionId
            }
        });

        if (response.ok) {
            const data = await response.json();
            this.logCommunication('IN', `Channels loaded: ${data.data?.count || 0} channels`, 'success');

            if (data.success && data.data.channels) {
                this.updateChannelsList(data.data.channels);
            }
        } else {
            const errorText = await response.text();
            console.error('Channels load failed:', errorText);
            this.logCommunication('IN', `Channels load failed: HTTP ${response.status}`, 'error');
        }
    } catch (error) {
        console.error('Load channels error:', error);
        this.logCommunication('IN', `Channels load error: ${error.message}`, 'error');
    } finally {
        if (document.activeElement) document.activeElement.blur();
    }
}
});
