/**
 * Meshtastic Web Client - Messages Module: Send, queue, ACK timeout, chat rendering, message routing
 */

Object.assign(MeshtasticClient.prototype, {

async sendMessage() {
    const messageInput = document.getElementById('messageInput');
    if (!messageInput) return;

    const text = messageInput.value.trim();
    if (!text) {
        this.showMessage('Please enter a message', 'warning');
        return;
    }

    if (!this.sessionId) {
        this.showMessage('No active session', 'error');
        return;
    }

    const payload = {
        text: text,
        channel: this.sendTarget.type === 'channel' ? this.sendTarget.id : (this.selectedChannelIndex || 0),
        want_ack: true
    };

    // If sending to a specific node (DM), set to_node
    if (this.sendTarget.type === 'node' && this.sendTarget.id) {
        payload.to_node = this.sendTarget.id;
    }

    // Clear input immediately for good UX
    messageInput.value = '';

    // Queue the message (with metadata for display after send)
    this._messageQueue.push({
        payload: payload,
        displayText: text,
        targetName: this.sendTarget.name,
        targetKey: this.getMessageStorageKey(),
        channel: payload.channel
    });

    console.log(`Message queued: "${text}" (queue size: ${this._messageQueue.length})`);

    if (this._messageQueue.length > 1) {
        this.showMessage(`Message queued (${this._messageQueue.length} in queue)`, 'info');
    }

    // Start processing if not already running
    this._processMessageQueue();
},

/**
 * Process the message queue, sending one message at a time with 3-second
 * spacing between each message to avoid overwhelming the mesh radio.
 */
async _processMessageQueue() {
    if (this._messageQueueProcessing) return;  // Already running
    this._messageQueueProcessing = true;

    try {
        while (this._messageQueue.length > 0) {
            const msg = this._messageQueue.shift();

            try {
                console.log(`Sending queued message: "${msg.displayText}" to ${msg.targetName}`);

                const response = await fetch('/api/messages/send', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Session-ID': this.sessionId
                    },
                    body: JSON.stringify(msg.payload)
                });

                const data = await response.json();

                if (data.success) {
                    // Extract packet_id for ack tracking
                    const packetId = data.data ? data.data.packet_id : null;
                    const wantAck = msg.payload.want_ack || false;

                    // Add sent message to chat display with ack tracking info
                    this.addChatMessage({
                        from: 'You',
                        text: msg.displayText,
                        timestamp: new Date().toISOString(),
                        type: 'sent',
                        to: msg.targetName,
                        channel: msg.channel,
                        _targetKey: msg.targetKey,
                        packet_id: packetId,
                        want_ack: wantAck,
                        ack_status: wantAck ? 'pending' : null
                    });

                    this.logCommunication('OUT', `Sent: "${msg.displayText}" to ${msg.targetName} (id=${packetId})`, 'success');
                    console.log(`Message sent successfully (packetId=${packetId})`);

                    // Start 15-second ACK timeout with retry button
                    if (wantAck && packetId) {
                        this._startAckTimeout(packetId, msg);
                    }
                } else {
                    // Send failed - show failed message with retry button
                    this._addFailedMessage(msg, data.message || 'Unknown error');
                    this.logCommunication('OUT', `Send failed: ${data.message}`, 'error');

                    // If connection lost, try to indicate reconnection
                    if (data.message && data.message.includes('not connected')) {
                        this.addConnectionLostMessage();
                    }
                }
            } catch (error) {
                console.error('Send message error:', error);
                // Show failed message with retry button
                this._addFailedMessage(msg, error.message);
                this.logCommunication('OUT', `Send error: ${error.message}`, 'error');
            }

            // Wait 3 seconds before sending the next message (if any remain)
            if (this._messageQueue.length > 0) {
                console.log(`Waiting ${this._messageQueueDelay}ms before next message (${this._messageQueue.length} remaining)`);
                await new Promise(resolve => setTimeout(resolve, this._messageQueueDelay));
            }
        }
    } finally {
        // ALWAYS reset the processing flag so future messages can be sent
        this._messageQueueProcessing = false;
    }
},

/**
 * Start a 15-second ACK timeout for a sent message.
 * If no ACK arrives, shows "No ack" with a Retry button.
 */
