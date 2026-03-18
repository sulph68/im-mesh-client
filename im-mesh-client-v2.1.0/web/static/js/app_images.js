/**
 * Meshtastic Web Client - Images Module: Encode, reassembly, segment send, settings, export, history, utils
 */

Object.assign(MeshtasticClient.prototype, {

updateNode(nodeData) {

    if (this.storage && nodeData) {
        this.storage.addOrUpdateNode(nodeData);

        // Refresh the nodes display
        const nodes = this.storage.getNodes();
        this.updateNodesList(nodes);
    }

    this.updateStatistics();
},

// ============================================
// IMAGE UPLOAD METHODS
// ============================================

openImageUploadModal() {
    const modal = document.getElementById('imageUploadModal');
    if (modal) {
        modal.style.display = 'flex';
        // Reset state
        const fileInput = document.getElementById('imageFileInput');
        if (fileInput) fileInput.value = '';
        document.getElementById('imagePreviewArea').style.display = 'none';
        document.getElementById('encodePreviewBtn').style.display = 'none';
        document.getElementById('confirmImageUpload').disabled = true;
        this._encodedSegments = null;

        // Load saved encoding settings
        this.loadEncodingSettingsToModal();
    }
},

closeImageUploadModal() {
    const modal = document.getElementById('imageUploadModal');
    if (modal) modal.style.display = 'none';
    this._encodedSegments = null;
},

handleImageSelected(event) {
    const file = event.target.files[0];
    if (!file) return;

    if (!file.type.startsWith('image/')) {
        this.showMessage('Please select an image file', 'error');
        return;
    }

    // Show original preview
    const reader = new FileReader();
    reader.onload = (e) => {
        const originalPreview = document.getElementById('originalPreview');
        if (originalPreview) {
            originalPreview.src = e.target.result;
        }
        document.getElementById('imagePreviewArea').style.display = 'block';
        document.getElementById('encodePreviewBtn').style.display = 'inline-flex';
        document.getElementById('encodedPreview').src = '';
        document.getElementById('encodingStats').innerHTML = '<em>Click "Encode Preview" to see encoding results</em>';
        this._selectedImageFile = file;
    };
    reader.readAsDataURL(file);
},

async encodeImagePreview() {
    if (!this._selectedImageFile || !this.sessionId) {
        this.showMessage('No image selected or no session', 'error');
        return;
    }

    const btn = document.getElementById('encodePreviewBtn');
    if (btn) btn.textContent = 'Encoding...';

    try {
        const formData = this._buildEncodeFormData();
        const response = await fetch('/api/encode-image', {
            method: 'POST',
            headers: { 'X-Session-ID': this.sessionId },
            body: formData
        });

        const data = await response.json();

        if (data.success) {
            this._encodedSegments = data.data.segments;

            // Use decoded_preview from backend (actual encoded result), 
            // fall back to preview_data (original resize)
            const bestPreview = data.data.decoded_preview || data.data.preview_data || null;
            this._encodedPreviewBase64 = bestPreview;

            // Show the decoded preview, or try frontend decode as fallback
            if (data.data.decoded_preview) {
                const encodedPreview = document.getElementById('encodedPreview');
                if (encodedPreview) {
                    encodedPreview.src = 'data:image/png;base64,' + data.data.decoded_preview;
                }
            } else {
                // Backend didn't provide decoded_preview, try decode via API
                await this._updateEncodedPreview(data.data);
            }

            // Show stats and segments
            this._renderEncodingStats(data.data.stats);
            this._renderSegmentList('encodingStats', this._encodedSegments);

            document.getElementById('confirmImageUpload').disabled = false;
            this.showMessage(`Image encoded: ${data.data.stats.segment_count} segments`, 'success');
        } else {
            this.showMessage('Encoding failed: ' + (data.message || 'Unknown error'), 'error');
        }
    } catch (error) {
        console.error('Encode preview error:', error);
        this.showMessage('Encoding failed: ' + error.message, 'error');
    } finally {
        if (btn) btn.textContent = 'Encode Preview';
    }
},

/** Build FormData with image file and encoding parameters. */
_buildEncodeFormData() {
    const formData = new FormData();
    formData.append('file', this._selectedImageFile);

    const sizeVal = (document.getElementById('encImageSize') || {}).value || '64x64';
    const [imgW, imgH] = sizeVal.split('x').map(Number);
    const params = {
        bit_depth: parseInt(document.getElementById('encBitDepth').value) || 1,
        image_width: imgW || 64,
        image_height: imgH || 64,
        mode: document.getElementById('encMode').value || 'rle_nibble_xor',
        segment_length: parseInt(document.getElementById('encSegmentLen').value) || 200
    };
    formData.append('encoding_params', JSON.stringify(params));
    return formData;
},

/** Decode encoded segments back to show the actual encoded image preview. */
async _updateEncodedPreview(encodeResult) {
    try {
        const decodeResp = await fetch('/api/decode-segments', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Session-ID': this.sessionId
            },
            body: JSON.stringify({ segments: encodeResult.segments })
        });
        const decodeData = await decodeResp.json();
        if (decodeData.success && decodeData.data && decodeData.data.image_data) {
            this._encodedPreviewBase64 = decodeData.data.image_data;
            const encodedPreview = document.getElementById('encodedPreview');
            if (encodedPreview) {
                encodedPreview.src = 'data:image/png;base64,' + decodeData.data.image_data;
            }
        } else {
            this._setPreviewFallback(encodeResult.preview_data);
        }
    } catch (decErr) {
        console.warn('Could not decode segments for preview:', decErr);
        this._setPreviewFallback(encodeResult.preview_data);
    }
},

