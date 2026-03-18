/**
 * Meshtastic Web Client - UI Module: Channel selection, favorites, showMainApp, status, toasts, log
 */

Object.assign(MeshtasticClient.prototype, {

selectChannel(channelIndex, channelName) {

    // Deselect any selected node
    this.selectedNodeId = null;
    document.querySelectorAll('.node-item').forEach(el => el.classList.remove('selected'));
    // Reset all node button labels back to "Select"
    this._updateNodeSelectButtons();
    // Hide node detail panel
    this.hideNodeDetail();

    // Store selected channel
    this.selectedChannelIndex = channelIndex;
    this.selectedChannelName = channelName;
    this.sendTarget = { type: 'channel', id: channelIndex, name: channelName };

    // Update channel selection UI
    document.querySelectorAll('.channel-item').forEach(el => el.classList.remove('selected'));
    document.querySelectorAll('.channel-item').forEach(el => {
        if (el.dataset.channelIndex === String(channelIndex)) {
            el.classList.add('selected');
        }
    });

    // Update chat header and load history
    this.updateChatTargetLabel();
    this.loadMessageHistory();

    // Clear unread count for this channel
    const channelKey = `messages_channel_${channelIndex}`;
    delete this._unreadCounts[channelKey];
    this._updateNotificationBadges();

    this.showMessage(`Sending to channel: ${channelName}`, 'info');

    // On mobile, switch to chat tab after selecting a channel
    if (this._isMobile) {
        this._switchMobileTab('chat');
    }
},

updateChatTargetLabel() {
    const label = document.getElementById('chatTargetLabel');
    if (label && this.sendTarget) {
        if (this.sendTarget.type === 'node') {
            label.textContent = `DM: ${this.sendTarget.name}`;
        } else {
            label.textContent = this.sendTarget.name;
        }
    }
},

/**
 * Re-apply the .selected class to the currently selected channel-item.
 * Called when deselecting a node to restore the channel highlight.
 */
_highlightSelectedChannel() {
    document.querySelectorAll('.channel-item').forEach(el => {
        if (el.dataset.channelIndex === String(this.selectedChannelIndex)) {
            el.classList.add('selected');
        } else {
            el.classList.remove('selected');
        }
    });
},

toggleFavorite(nodeId) {

    if (!this.storage) {
        console.error('Storage not available');
        return;
    }

    // Get current node data
    const nodes = this.storage.getNodes();
    const node = nodes.find(n => (n.id || n.num) === nodeId);

    if (node) {
        // Toggle favorite status
        node.isFavorite = !node.isFavorite;

        // Update in storage
        this.storage.addOrUpdateNode(node);

        // Refresh the nodes display
        this.updateNodesList(nodes);

        // Update statistics
        this.updateStatistics();

        const action = node.isFavorite ? 'added to' : 'removed from';
        this.showMessage(`Node ${action} favorites`, 'info');
    } else {
        console.error('Node not found:', nodeId);
    }
},

showMainApp(host, port, sessionName) {
    try {
        const sessionSetup = document.getElementById('sessionSetup');
        const mainApp = document.getElementById('mainApp');

        if (sessionSetup) sessionSetup.style.display = 'none';
        if (mainApp) {
            mainApp.style.display = 'flex';
            mainApp.style.flexDirection = 'column';
        }

        // Update session info in header
        const sessionNodeElement = document.getElementById('sessionNode');
        if (sessionNodeElement) {
            sessionNodeElement.textContent = `${host}:${port}`;
        }

        // Update session name if provided
        const sessionNameElement = document.querySelector('.session-name');
        if (sessionNameElement && sessionName !== 'Default') {
            sessionNameElement.textContent = sessionName;
        }

        // Update connection status to show establishing
        this.updateConnectionStatus('connecting', 'Establishing Connection...');

        // Show initial system message with correct status
        this.addSystemMessage(`Establishing connection to ${host}:${port}...`, 'info');

    } catch (error) {
        console.error('Error showing main app:', error);
        this.showMessage('Error displaying main app: ' + error.message, 'error');
    }
},

showStatus(message) {
    const statusElement = document.getElementById('sessionStatus');
    if (statusElement) {
        statusElement.textContent = message;
        statusElement.style.display = 'block';
    }
},

showMessage(message, type = 'info') {
    console.log(`${type.toUpperCase()}: ${message}`);

    // Create toast notification
    const container = document.getElementById('toastContainer');
    if (!container) {
        console.warn('Toast container not found');
        return;
    }

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;

    container.appendChild(toast);

    // Auto-remove after 5 seconds
    setTimeout(() => {
        if (toast.parentNode) {
            toast.parentNode.removeChild(toast);
        }
    }, 5000);
},

updateConnectionStatus(status, message) {

    // Update the status dot
    const statusDot = document.getElementById('statusDot');
    if (statusDot) {
        statusDot.className = `status-dot ${status}`;
    }

    // Update the status text
    const statusText = document.getElementById('statusText');
    if (statusText) {
        statusText.textContent = message;
    }

    // Update the container class for styling
    const statusElement = document.querySelector('.connection-status');
    if (statusElement) {
        statusElement.className = `connection-status ${status}`;
    }
},

addSystemMessage(message, type) {
    // Route system messages to toast banners instead of the message pane
    this.showMessage(message, type);
},

addConnectionLostMessage() {
    // Show connection lost via toast banner and status indicator
    this.showMessage('Connection to Meshtastic node lost. Click "Sync Device" or "Refresh Channels" to reconnect.', 'error');
    this.updateConnectionStatus('disconnected', 'Connection Lost');
},

logCommunication(direction, message, type = 'info') {
    console.log(`COMM ${direction}:`, message);

    const timestamp = new Date().toLocaleTimeString();
    const html = `
        <span class="log-time">[${timestamp}]</span>
        <span class="log-direction">${this.escapeHtml(direction)}</span>
        <span class="log-message">${this.escapeHtml(message)}</span>
    `;

    // Desktop log
    const logContainer = document.getElementById('logContent');
    if (logContainer) {
        const logEntry = document.createElement('div');
        logEntry.className = `log-entry ${direction.toLowerCase()} ${type}`;
        logEntry.innerHTML = html;
        logContainer.appendChild(logEntry);
        logContainer.scrollTop = logContainer.scrollHeight;
    }

    // Modal log (if open)
    const modalLog = document.getElementById('logContentModal');
    if (modalLog) {
        const logEntry = document.createElement('div');
        logEntry.className = `log-entry ${direction.toLowerCase()} ${type}`;
        logEntry.innerHTML = html;
        modalLog.appendChild(logEntry);
        modalLog.scrollTop = modalLog.scrollHeight;
    }
},

showCommunicationLog() {
    // In mobile mode, open log as a modal
    if (this._isMobile) {
        this._openLogModal();
        return;
    }
    const logPanel = document.getElementById('communicationLog');
    const container = document.querySelector('.container');
    if (logPanel) {
        logPanel.classList.add('visible');
        logPanel.style.display = 'block';
        if (container) container.classList.add('log-open');
    }
},

toggleCommunicationLog() {
    // In mobile mode, toggle log modal
    if (this._isMobile) {
        const logModal = document.getElementById('logModal');
        if (logModal && logModal.style.display !== 'none') {
            this._closeLogModal();
        } else {
            this._openLogModal();
        }
        return;
    }
    const logPanel = document.getElementById('communicationLog');
    const container = document.querySelector('.container');
    const showLogBtn = document.getElementById('showLogBtn');

    if (logPanel) {
        const isVisible = logPanel.classList.contains('visible');

        if (isVisible) {
            logPanel.classList.remove('visible');
            logPanel.style.display = 'none';
            if (container) container.classList.remove('log-open');
            if (showLogBtn) showLogBtn.textContent = 'Show Log';
        } else {
            logPanel.classList.add('visible');
            logPanel.style.display = 'block';
            if (container) container.classList.add('log-open');
            if (showLogBtn) showLogBtn.textContent = 'Hide Log';
        }
    }
},

clearCommunicationLog() {
    const logContent = document.getElementById('logContent');
    if (logContent) {
        logContent.innerHTML = '<div class="log-entry">Communication log cleared...</div>';
    }
    const modalLog = document.getElementById('logContentModal');
    if (modalLog) {
        modalLog.innerHTML = '<div class="log-entry">Communication log cleared...</div>';
    }
},

_openLogModal() {
    const logModal = document.getElementById('logModal');
    if (!logModal) return;
    // Sync content from desktop log into the modal
    const desktopLog = document.getElementById('logContent');
    const modalLog = document.getElementById('logContentModal');
    if (desktopLog && modalLog) {
        modalLog.innerHTML = desktopLog.innerHTML;
    }
    logModal.style.display = 'flex';
    if (modalLog) {
        modalLog.scrollTop = modalLog.scrollHeight;
    }
},

_closeLogModal() {
    const logModal = document.getElementById('logModal');
    if (logModal) {
        logModal.style.display = 'none';
    }
},

_initLogResize() {
    const handle = document.getElementById('logResizeHandle');
    const logContent = document.getElementById('logContent');
    if (!handle || !logContent) return;

    let startY = 0;
    let startHeight = 0;
    let dragging = false;

    const onMouseDown = (e) => {
        e.preventDefault();
        dragging = true;
        startY = e.clientY || (e.touches && e.touches[0].clientY) || 0;
        startHeight = logContent.offsetHeight;
        document.body.style.cursor = 'ns-resize';
        document.body.style.userSelect = 'none';
    };

    const onMouseMove = (e) => {
        if (!dragging) return;
        const clientY = e.clientY || (e.touches && e.touches[0].clientY) || 0;
        // Dragging UP increases height (startY > clientY means drag up)
        const delta = startY - clientY;
        const newHeight = Math.max(60, Math.min(500, startHeight + delta));
        logContent.style.height = newHeight + 'px';
    };

    const onMouseUp = () => {
        if (!dragging) return;
        dragging = false;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
    };

    handle.addEventListener('mousedown', onMouseDown);
    handle.addEventListener('touchstart', onMouseDown, { passive: false });
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('touchmove', onMouseMove, { passive: false });
    document.addEventListener('mouseup', onMouseUp);
    document.addEventListener('touchend', onMouseUp);
}

});