_startAckTimeout(packetId, originalMsg) {
    setTimeout(() => {
        const container = document.getElementById('messagesContainer');
        if (!container) return;
        const msgEl = container.querySelector(`[data-packet-id="${packetId}"]`);
        if (!msgEl) return;
        const ackDiv = msgEl.querySelector('.ack-status');
        if (!ackDiv) return;

        // Only update if still pending (hasn't received ack yet)
        if (ackDiv.classList.contains('ack-pending')) {
            ackDiv.className = 'ack-status ack-timeout';
            ackDiv.innerHTML = 'No ack received ';

            const retryBtn = document.createElement('button');
            retryBtn.className = 'btn-retry-seg';
            retryBtn.textContent = 'Retry';
            retryBtn.addEventListener('click', () => {
                retryBtn.disabled = true;
                retryBtn.textContent = 'Retrying...';
                // Re-queue the original message
                this._messageQueue.push({
                    payload: originalMsg.payload,
                    displayText: originalMsg.displayText,
                    targetName: originalMsg.targetName,
                    targetKey: originalMsg.targetKey,
                    channel: originalMsg.channel
                });
                // Remove the old message element
                msgEl.remove();
                this._processMessageQueue();
            });
            ackDiv.appendChild(retryBtn);
        }
    }, 15000);
},

/**
 * Add a failed message to chat with a Retry button.
 */
_addFailedMessage(msg, errorText) {
    const messagesContainer = document.getElementById('messagesContainer');
    if (!messagesContainer) return;

    const messageElement = document.createElement('div');
    messageElement.className = 'message sent';

    const time = new Date().toLocaleTimeString();
    messageElement.innerHTML = `
        <div class="message-header">
            <span class="message-from sent-name">You</span>
            <span class="message-time">${time}</span>
        </div>
        <div class="message-content">${this.escapeHtml(msg.displayText)}</div>
        <div class="ack-status ack-failed">Send failed: ${this.escapeHtml(errorText)}</div>
    `;

    const retryBtn = document.createElement('button');
    retryBtn.className = 'btn-retry-seg';
    retryBtn.textContent = 'Retry';
    retryBtn.style.marginTop = '0.3rem';
    retryBtn.addEventListener('click', () => {
        retryBtn.disabled = true;
        retryBtn.textContent = 'Retrying...';
        // Re-queue the message
        this._messageQueue.push({
            payload: msg.payload,
            displayText: msg.displayText,
            targetName: msg.targetName,
            targetKey: msg.targetKey,
            channel: msg.channel
        });
        // Remove the failed element
        messageElement.remove();
        this._processMessageQueue();
    });
    messageElement.appendChild(retryBtn);

    messagesContainer.appendChild(messageElement);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
},

// Add a chat message to the messages display area
addChatMessage(messageData) {
    try {
        // Store message for current target
        this.storeMessageForTarget(messageData);

        // Also store in global message list
        if (this.storage) {
            this.storage.addMessage(messageData);
        }
    } catch (e) {
        console.error('Error storing message:', e);
    }

    // Render in chat (even if storage fails)
    try {
        this.renderChatMessage(messageData, true);
    } catch (e) {
        console.error('Error rendering message:', e);
    }
},