/** Set the encoded preview image to the fallback resized preview. */
_setPreviewFallback(previewData) {
    if (previewData) {
        const encodedPreview = document.getElementById('encodedPreview');
        if (encodedPreview) {
            encodedPreview.src = 'data:image/png;base64,' + previewData;
        }
    }
},

/** Render encoding statistics in the stats container. */
_renderEncodingStats(stats) {
    const statsEl = document.getElementById('encodingStats');
    if (statsEl) {
        statsEl.innerHTML = `
            <div class="stat-row"><span class="stat-label">Packets required:</span> <span class="stat-value">${stats.segment_count}</span></div>
            <div class="stat-row"><span class="stat-label">Payload size:</span> <span class="stat-value">${stats.total_bytes} bytes</span></div>
            <div class="stat-row"><span class="stat-label">Encoding:</span> <span class="stat-value">${stats.compression_method}</span></div>
            <div class="stat-row"><span class="stat-label">Dimensions:</span> <span class="stat-value">${stats.image_dimensions}</span></div>
            <div class="stat-row"><span class="stat-label">Bit depth:</span> <span class="stat-value">${stats.bit_depth}-bit</span></div>
        `;
    }
},

/**
 * Render a list of segments inside a disclosure triangle with per-segment
 * copy buttons and a "Copy All" button. Appended to the given container.
 */
_renderSegmentList(containerId, segments) {
    if (!segments || segments.length === 0) return;
    const container = document.getElementById(containerId);
    if (!container) return;

    // Build disclosure triangle (details/summary)
    const details = document.createElement('details');
    details.className = 'segment-disclosure';
    const summary = document.createElement('summary');
    summary.textContent = `Segments (${segments.length})`;
    details.appendChild(summary);

    // "Copy All Segments" button at top
    const copyAllBtn = document.createElement('button');
    copyAllBtn.className = 'btn btn-small btn-copy-all';
    copyAllBtn.textContent = 'Copy All Segments';
    copyAllBtn.addEventListener('click', () => {
        const allText = segments.join('\n');
        this._copyToClipboard(allText).then(() => {
            copyAllBtn.textContent = 'Copied!';
            setTimeout(() => { copyAllBtn.textContent = 'Copy All Segments'; }, 1500);
        });
    });
    details.appendChild(copyAllBtn);

    // Each segment with its own copy button
    segments.forEach((seg, idx) => {
        const row = document.createElement('div');
        row.className = 'segment-row';

        const label = document.createElement('span');
        label.className = 'segment-label';
        label.textContent = `Seg ${idx + 1}/${segments.length}:`;

        const value = document.createElement('code');
        value.className = 'segment-value';
        value.textContent = seg.length > 80 ? seg.substring(0, 77) + '...' : seg;
        value.title = seg;  // Full text on hover

        const copyBtn = document.createElement('button');
        copyBtn.className = 'btn btn-tiny btn-copy-seg';
        copyBtn.textContent = 'Copy';
        copyBtn.addEventListener('click', () => {
            this._copyToClipboard(seg).then(() => {
                copyBtn.textContent = 'OK';
                setTimeout(() => { copyBtn.textContent = 'Copy'; }, 1500);
            });
        });

        row.appendChild(label);
        row.appendChild(value);
        row.appendChild(copyBtn);
        details.appendChild(row);
    });

    container.appendChild(details);
},

/**
 * Copy text to clipboard. Works on both HTTPS and plain HTTP.
 * Uses navigator.clipboard when available, falls back to execCommand.
 * Returns a Promise that resolves when copy is done.
 */
_copyToClipboard(text) {
    return new Promise((resolve, reject) => {
        // navigator.clipboard is only available in secure contexts (HTTPS / localhost)
        if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
            navigator.clipboard.writeText(text).then(resolve).catch(() => {
                // Fallback if clipboard API rejects (e.g. permissions)
                this._fallbackCopy(text);
                resolve();
            });
        } else {
            this._fallbackCopy(text);
            resolve();
        }
    });
},