// Render a message element in the chat container
renderChatMessage(messageData, scrollToBottom) {
    const messagesContainer = document.getElementById('messagesContainer');
    if (!messagesContainer) return;

    const messageElement = document.createElement('div');
    const isSent = messageData.type === 'sent';
    const isSystem = messageData.type === 'system';
    const isBinary = messageData.portnum === 256 || messageData.isBinary;
    const isImage = messageData.isImage;

    let className = 'message';
    if (isSent) className += ' sent';
    else if (isSystem) className += ' system';
    else className += ' received';
    if (isBinary) className += ' binary-msg';
    if (isImage) className += ' image-msg';
    messageElement.className = className;

    const time = messageData.timestamp ? new Date(messageData.timestamp).toLocaleTimeString() : new Date().toLocaleTimeString();
    const fromName = this.escapeHtml(messageData.from || 'Unknown');
    const text = messageData.text || messageData.decoded_text || messageData.payload || '';

    // Render content by message type
    if (isBinary && !isSent) {
        this._renderBinaryMessageContent(messageElement, messageData, fromName, time);
    } else if (isImage && messageData.imageData) {
        this._renderReceivedImageContent(messageElement, fromName, time, text, messageData.imageData);
    } else if (isImage && isSent) {
        this._renderSentImageContent(messageElement, messageData, fromName, time, text);
    } else {
        this._renderTextMessageContent(messageElement, messageData, fromName, time, text, isSent);
    }

    // ACK indicator for sent messages
    if (isSent && messageData.want_ack) {
        const packetId = messageData.packet_id;
        if (packetId) messageElement.setAttribute('data-packet-id', packetId);
        const ackDiv = document.createElement('div');
        ackDiv.className = 'ack-status ack-pending';
        ackDiv.textContent = 'Awaiting ack...';
        messageElement.appendChild(ackDiv);
    }

    messagesContainer.appendChild(messageElement);

    // Check for image segment reassembly on received text messages
    if (!isSent && !isSystem && !isBinary && !isImage) {
        this._checkForImageSegments(messageElement, messageData);
    }

    if (scrollToBottom) {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }
},

/** Render binary/custom app message content. */
_renderBinaryMessageContent(el, messageData, fromName, time) {
    const payload = messageData.rawPayload || messageData.text || '';
    const segInfo = messageData.segments ? `Segments: ${messageData.segments}` : '';
    const sizeInfo = messageData.payloadSize ? `Size: ${messageData.payloadSize} bytes` : '';
    el.innerHTML = `
        <div class="message-header">
            <span class="message-from">${fromName}</span>
            <span class="message-time">${time}</span>
        </div>
        <div class="message-content">Binary Message</div>
        <div class="binary-meta">
            ${segInfo ? `<span>${segInfo}</span>` : ''}
            ${sizeInfo ? `<span>${sizeInfo}</span>` : ''}
        </div>
        <button class="copy-payload-btn" onclick="window.meshtasticClient._copyToClipboard('${this.escapeHtml(String(payload)).replace(/'/g, "\\'")}').then(()=>window.meshtasticClient.showMessage('Payload copied','success'))">Copy Payload</button>
    `;
},

/** Render received decoded image content. */
_renderReceivedImageContent(el, fromName, time, text, imageData) {
    el.innerHTML = `
        <div class="message-header">
            <span class="message-from">${fromName}</span>
            <span class="message-time">${time}</span>
        </div>
        <div class="message-content">${this.escapeHtml(text)}</div>
        <img src="data:image/png;base64,${imageData}" alt="Image" style="max-width: 200px; max-height: 200px; border-radius: 4px; border: 1px solid var(--border); margin-top: 0.5rem;">
    `;
},

/** Render sent image with preview and segment disclosure. */
_renderSentImageContent(el, messageData, fromName, time, text) {
    let previewHtml = '';
    if (messageData.imagePreviewBase64) {
        previewHtml = `<img src="data:image/png;base64,${messageData.imagePreviewBase64}" alt="Sent Image Preview" class="sent-image-preview">`;
    }
    el.innerHTML = `
        <div class="message-header">
            <span class="message-from sent-name">${fromName}</span>
            <span class="message-time">${time}</span>
        </div>
        <div class="message-content">${this.escapeHtml(text)}</div>
        ${previewHtml}
    `;
    if (messageData.segments && messageData.segments.length > 0) {
        const disclosureContainer = document.createElement('div');
        disclosureContainer.className = 'sent-segments-disclosure';
        el.appendChild(disclosureContainer);
        const uid = 'seg-chat-' + Date.now();
        disclosureContainer.id = uid;
        setTimeout(() => this._renderSegmentList(uid, messageData.segments), 0);
    }
},

/** Render standard text message content. */
_renderTextMessageContent(el, messageData, fromName, time, text, isSent) {
    const portLabel = messageData.portnum === 256 ? ' [BINARY]' : '';
    el.innerHTML = `
        <div class="message-header">
            <span class="message-from${isSent ? ' sent-name' : ''}">${fromName}${portLabel}</span>
            <span class="message-time">${time}</span>
        </div>
        <div class="message-content">${this.escapeHtml(text)}</div>
    `;
},