/**
 * Fallback copy using a temporary textarea (for non-HTTPS contexts).
 */
_fallbackCopy(text) {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.left = '-9999px';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    try { document.execCommand('copy'); } catch (e) { /* ignore */ }
    document.body.removeChild(textarea);
},

/**
 * Check if a text message is an image segment.
 * Matches format: IMG{width}x{height}:{method}{bitdepth}:{seg}[/{total}]:{data}
 */
_isImageSegment(text) {
    if (!text || typeof text !== 'string') return false;
    return /^IMG\d+x\d+:[TRXtrx]\d+:\d+(?:\/\d+)?:.+$/.test(text.trim());
},

/**
 * Parse an image segment header to extract metadata.
 * Returns null if not a valid segment.
 */
_parseImageSegment(text) {
    if (!text) return null;
    const match = text.trim().match(/^IMG(\d+)x(\d+):([TRXtrx])(\d+):(\d+)(?:\/(\d+))?:(.+)$/);
    if (!match) return null;
    return {
        width: parseInt(match[1]),
        height: parseInt(match[2]),
        method: match[3],
        bitDepth: parseInt(match[4]),
        segIndex: parseInt(match[5]),
        totalSegs: match[6] ? parseInt(match[6]) : null,
        data: match[7],
        raw: text.trim()
    };
},

/**
 * After rendering a received message, check if consecutive messages from the 
 * same sender form a complete (or partial) image segment set. If so, attach
 * a "Reassemble Image" button to the last segment message element.
 */
_checkForImageSegments(messageElement, messageData) {
    const text = messageData.text || messageData.decoded_text || '';
    if (!this._isImageSegment(text)) return;

    const currentParsed = this._parseImageSegment(text);
    if (!currentParsed) return;

    const fromDisplay = messageData.from || '';
    const imageHeader = `${currentParsed.width}x${currentParsed.height}:${currentParsed.method}${currentParsed.bitDepth}`;

    const container = document.getElementById('messagesContainer');
    if (!container) return;

    const allMessages = Array.from(container.querySelectorAll('.message.received'));
    const myIndex = allMessages.indexOf(messageElement);
    if (myIndex < 0) return;

    // Collect consecutive segments from same sender with matching header
    const segments = this._collectImageSegments(allMessages, myIndex, fromDisplay, imageHeader);
    if (segments.length < 1) return;

    const totalExpected = currentParsed.totalSegs || segments.reduce((max, s) => {
        return Math.max(max, s.parsed.totalSegs || s.parsed.segIndex + 1);
    }, 1);

    const segIndices = new Set(segments.map(s => s.parsed.segIndex));
    const isComplete = segIndices.size >= totalExpected;

    // Remove previous reassemble buttons
    segments.forEach(s => {
        const old = s.element.querySelector('.reassemble-btn-container');
        if (old) old.remove();
    });

    // Add reassemble button to last segment element
    this._addReassembleButton(segments, totalExpected, segIndices.size, isComplete);
},

/**
 * Walk backward and forward from myIndex to collect consecutive image segments
 * from the same sender with the same image header.
 *
 * IMPORTANT: Stops at image-set boundaries. When walking backward, if we
 * encounter a segment index we have already seen, it means we have crossed
 * into a previous (different) image that shares the same header format.
 * We stop there so only the *latest* image's segments are collected.
 *
 * Any non-segment message (including text from the same sender) also breaks
 * the chain, per the requirement that intervening text invalidates earlier
 * segments.
 */
_collectImageSegments(allMessages, myIndex, fromDisplay, imageHeader) {
    const segments = [];
    const seenIndices = new Set();

    // Walk backward (inclusive of myIndex)
    for (let i = myIndex; i >= 0; i--) {
        const el = allMessages[i];
        const contentEl = el.querySelector('.message-content');
        if (!contentEl) break;

        // Different sender -> break (not continue), per issues.txt line 71-72
        const fromEl = el.querySelector('.message-from');
        const senderName = fromEl ? fromEl.textContent.trim() : '';
        if (fromDisplay && senderName && senderName !== fromDisplay) break;

        const msgText = contentEl.textContent || '';
        const parsed = this._parseImageSegment(msgText);
        // Non-segment text from same sender -> break the chain
        if (!parsed) break;

        const h = `${parsed.width}x${parsed.height}:${parsed.method}${parsed.bitDepth}`;
        if (h !== imageHeader) break;

        // Duplicate segment index means we crossed into a previous image set
        if (seenIndices.has(parsed.segIndex)) break;
        seenIndices.add(parsed.segIndex);

        segments.unshift({ parsed, element: el });
    }

    // Walk forward (exclusive of myIndex, already included above)
    for (let i = myIndex + 1; i < allMessages.length; i++) {
        const el = allMessages[i];
        const contentEl = el.querySelector('.message-content');
        if (!contentEl) break;

        // Different sender -> break
        const fromEl = el.querySelector('.message-from');
        const senderName = fromEl ? fromEl.textContent.trim() : '';
        if (fromDisplay && senderName && senderName !== fromDisplay) break;

        const msgText = contentEl.textContent || '';
        const parsed = this._parseImageSegment(msgText);
        if (!parsed) break;

        const h = `${parsed.width}x${parsed.height}:${parsed.method}${parsed.bitDepth}`;
        if (h !== imageHeader) break;

        // Duplicate segment index means we crossed into the next image set
        if (seenIndices.has(parsed.segIndex)) break;
        seenIndices.add(parsed.segIndex);

        segments.push({ parsed, element: el });
    }

    return segments;
},

/** Add a "Reassemble Image" button to the last segment in the chain. */
_addReassembleButton(segments, totalExpected, uniqueCount, isComplete) {
    const lastEl = segments[segments.length - 1].element;
    const btnContainer = document.createElement('div');
    btnContainer.className = 'reassemble-btn-container';

    const statusText = isComplete 
        ? `Image complete (${uniqueCount}/${totalExpected} segments)`
        : `Image partial (${uniqueCount}/${totalExpected} segments received)`;

    const statusSpan = document.createElement('span');
    statusSpan.className = 'reassemble-status';
    statusSpan.textContent = statusText;
    btnContainer.appendChild(statusSpan);

    const btn = document.createElement('button');
    btn.className = 'btn btn-small btn-reassemble';
    btn.textContent = isComplete ? 'Reassemble Image' : 'Try Reassemble';
    btn.addEventListener('click', () => {
        const seen = new Set();
        const uniqueSegments = [];
        for (const s of segments) {
            if (!seen.has(s.parsed.segIndex)) {
                seen.add(s.parsed.segIndex);
                uniqueSegments.push(s.parsed.raw);
            }
        }
        uniqueSegments.sort((a, b) => {
            const parsedA = this._parseImageSegment(a);
            const parsedB = this._parseImageSegment(b);
            return (parsedA ? parsedA.segIndex : 0) - (parsedB ? parsedB.segIndex : 0);
        });
        this._reassembleImage(uniqueSegments, lastEl);
    });
    btnContainer.appendChild(btn);

    lastEl.appendChild(btnContainer);
},

/**
 * Send segments to the server for decoding and display the resulting image.
 */
async _reassembleImage(segments, afterElement) {
    if (!this.sessionId) {
        this.showMessage('No active session', 'error');
        return;
    }

    // Find or create result container
    let resultContainer = afterElement.querySelector('.reassemble-result');
    if (!resultContainer) {
        resultContainer = document.createElement('div');
        resultContainer.className = 'reassemble-result';
        afterElement.appendChild(resultContainer);
    }
    resultContainer.innerHTML = '<span class="reassemble-loading">Decoding image...</span>';

    try {
        const response = await fetch('/api/decode-segments', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Session-ID': this.sessionId
            },
            body: JSON.stringify({ segments: segments })
        });

        const data = await response.json();

        if (data.success && data.data && data.data.image_data) {
            const stats = data.data.stats || {};
            resultContainer.innerHTML = `
                <div class="reassembled-image-info">
                    Decoded: ${stats.width || '?'}x${stats.height || '?'}, 
                    ${stats.compression_method || 'unknown'}, 
                    ${stats.segments_received || segments.length} segments
                </div>
                <img src="data:image/png;base64,${data.data.image_data}" 
                     alt="Reassembled Image" 
                     class="reassembled-image">
            `;
            this.showMessage('Image reassembled successfully', 'success');
        } else {
            resultContainer.innerHTML = `<span class="reassemble-error">Decode failed: ${this.escapeHtml(data.message || 'Unknown error')}</span>`;
            this.showMessage('Image decode failed: ' + (data.message || 'Unknown error'), 'error');
        }
    } catch (error) {
        console.error('Reassemble error:', error);
        resultContainer.innerHTML = `<span class="reassemble-error">Error: ${this.escapeHtml(error.message)}</span>`;
        this.showMessage('Reassemble failed: ' + error.message, 'error');
    }
},