// Handle incoming message from WebSocket
addMessage(messageData) {

    // Notify new message in browser tab title
    this._notifyNewMessageInTitle();

    // Resolve sender name
    const fromName = this._resolveSenderName(messageData);

    // Determine routing key (channel vs DM)
    const { msgTargetKey, isDM } = this._resolveMessageTarget(messageData);

    console.log(`Message routing: from=${messageData.from_node} to=${messageData.to_node} is_broadcast=${messageData.is_broadcast} isDM=${isDM} targetKey=${msgTargetKey}`);

    const currentTargetKey = this.getMessageStorageKey();
    const isCurrentView = (currentTargetKey === msgTargetKey);

    // Dispatch by message type
    if (messageData.type === 'image_complete' && messageData.image_data) {
        this._handleImageCompleteMessage(messageData, fromName, msgTargetKey, isCurrentView);
        return;
    }

    if (messageData.decoded && messageData.decoded.portnum === 256) {
        this._handleBinaryMessage(messageData, fromName, msgTargetKey, isCurrentView);
        this.updateStatistics();
        return;
    }

    if (messageData.decoded_text || (messageData.decoded && messageData.decoded.text)) {
        this._handleTextMessage(messageData, fromName, msgTargetKey, isCurrentView);
    } else {
        this._handleFallbackMessage(messageData, fromName, msgTargetKey, isCurrentView);
    }

    this.updateStatistics();
},

/** Resolve sender display name from messageData or stored nodes. */
_resolveSenderName(messageData) {
    let fromName = messageData.from_name || messageData.from_node || messageData.from || 'Unknown';
    if (this.storage && (messageData.from_node || messageData.from)) {
        const nodeId = messageData.from_node || messageData.from;
        const nodes = this.storage.getNodes();
        const senderNode = nodes.find(n => (n.id || n.num) === nodeId);
        if (senderNode) {
            fromName = senderNode.longName || senderNode.shortName || senderNode.name || fromName;
        }
    }
    return fromName;
},

/** Determine the storage key and whether this is a DM. */
_resolveMessageTarget(messageData) {
    const toNodeStr = String(messageData.to_node || '').toLowerCase().replace(/^!/, '');
    const isBroadcastAddr = !toNodeStr || toNodeStr === 'ffffffff' || toNodeStr === '4294967295';
    const isDM = messageData.to_node && messageData.is_broadcast === false && !isBroadcastAddr;
    let msgTargetKey;
    if (isDM) {
        msgTargetKey = `messages_node_${messageData.from_node || messageData.from}`;
    } else {
        msgTargetKey = `messages_channel_${messageData.channel || 0}`;
    }
    return { msgTargetKey, isDM };
},

/** Handle decoded image_complete messages. */
_handleImageCompleteMessage(messageData, fromName, msgTargetKey, isCurrentView) {
    const chatMsg = {
        from: fromName,
        text: 'Image received',
        timestamp: messageData.rx_time || messageData.timestamp,
        type: 'received',
        isImage: true,
        imageData: messageData.image_data,
        channel: messageData.channel,
        _targetKey: msgTargetKey
    };
    if (isCurrentView) {
        this.addChatMessage(chatMsg);
    } else {
        this._storeAndNotify(chatMsg, msgTargetKey, messageData.from_node || messageData.from);
    }
},

/** Handle BINARY_MESSAGE_APP (portnum 256) messages. */
_handleBinaryMessage(messageData, fromName, msgTargetKey, isCurrentView) {
    const payload = messageData.decoded.payload || '[binary data]';
    const chatMsg = {
        from: fromName,
        text: '[Binary Message]',
        timestamp: messageData.rx_time || messageData.timestamp,
        type: 'received',
        portnum: 256,
        isBinary: true,
        rawPayload: payload,
        payloadSize: typeof payload === 'string' ? payload.length : 0,
        segments: messageData.decoded.segments || null,
        channel: messageData.channel,
        _targetKey: msgTargetKey
    };
    if (isCurrentView) {
        this.addChatMessage(chatMsg);
    } else {
        this._storeAndNotify(chatMsg, msgTargetKey, messageData.from_node || messageData.from);
    }
},