async sendImageSegments() {
    if (!this._encodedSegments || this._encodedSegments.length === 0) {
        this.showMessage('No encoded image to send. Click "Encode Preview" first.', 'warning');
        return;
    }

    if (!this.sessionId) {
        this.showMessage('No active session', 'error');
        return;
    }

    const confirmBtn = document.getElementById('confirmImageUpload');
    if (confirmBtn) {
        confirmBtn.disabled = true;
        confirmBtn.textContent = 'Sending...';
    }

    const segments = [...this._encodedSegments];
    const totalSegments = segments.length;
    const channel = this.sendTarget.type === 'channel' ? this.sendTarget.id : (this.selectedChannelIndex || 0);
    const toNode = (this.sendTarget.type === 'node' && this.sendTarget.id) ? this.sendTarget.id : null;
    const previewBase64 = this._encodedPreviewBase64 || null;

    this.closeImageUploadModal();

    // Build the message UI
    const msgUid = 'img-send-' + Date.now();
    const { messageElement, statusContainer } = this._buildImageSendUI(msgUid, totalSegments, previewBase64);

    // Per-segment tracking state
    const segState = {
        ackState: new Array(totalSegments).fill(null),
        packetIds: new Array(totalSegments).fill(null),
        _segments: segments,
        _channel: channel,
        _toNode: toNode
    };

    // Create abort button
    this._imageSendAborted = false;
    this._addImageAbortButton(msgUid, statusContainer);

    // Create bound helpers for send/retry/ack
    const sendOne = (idx) => this._sendOneImageSegment(idx, segments, channel, toNode, msgUid, segState);
    const addRetry = (idx) => this._addSegmentRetryButton(idx, msgUid, segState, sendOne);
    const startAckTimeout = (idx) => this._startSegmentAckTimeout(idx, msgUid, segState, addRetry);

    // Set up ACK handler for image segments
    this._imageSegmentAckHandler = (ackData) => {
        this._handleImageSegmentAck(ackData, msgUid, totalSegments, segState);
    };

    // Send segments sequentially with 15s delay
    const { allOk, aborted } = await this._sendSegmentsSequentially(
        totalSegments, sendOne, addRetry, startAckTimeout, msgUid, segState
    );

    // Clean up and finalize
    this._finalizeImageSend(msgUid, messageElement, segments, segState, totalSegments, allOk, aborted);

    if (confirmBtn) {
        confirmBtn.disabled = false;
        confirmBtn.textContent = 'Send Image';
    }
},

/** Build the image send message element with per-segment status rows. */
_buildImageSendUI(msgUid, totalSegments, previewBase64) {
    const messagesContainer = document.getElementById('messagesContainer');
    const messageElement = document.createElement('div');
    messageElement.className = 'message sent';
    messageElement.id = msgUid;

    let previewHtml = '';
    if (previewBase64) {
        previewHtml = `<img src="data:image/png;base64,${previewBase64}" alt="Sent Image Preview" class="sent-image-preview">`;
    }

    messageElement.innerHTML = `
        <div class="message-header">
            <span class="message-from sent-name">You</span>
            <span class="message-time">${new Date().toLocaleTimeString()}</span>
        </div>
        <div class="message-content">[Image] Sending ${totalSegments} segment${totalSegments > 1 ? 's' : ''}...</div>
        ${previewHtml}
        <div class="segment-send-status" id="${msgUid}-status"></div>
    `;
    messagesContainer.appendChild(messageElement);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;

    // Build per-segment status rows
    const statusContainer = document.getElementById(`${msgUid}-status`);
    for (let i = 0; i < totalSegments; i++) {
        const row = document.createElement('div');
        row.className = 'segment-row';
        row.id = `${msgUid}-seg-${i}`;
        row.innerHTML = `
            <span class="seg-label">Seg ${i + 1}/${totalSegments}</span>
            <span class="seg-state seg-waiting" id="${msgUid}-seg-${i}-state">Waiting</span>
        `;
        statusContainer.appendChild(row);
    }

    return { messageElement, statusContainer };
},

/** Add abort button to segment status container. */
_addImageAbortButton(msgUid, statusContainer) {
    const abortBtn = document.createElement('button');
    abortBtn.className = 'btn btn-small btn-abort-send';
    abortBtn.id = `${msgUid}-abort`;
    abortBtn.textContent = 'Abort Send';
    abortBtn.addEventListener('click', () => {
        this._imageSendAborted = true;
        abortBtn.disabled = true;
        abortBtn.textContent = 'Aborting...';
    });
    statusContainer.appendChild(abortBtn);
},

/** Send one image segment via API. Updates segState in-place. */
async _sendOneImageSegment(idx, segments, channel, toNode, msgUid, segState) {
    const totalSegments = segments.length;
    const stateEl = document.getElementById(`${msgUid}-seg-${idx}-state`);
    if (stateEl) {
        stateEl.className = 'seg-state seg-sending';
        stateEl.textContent = 'Sending...';
    }

    try {
        const payload = {
            text: segments[idx],
            channel: channel,
            want_ack: true
        };
        if (toNode) payload.to_node = toNode;

        const response = await fetch('/api/messages/send', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Session-ID': this.sessionId
            },
            body: JSON.stringify(payload)
        });

        const data = await response.json();

        if (data.success) {
            const packetId = data.data ? data.data.packet_id : null;
            segState.packetIds[idx] = packetId;
            segState.ackState[idx] = 'pending';

            if (stateEl) {
                stateEl.className = 'seg-state seg-awaiting-ack';
                stateEl.textContent = 'Awaiting ack...';
            }

            this.logCommunication('OUT', `Seg ${idx + 1}/${totalSegments} sent (id=${packetId})`, 'success');
            return true;
        } else {
            segState.ackState[idx] = 'failed';
            if (stateEl) {
                stateEl.className = 'seg-state seg-failed';
                stateEl.textContent = 'Send failed';
            }
            this.logCommunication('OUT', `Seg ${idx + 1}/${totalSegments} send failed`, 'error');
            return false;
        }
    } catch (error) {
        segState.ackState[idx] = 'failed';
        if (stateEl) {
            stateEl.className = 'seg-state seg-failed';
            stateEl.textContent = 'Error';
        }
        console.error(`Segment ${idx + 1} send error:`, error);
        return false;
    }
},

/** Add a retry button to a segment row. */
_addSegmentRetryButton(idx, msgUid, segState, sendOneFn) {
    const row = document.getElementById(`${msgUid}-seg-${idx}`);
    if (!row || row.querySelector('.btn-retry-seg')) return;
    const btn = document.createElement('button');
    btn.className = 'btn btn-small btn-retry-seg';
    btn.textContent = 'Retry';
    btn.addEventListener('click', async () => {
        btn.disabled = true;
        btn.textContent = 'Retrying...';
        const ok = await sendOneFn(idx);
        if (ok) {
            btn.remove();
            this._startSegmentAckTimeout(idx, msgUid, segState,
                (i) => this._addSegmentRetryButton(i, msgUid, segState, sendOneFn));
        } else {
            btn.disabled = false;
            btn.textContent = 'Retry';
        }
    });
    row.appendChild(btn);
},

/** Start a 30-second ACK timeout for a segment; adds retry button on timeout. */
_startSegmentAckTimeout(idx, msgUid, segState, addRetryFn) {
    setTimeout(() => {
        if (segState.ackState[idx] === 'pending') {
            segState.ackState[idx] = 'retry';
            const stateEl = document.getElementById(`${msgUid}-seg-${idx}-state`);
            if (stateEl) {
                stateEl.className = 'seg-state seg-timeout';
                stateEl.textContent = 'No ack (30s)';
            }
            addRetryFn(idx);
        }
    }, 30000);
},

/** Handle ACK for image segment packet IDs. */
_handleImageSegmentAck(ackData, msgUid, totalSegments, segState) {
    if (!ackData || !ackData.request_id) return;
    const rid = String(ackData.request_id);
    for (let i = 0; i < totalSegments; i++) {
        if (String(segState.packetIds[i]) === rid) {
            const ackOk = ackData.ack_received;
            const stateEl = document.getElementById(`${msgUid}-seg-${i}-state`);
            if (ackOk) {
                segState.ackState[i] = 'ack';
                if (stateEl) {
                    stateEl.className = 'seg-state seg-ack-ok';
                    stateEl.textContent = 'Ack received';
                }
                const row = document.getElementById(`${msgUid}-seg-${i}`);
                const retryBtn = row ? row.querySelector('.btn-retry-seg') : null;
                if (retryBtn) retryBtn.remove();
            } else {
                segState.ackState[i] = 'failed';
                if (stateEl) {
                    stateEl.className = 'seg-state seg-failed';
                    stateEl.textContent = `Nak: ${ackData.error_reason || 'unknown'}`;
                }
                // Use segState._segments/_channel/_toNode captured at send time
                this._addSegmentRetryButton(i, msgUid, segState,
                    (idx) => this._sendOneImageSegment(idx, segState._segments, segState._channel, segState._toNode, msgUid, segState));
            }
            break;
        }
    }
},

/** Send segments sequentially with 15s delay and abort support. */
async _sendSegmentsSequentially(totalSegments, sendOneFn, addRetryFn, startAckTimeoutFn, msgUid, segState) {
    let allOk = true;
    let aborted = false;
    for (let i = 0; i < totalSegments; i++) {
        if (this._imageSendAborted) {
            aborted = true;
            for (let j = i; j < totalSegments; j++) {
                segState.ackState[j] = 'aborted';
                const stateEl = document.getElementById(`${msgUid}-seg-${j}-state`);
                if (stateEl) {
                    stateEl.className = 'seg-state seg-aborted';
                    stateEl.textContent = 'Aborted';
                }
            }
            break;
        }

        const ok = await sendOneFn(i);
        if (ok) {
            startAckTimeoutFn(i);
        } else {
            allOk = false;
            addRetryFn(i);
        }

        if (i < totalSegments - 1) {
            const stateElNext = document.getElementById(`${msgUid}-seg-${i + 1}-state`);
            if (stateElNext) {
                stateElNext.className = 'seg-state seg-waiting';
                stateElNext.textContent = 'Waiting (15s)...';
            }
            for (let t = 0; t < 30; t++) {
                if (this._imageSendAborted) break;
                await new Promise(resolve => setTimeout(resolve, 500));
            }
        }
    }
    return { allOk, aborted };
},