/** Handle standard text messages. */
_handleTextMessage(messageData, fromName, msgTargetKey, isCurrentView) {
    const text = messageData.decoded_text || messageData.decoded.text;
    const chatMsg = {
        from: fromName,
        text: text,
        timestamp: messageData.rx_time || messageData.timestamp,
        type: 'received',
        channel: messageData.channel,
        from_node: messageData.from_node,
        _targetKey: msgTargetKey
    };
    if (isCurrentView) {
        this.addChatMessage(chatMsg);
    } else {
        this._storeAndNotify(chatMsg, msgTargetKey, messageData.from_node || messageData.from);
    }
},

/** Handle messages with no recognized payload format. */
_handleFallbackMessage(messageData, fromName, msgTargetKey, isCurrentView) {
    const fallbackText = messageData.payload || messageData.text || null;
    if (fallbackText) {
        const chatMsg = {
            from: fromName,
            text: typeof fallbackText === 'string' ? fallbackText : '[message]',
            timestamp: messageData.rx_time || messageData.timestamp,
            type: 'received',
            channel: messageData.channel,
            from_node: messageData.from_node,
            _targetKey: msgTargetKey
        };
        if (isCurrentView) {
            this.addChatMessage(chatMsg);
        } else {
            this._storeAndNotify(chatMsg, msgTargetKey, messageData.from_node || messageData.from);
        }
    } else {
        console.warn('addMessage: unhandled message format', messageData);
    }
},

/**
 * Store a message and show a notification badge (message is NOT for current view).
 */
_storeAndNotify(chatMsg, targetKey, fromNodeId) {
    // Store in localStorage
    try {
        this.storeMessageForTarget(chatMsg);
        if (this.storage) {
            this.storage.addMessage(chatMsg);
        }
    } catch (e) {
        console.error('Error storing off-view message:', e);
    }

    // Increment unread count
    this._unreadCounts[targetKey] = (this._unreadCounts[targetKey] || 0) + 1;

    // Track node with unread messages (for DMs)
    if (targetKey.startsWith('messages_node_') && fromNodeId) {
        this._nodesWithUnread.add(fromNodeId);
    }

    // Update badges on channels and nodes
    this._updateNotificationBadges();

    // Re-sort nodes if a DM arrived
    if (targetKey.startsWith('messages_node_') && this.storage) {
        const nodes = this.storage.getNodes();
        this.updateNodesList(nodes);
    }
},

/**
 * Update notification badges on channel and node elements.
 */
_updateNotificationBadges() {
    // Update channel badges
    document.querySelectorAll('.channel-item').forEach(el => {
        const channelIdx = el.dataset.channelIndex;
        if (channelIdx === undefined) return;
        const key = `messages_channel_${channelIdx}`;
        const count = this._unreadCounts[key] || 0;

        // Remove existing badge
        let badge = el.querySelector('.unread-badge');
        if (count > 0) {
            if (!badge) {
                badge = document.createElement('span');
                badge.className = 'unread-badge';
                el.appendChild(badge);
            }
            badge.textContent = count > 99 ? '99+' : count;
        } else if (badge) {
            badge.remove();
        }
    });

    // Update node badges
    document.querySelectorAll('.node-item').forEach(el => {
        const detailsEl = el.querySelector('.node-details');
        if (!detailsEl) return;

        // Extract node ID from details text (e.g., "<uCon@!3d8309d0>")
        const detailsText = detailsEl.textContent || '';
        const idMatch = detailsText.match(/(![0-9a-f]{8})/i);
        if (!idMatch) return;

        const nodeId = idMatch[1];
        const key = `messages_node_${nodeId}`;
        const count = this._unreadCounts[key] || 0;

        // Remove existing badge
        let badge = el.querySelector('.unread-badge');
        if (count > 0) {
            if (!badge) {
                badge = document.createElement('span');
                badge.className = 'unread-badge';
                el.appendChild(badge);
            }
            badge.textContent = count > 99 ? '99+' : count;
        } else if (badge) {
            badge.remove();
        }
    });
},

// Handle node update from WebSocket

/**
 * Add (*) to document.title when a new message arrives (if tab is not focused).
 * The marker is cleared when the tab regains focus (see app_core.js).
 */
_notifyNewMessageInTitle() {
    if (document.hidden || !document.hasFocus()) {
        if (!document.title.startsWith('(*)')) {
            document.title = '(*) ' + document.title;
        }
    }
}
});