/** Finalize image send: remove abort button, update status text, add segment disclosure. */
_finalizeImageSend(msgUid, messageElement, segments, segState, totalSegments, allOk, aborted) {
    const abortEl = document.getElementById(`${msgUid}-abort`);
    if (abortEl) abortEl.remove();

    const contentEl = messageElement.querySelector('.message-content');
    if (contentEl) {
        const sentCount = segState.ackState.filter(s => s !== null && s !== 'failed' && s !== 'aborted').length;
        if (aborted) {
            contentEl.textContent = `[Image] Aborted - ${sentCount}/${totalSegments} segments sent`;
        } else {
            contentEl.textContent = `[Image] ${sentCount}/${totalSegments} segments sent`;
        }
    }

    if (segments.length > 0) {
        const disclosureContainer = document.createElement('div');
        disclosureContainer.className = 'sent-segments-disclosure';
        const discId = 'seg-disc-' + Date.now();
        disclosureContainer.id = discId;
        messageElement.appendChild(disclosureContainer);
        setTimeout(() => this._renderSegmentList(discId, segments), 0);
    }

    if (aborted) {
        this.showMessage('Image send aborted', 'warning');
    } else {
        this.showMessage(allOk ? `Image: ${totalSegments} segments sent` : 'Some segments failed - use Retry buttons', allOk ? 'success' : 'warning');
    }
},

loadEncodingSettingsToModal() {
    // Load saved encoding settings from localStorage
    const defaults = this.getEncodingSettings();
    const setVal = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.value = val;
    };
    setVal('encMode', defaults.mode);
    setVal('encBitDepth', defaults.bit_depth);
    setVal('encImageSize', `${defaults.image_width}x${defaults.image_height}`);
    setVal('encSegmentLen', defaults.segment_length);
},

getEncodingSettings() {
    const saved = localStorage.getItem('meshtastic_encoding_settings');
    if (saved) {
        try { return JSON.parse(saved); } catch (e) {}
    }
    return {
        mode: 'rle_nibble_xor',
        bit_depth: 1,
        image_width: 64,
        image_height: 64,
        segment_length: 200
    };
},

// ============================================
// SETTINGS MODAL METHODS
// ============================================

openSettingsModal() {
    const modal = document.getElementById('settingsModal');
    if (modal) {
        modal.style.display = 'flex';
        const defaults = this.getEncodingSettings();
        const setVal = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.value = val;
        };
        setVal('settingsEncMode', defaults.mode);
        setVal('settingsBitDepth', defaults.bit_depth);
        setVal('settingsImageSize', `${defaults.image_width}x${defaults.image_height}`);
        setVal('settingsSegmentLen', defaults.segment_length);
    }
},

closeSettingsModal() {
    const modal = document.getElementById('settingsModal');
    if (modal) modal.style.display = 'none';
},

saveSettings() {
    const sizeVal = (document.getElementById('settingsImageSize') || {}).value || '64x64';
    const [sW, sH] = sizeVal.split('x').map(Number);
    const settings = {
        mode: document.getElementById('settingsEncMode').value,
        bit_depth: parseInt(document.getElementById('settingsBitDepth').value),
        image_width: sW || 64,
        image_height: sH || 64,
        segment_length: parseInt(document.getElementById('settingsSegmentLen').value)
    };
    localStorage.setItem('meshtastic_encoding_settings', JSON.stringify(settings));
    this.showMessage('Settings saved', 'success');
    this.closeSettingsModal();
},

/**
 * Export all stored messages as a downloadable JSON file.
 */
exportMessages() {
    if (!this.storage) {
        this.showMessage('No active session to export from', 'error');
        return;
    }
    const data = this.storage.exportData();
    const exportPayload = {
        exported_at: new Date().toISOString(),
        session_id: this.sessionId || 'unknown',
        host: this.host || 'unknown',
        port: this.port || 'unknown',
        data: data
    };
    const blob = new Blob([JSON.stringify(exportPayload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `meshtastic-export-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    this.showMessage('Messages exported', 'success');
},

// ============================================
// MESSAGE HISTORY PER CHANNEL/NODE
// ============================================

getMessageStorageKey() {
    if (!this.sendTarget) return null;
    if (this.sendTarget.type === 'node') {
        return `messages_node_${this.sendTarget.id}`;
    }
    return `messages_channel_${this.sendTarget.id}`;
},

loadMessageHistory() {
    // Load stored messages for the current target from localStorage
    const messagesContainer = document.getElementById('messagesContainer');
    if (!messagesContainer || !this.storage) return;

    // Clear current messages
    messagesContainer.innerHTML = '';

    const key = this.getMessageStorageKey();
    if (!key) return;

    const messages = this.storage.getItem(key) || [];
    if (messages.length === 0) {
        messagesContainer.innerHTML = `<div class="empty-history-hint">No message history for ${this.escapeHtml(this.sendTarget.name)}</div>`;
        return;
    }

    // Render stored messages
    messages.forEach(msg => {
        this.renderChatMessage(msg, false);
    });

    // Scroll to bottom
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
},

storeMessageForTarget(messageData) {
    if (!this.storage) return;

    // Determine which target this message belongs to
    let key = null;
    if (messageData._targetKey) {
        key = messageData._targetKey;
    } else if (messageData.type === 'sent') {
        key = this.getMessageStorageKey();
    } else {
        // Received messages: store under channel or DM based on context
        // Check isDM flag which was computed properly by addMessage()
        if (messageData.isDM) {
            key = `messages_node_${messageData.from_node || messageData.from}`;
        } else {
            key = `messages_channel_${messageData.channel || 0}`;
        }
    }

    if (!key) return;

    const messages = this.storage.getItem(key) || [];
    // Remove the internal key before storing
    const toStore = { ...messageData };
    delete toStore._targetKey;
    messages.push(toStore);

    // Keep max 200 messages per target
    if (messages.length > 200) {
        messages.splice(0, messages.length - 200);
    }
    this.storage.setItem(key, messages);
},

// Escape HTML to prevent XSS
escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
},

// Sync device method
async syncDevice() {
            this.showMessage('Refreshing device data...', 'info');

    try {
        const response = await fetch('/api/device/refresh', {
            method: 'POST',
            headers: {
                'X-Session-ID': this.sessionId
            }
        });

        if (response.ok) {
            const data = await response.json();
            if (data.success) {
                this.showMessage('Device sync completed', 'success');
                // Reset flag and reload data
                this._initialDataLoaded = false;
                this.loadInitialData();
            } else {
                this.showMessage('Device sync failed: ' + data.message, 'error');
            }
        } else {
            this.showMessage('Device sync failed: HTTP ' + response.status, 'error');
        }
    } catch (error) {
        console.error('Sync device error:', error);
        this.showMessage('Device sync error: ' + error.message, 'error');
    } finally {
        // Remove focus/highlight from the button
        if (document.activeElement) document.activeElement.blur();
    }
},

// Alias for refreshChannels (for HTML onclick compatibility)
async refreshChannels() {

    this.showMessage('Reconnecting to refresh channel data...', 'info');
    this.addSystemMessage('Refreshing channel data - reopening connection...', 'info');
    this.showStatus('Reconnecting to refresh data...');

    try {
        // Trigger a fresh connection to get updated data
        const result = await this.loadChannels();

        this.showMessage('Channel data refreshed successfully', 'success');
        this.addSystemMessage('Channel data updated', 'success');
        this.showStatus('Data refreshed - Connection closed (will reconnect when needed)');

        return result;

    } catch (error) {
        console.error('Error refreshing channels:', error);
        this.showMessage('Failed to refresh channel data: ' + error.message, 'error');
        this.addSystemMessage('Failed to refresh channel data', 'error');
        throw error;
    } finally {
        if (document.activeElement) document.activeElement.blur();
    }
},

// Update statistics in the sidebar
updateStatistics() {
    try {
        // Get data from storage if available
        const nodes = this.storage ? this.storage.getNodes() : [];
        const channels = this.storage ? this.storage.getChannels() : [];
        const favorites = this.storage ? this.storage.getFavorites() : [];
        const messages = this.storage ? this.storage.getMessages() : [];

        // Count "online" nodes (heard in last 1 hour)
        const oneHourAgo = Math.floor(Date.now() / 1000) - 3600;
        const onlineCount = nodes.filter(n => {
            const lastHeard = n.lastHeard || n.lastSeen;
            return lastHeard && lastHeard > oneHourAgo;
        }).length;

        // Count nodes with position
        const withPosition = nodes.filter(n => n.position && n.position.latitude !== undefined).length;

        // Update DOM elements
        const updateElement = (id, value) => {
            const element = document.getElementById(id);
            if (element) element.textContent = value;
        };

        updateElement('totalNodes', nodes.length);
        updateElement('onlineNodes', onlineCount);
        updateElement('totalChannels', channels.length);
        updateElement('favoriteNodes', favorites.length);
        updateElement('messageCount', messages.length);
        updateElement('fragmentCount', withPosition);

        console.log('Statistics updated:', { 
            nodes: nodes.length, 
            online: onlineCount,
            channels: channels.length,
            favorites: favorites.length,
            messages: messages.length,
            withPosition: withPosition
        });
    } catch (error) {
        console.error('Error updating statistics:', error);
    }
}
});
