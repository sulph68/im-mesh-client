/**
 * Meshtastic Web Client - Nodes Module: Node/channel lists, mobile layout, selection, detail, map
 */

Object.assign(MeshtasticClient.prototype, {

updateNodesList(nodes) {

    const nodesList = document.getElementById('nodesList');
    const favoritesList = document.getElementById('favoritesList');
    if (!nodesList) {
        console.error('nodesList element not found!');
        return;
    }

    // Store nodes in storage, preserving isFavorite from device
    if (this.storage && nodes.length > 0) {
        nodes.forEach(node => {
            this.storage.addOrUpdateNode(node);
        });
                }

    // Cache all nodes for filtering
    this._allNodes = nodes;

    if (nodes.length === 0) {
        nodesList.innerHTML = '<div class="node-item">No nodes found</div>';
        if (favoritesList) {
            favoritesList.innerHTML = '<div class="node-item">No favorites yet</div>';
        }
        this._updateNodeCountLabel(0, 0);
        return;
    }

    // Separate favorites (from device data) and regular nodes
    const favoriteNodes = nodes.filter(node => node.isFavorite === true);
    const regularNodes = nodes.filter(node => !node.isFavorite);

    // Update favorites list
    if (favoritesList) {
        if (favoriteNodes.length === 0) {
            favoritesList.innerHTML = '<div class="node-item">No favorites yet</div>';
        } else {
            // Sort: favorites with unread messages first
            const sortedFavs = [...favoriteNodes].sort((a, b) => {
                const aId = a.id || a.num;
                const bId = b.id || b.num;
                const aUnread = this._nodesWithUnread.has(aId) ? 1 : 0;
                const bUnread = this._nodesWithUnread.has(bId) ? 1 : 0;
                return bUnread - aUnread;
            });
            favoritesList.innerHTML = '';
            const favFragment = document.createDocumentFragment();
            sortedFavs.forEach(node => {
                favFragment.appendChild(this.createNodeElement(node));
            });
            favoritesList.appendChild(favFragment);
        }
    }

    // Render the regular nodes list (with filter support)
    this._renderFilteredNodes(regularNodes);

    // Update statistics
    this.updateStatistics();

    // Re-apply notification badges (nodes were re-created)
    this._updateNotificationBadges();

    // Re-apply selected node state after DOM rebuild
    this._reapplyNodeSelection();

},

/**
 * Re-apply the selected node visual state after the node list is rebuilt.
 * Fixes issue where pull-to-refresh or node refresh clears selection.
 */
_reapplyNodeSelection() {
    if (!this.selectedNodeId) return;

    const nodeId = this.selectedNodeId;
    document.querySelectorAll('.node-item').forEach(element => {
        const detailsEl = element.querySelector('.node-details');
        if (detailsEl && detailsEl.textContent && detailsEl.textContent.includes(nodeId)) {
            element.classList.add('selected');
        }
    });
    this._updateNodeSelectButtons();
},

// ─── Mobile Layout Management ────────────────────────────────────

/**
 * Initialize mobile layout detection and apply the correct mode.
 * Checks localStorage for user preference, otherwise auto-detects.
 */
_initMobileLayout() {
    // Check for saved preference
    const savedMode = localStorage.getItem('mesh_layout_mode');
    if (savedMode === 'mobile') {
        this._isMobile = true;
        this._mobileAutoDetect = false;
    } else if (savedMode === 'desktop') {
        this._isMobile = false;
        this._mobileAutoDetect = false;
    } else {
        // Auto-detect based on screen width and touch capability
        this._mobileAutoDetect = true;
        this._isMobile = this._detectMobile();
    }

    this._applyLayoutMode();

    // Listen for window resize to re-evaluate in auto mode
    window.addEventListener('resize', () => {
        if (this._mobileAutoDetect) {
            const wasMobile = this._isMobile;
            this._isMobile = this._detectMobile();
            if (wasMobile !== this._isMobile) {
                this._applyLayoutMode();
            }
        }
    });
},

/**
 * Detect if the device should use mobile layout.
 * Uses screen width + touch capability as heuristics.
 * Works even with Safari "Request Desktop Site" because we check actual viewport width.
 */
_detectMobile() {
    const viewportWidth = window.innerWidth;
    const hasTouch = ('ontouchstart' in window) || (navigator.maxTouchPoints > 0);
    // Mobile if viewport < 900px, or if viewport < 1100px AND has touch
    return viewportWidth < 900 || (viewportWidth < 1100 && hasTouch);
},

/**
 * Toggle between mobile and desktop layout.
 * Saves the preference to localStorage.
 */
_toggleMobileLayout() {
    this._mobileAutoDetect = false;
    this._isMobile = !this._isMobile;
    localStorage.setItem('mesh_layout_mode', this._isMobile ? 'mobile' : 'desktop');
    this._applyLayoutMode();
},

/**
 * Apply the current layout mode (mobile or desktop) to the DOM.
 * Adds/removes 'mobile-mode' class on body and updates the toggle button.
 */
_applyLayoutMode() {
    const body = document.body;
    const toggleBtn = document.getElementById('toggleLayoutBtn');
    const tabBar = document.getElementById('mobileTabBar');

    if (this._isMobile) {
        body.classList.add('mobile-mode');
        if (toggleBtn) toggleBtn.textContent = '🖥️';
        if (toggleBtn) toggleBtn.title = 'Switch to desktop layout';
        if (tabBar) tabBar.style.display = 'flex';
        // Apply current tab
        this._switchMobileTab(this._activeTab);
    } else {
        body.classList.remove('mobile-mode');
        body.classList.remove('show-more-sections');
        if (toggleBtn) toggleBtn.textContent = '📱';
        if (toggleBtn) toggleBtn.title = 'Switch to mobile layout';
        if (tabBar) tabBar.style.display = 'none';
        // Show all panels in desktop mode - clear any inline styles from mobile tab switching
        const leftSidebar = document.querySelector('.sidebar-left');
        const rightSidebar = document.querySelector('.sidebar-right');
        const chatArea = document.querySelector('.chat-area');
        if (leftSidebar) leftSidebar.style.display = '';
        if (rightSidebar) rightSidebar.style.display = '';
        if (chatArea) chatArea.style.display = '';
    }
},

/**
 * Switch the active tab in mobile mode.
 * Shows only the relevant panel and hides others.
 */
_switchMobileTab(tabName) {
    this._activeTab = tabName;

    const leftSidebar = document.querySelector('.sidebar-left');
    const rightSidebar = document.querySelector('.sidebar-right');
    const chatArea = document.querySelector('.chat-area');
    const body = document.body;

    // Hide all panels first
    if (leftSidebar) leftSidebar.style.display = 'none';
    if (rightSidebar) rightSidebar.style.display = 'none';
    if (chatArea) chatArea.style.display = 'none';
    body.classList.remove('show-more-sections');

    // Show the selected panel
    switch (tabName) {
        case 'channels':
            // Show left sidebar with ONLY channels (Actions/Stats hidden via CSS)
            if (leftSidebar) leftSidebar.style.display = 'flex';
            break;
        case 'chat':
            if (chatArea) chatArea.style.display = 'flex';
            break;
        case 'nodes':
            if (rightSidebar) rightSidebar.style.display = 'flex';
            break;
        case 'more':
            // Show left sidebar with Actions/Stats/Log visible (channels hidden via CSS)
            if (leftSidebar) leftSidebar.style.display = 'flex';
            body.classList.add('show-more-sections');
            break;
    }

    // Update tab bar active state
    document.querySelectorAll('.mobile-tab').forEach(tab => {
        const isActive = tab.dataset.tab === tabName;
        tab.classList.toggle('active', isActive);
        tab.setAttribute('aria-selected', isActive ? 'true' : 'false');
    });
},

/**
 * Render the filtered node list based on the current search query.
 * Can be called with explicit nodes or uses cached regular nodes.
 */
_renderFilteredNodes(regularNodes) {
    const nodesList = document.getElementById('nodesList');
    if (!nodesList) return;

    // If no explicit nodes provided, derive from cached _allNodes
    if (!regularNodes) {
        regularNodes = this._allNodes.filter(node => !node.isFavorite);
    }

    const query = this._nodeSearchQuery;

    // Apply search filter
    let filtered = regularNodes;
    if (query) {
        filtered = regularNodes.filter(node => {
            const nodeId = (node.id || node.num || '').toLowerCase();
            const longName = (node.longName || '').toLowerCase();
            const shortName = (node.shortName || '').toLowerCase();
            const name = (node.name || '').toLowerCase();
            const hwModel = (node.hwModelString || '').toLowerCase();
            return longName.includes(query) || shortName.includes(query) ||
                   nodeId.includes(query) || name.includes(query) || hwModel.includes(query);
        });
    }

    // Sort: unread first, then by last heard (most recent first)
    const sorted = [...filtered].sort((a, b) => {
        const aId = a.id || a.num;
        const bId = b.id || b.num;
        const aUnread = this._nodesWithUnread.has(aId) ? 1 : 0;
        const bUnread = this._nodesWithUnread.has(bId) ? 1 : 0;
        if (aUnread !== bUnread) return bUnread - aUnread;
        // Secondary: most recently heard first
        const aHeard = a.lastHeard || a.lastSeen || 0;
        const bHeard = b.lastHeard || b.lastSeen || 0;
        return bHeard - aHeard;
    });

    nodesList.innerHTML = '';
    if (sorted.length === 0) {
        nodesList.innerHTML = query
            ? '<div class="node-item">No nodes match filter</div>'
            : '<div class="node-item">No other nodes</div>';
    } else {
        // Use DocumentFragment to batch DOM insertions (avoids 136+ reflows)
        const fragment = document.createDocumentFragment();
        sorted.forEach(node => {
            fragment.appendChild(this.createNodeElement(node));
        });
        nodesList.appendChild(fragment);
    }

    // Update count label
    this._updateNodeCountLabel(sorted.length, regularNodes.length);
},

/**
 * Update the "X of Y" node count label.
 */
_updateNodeCountLabel(shown, total) {
    const label = document.getElementById('nodeCountLabel');
    if (!label) return;
    if (this._nodeSearchQuery) {
        label.textContent = `${shown} of ${total}`;
    } else {
        label.textContent = `${total}`;
    }
},

createNodeElement(node) {
    const nodeElement = document.createElement('div');

    // Use the actual API field names for node ID
    const nodeId = node.id || node.num;
    const hwModel = node.hwModelString || 'Unknown';

    // Determine online status (heard within last hour)
    const lastHeard = node.lastHeard || node.lastSeen;
    const oneHourAgo = Math.floor(Date.now() / 1000) - 3600;
    const isOnline = lastHeard && lastHeard > oneHourAgo;

    // Build CSS classes
    let classes = 'node-item';
    if (isOnline) classes += ' online';
    if (node.isFavorite) classes += ' favorite';
    nodeElement.className = classes;

    // Format node display as "LongName <shortname@nodeid>"
    let displayName = '';
    let secondLine = '';

    if (node.longName && node.longName.trim()) {
        // Has long name, use it as primary
        displayName = node.longName.trim();
        if (node.shortName && node.shortName.trim()) {
            secondLine = `&lt;${node.shortName.trim()}@${nodeId}&gt;`;
        } else {
            secondLine = `&lt;@${nodeId}&gt;`;
        }
    } else if (node.shortName && node.shortName.trim()) {
        // Has short name but no long name
        displayName = node.shortName.trim();
        secondLine = `@${nodeId}`;
    } else if (node.name && node.name.trim()) {
        // Has generated name
        displayName = node.name.trim();
        secondLine = `@${nodeId}`;
    } else {
        // No names, use ID only
        displayName = nodeId;
        secondLine = hwModel;
    }

    // Add favorite indicator if needed
    const favoriteIcon = node.isFavorite ? '⭐ ' : '';

    // Build compact status line
    let statusParts = [];
    if (node.snr !== undefined && node.snr !== null) statusParts.push(`${node.snr}dB`);
    if (node.hopsAway !== undefined && node.hopsAway !== null) statusParts.push(node.hopsAway === 0 ? 'direct' : `${node.hopsAway}hop`);
    if (node.deviceMetrics && node.deviceMetrics.batteryLevel !== undefined) {
        const bl = node.deviceMetrics.batteryLevel;
        statusParts.push(bl > 100 ? 'USB' : `${bl}%`);
    }
    if (node.lastHeard || node.lastSeen) {
        statusParts.push(this._timeAgo(node.lastHeard || node.lastSeen));
    }
    const statusLine = statusParts.length > 0 ? `<div class="node-status-line" style="font-size: 0.7rem; color: var(--text-tertiary, #999); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${statusParts.join(' | ')}</div>` : '';

    // Escape all user-controlled data to prevent XSS from malicious node names
    const safeDisplayName = this.escapeHtml(displayName);
    const safeSecondLine = this.escapeHtml(secondLine.replace(/&lt;/g, '<').replace(/&gt;/g, '>'));
    const safeNodeId = this.escapeHtml(nodeId);
    nodeElement.innerHTML = `
        <div class="node-info">
            <div class="node-name" title="${safeDisplayName}">${favoriteIcon}${safeDisplayName}</div>
            <div class="node-details" title="${safeSecondLine}">${safeSecondLine}</div>
            ${statusLine}
        </div>
        <div class="node-actions">
            <button onclick="event.stopPropagation(); window.meshtasticClient.selectNode('${safeNodeId}')" class="btn btn-small">Select</button>
            <button onclick="event.stopPropagation(); window.meshtasticClient.toggleFavorite('${safeNodeId}')" class="btn btn-small btn-outline" title="Toggle Favorite">
                ${node.isFavorite ? '⭐' : '☆'}
            </button>
        </div>
    `;

    // Make entire node card clickable for select/unselect
    nodeElement.addEventListener('click', () => {
        this.selectNode(safeNodeId);
    });

    return nodeElement;
},

updateChannelsList(channels) {

    const channelsList = document.getElementById('channelsList');
    if (!channelsList) {
        console.error('channelsList element not found!');
        return;
    }

    if (this.storage && channels.length > 0) {
        channels.forEach(channel => {
            this.storage.addOrUpdateChannel(channel);
        });
                }

    channelsList.innerHTML = '';

    if (channels.length === 0) {
        channelsList.innerHTML = '<div class="channel-item">No channels found</div>';
        return;
    }

    // Classify channels
    const { configured, unconfigured } = this._classifyChannels(channels);

    // Render configured channels
    configured.forEach((channel, idx) => {
        channelsList.appendChild(this._createChannelElement(channel, idx));
    });

    // Set initial selection defaults
    this._applyChannelDefaults(configured);

    // Render unconfigured channels under disclosure
    if (unconfigured.length > 0) {
        channelsList.appendChild(this._createUnconfiguredSection(unconfigured));
    }

    this.updateStatistics();
},

/** Classify channels into configured and unconfigured groups. */
_classifyChannels(channels) {
    const configured = [];
    const unconfigured = [];

    channels.forEach(channel => {
        const isMainChannel = channel.index <= 3;
        const hasPSK = channel.psk && channel.psk !== "";
        const hasCustomName = channel.name && channel.name !== `Channel ${channel.index}`;
        const hasSpecialSettings = channel.uplink || channel.downlink || channel.modemPreset;
        const isConfigured = isMainChannel || hasPSK || hasCustomName || hasSpecialSettings;

        if (isConfigured) {
            configured.push({
                ...channel,
                displayName: channel.index === 0 
                    ? (channel.name && channel.name !== 'Channel 0' ? channel.name : 'Primary')
                    : channel.name || `Channel ${channel.index}`,
                configType: channel.index === 0 ? 'Primary' : (isMainChannel ? 'Secondary' : 'Custom')
            });
        } else {
            unconfigured.push({
                ...channel,
                displayName: `Channel ${channel.index}`,
                configType: 'Unconfigured'
            });
        }
    });

    return { configured, unconfigured };
},

/** Create a clickable channel DOM element. */
_createChannelElement(channel, idx) {
    const channelElement = document.createElement('div');
    const isSelected = this.selectedNodeId
        ? false
        : (this.selectedChannelIndex !== undefined
            ? channel.index === this.selectedChannelIndex
            : idx === 0);
    channelElement.className = 'channel-item' + (isSelected ? ' selected' : '');
    channelElement.dataset.channelIndex = channel.index;
    channelElement.innerHTML = `
        <div class="channel-name">${this.escapeHtml(channel.displayName)}</div>
        <div class="channel-info">Channel ${channel.index} &bull; ${this.escapeHtml(channel.configType)}</div>
    `;
    channelElement.addEventListener('click', () => {
        this.selectChannel(channel.index, channel.displayName);
    });
    return channelElement;
},

/** Set initial channel selection defaults if none selected yet. */
_applyChannelDefaults(configuredChannels) {
    if (configuredChannels.length > 0) {
        if (this.selectedChannelIndex === undefined || this.selectedChannelIndex === null) {
            this.selectedChannelIndex = configuredChannels[0].index;
            this.selectedChannelName = configuredChannels[0].displayName;
        }
        if (!this.selectedNodeId && this.sendTarget.type === 'channel') {
            const currentChannel = configuredChannels.find(c => c.index === this.selectedChannelIndex);
            if (currentChannel) {
                this.selectedChannelName = currentChannel.displayName;
                this.sendTarget = { type: 'channel', id: currentChannel.index, name: currentChannel.displayName };
            }
            this.updateChatTargetLabel();
        }
    }
},

/** Create the unconfigured channels disclosure section. */
_createUnconfiguredSection(unconfiguredChannels) {
    const unconfiguredContainer = document.createElement('div');
    unconfiguredContainer.className = 'unconfigured-channels';
    unconfiguredContainer.innerHTML = `
        <details>
            <summary class="unconfigured-summary">
                <span>Unconfigured Channels (${unconfiguredChannels.length})</span>
            </summary>
            <div class="unconfigured-list">
                ${unconfiguredChannels.map(channel => `
                    <div class="channel-item unconfigured">
                        <div class="channel-name">${channel.displayName}</div>
                        <div class="channel-info">Channel ${channel.index} • Unconfigured</div>
                    </div>
                `).join('')}
            </div>
        </details>
    `;
    return unconfiguredContainer;
},

selectNode(nodeId) {

    // Toggle: if already selected, deselect and revert to channel
    if (this.selectedNodeId === nodeId) {
        this.selectedNodeId = null;
        this.sendTarget = { type: 'channel', id: this.selectedChannelIndex || 0, name: this.selectedChannelName || 'Primary Channel' };
        document.querySelectorAll('.node-item').forEach(el => el.classList.remove('selected'));
        // Reset all Select/Unselect button labels back to "Select"
        this._updateNodeSelectButtons();
        // Re-highlight the previously selected channel
        this._highlightSelectedChannel();
        this.updateChatTargetLabel();
        this.loadMessageHistory();
        this.hideNodeDetail();
        this.showMessage('Node deselected - sending to channel', 'info');
        return;
    }

    this.selectedNodeId = nodeId;

    // Find the node name for display
    let nodeName = nodeId;
    if (this.storage) {
        const nodes = this.storage.getNodes();
        const node = nodes.find(n => (n.id || n.num) === nodeId);
        if (node) {
            nodeName = node.longName || node.shortName || node.name || nodeId;
        }
    }

    // Set send target to this node
    this.sendTarget = { type: 'node', id: nodeId, name: nodeName };

    // Update UI to show selected node
    const nodeElements = document.querySelectorAll('.node-item');
    nodeElements.forEach(element => {
        element.classList.remove('selected');
        const nodeDetailsElement = element.querySelector('.node-details');
        if (nodeDetailsElement && nodeDetailsElement.textContent && nodeDetailsElement.textContent.includes(nodeId)) {
            element.classList.add('selected');
        }
    });

    // Update Select/Unselect button labels
    this._updateNodeSelectButtons();

    // Deselect any selected channel
    document.querySelectorAll('.channel-item').forEach(el => el.classList.remove('selected'));

    // Update chat header and load history
    this.updateChatTargetLabel();
    this.loadMessageHistory();

    // Clear unread count for this node
    const nodeKey = `messages_node_${nodeId}`;
    delete this._unreadCounts[nodeKey];
    this._nodesWithUnread.delete(nodeId);
    this._updateNotificationBadges();

    this.showMessage(`Sending to node: ${nodeName}`, 'info');

    // Show node detail panel
    this.showNodeDetail(nodeId);

    // On mobile, switch to chat tab after selecting a node
    if (this._isMobile) {
        this._switchMobileTab('chat');
    }
},

/**
 * Update all node Select/Unselect button labels based on current selection.
 * Selected node's button shows "Unselect", all others show "Select".
 */
_updateNodeSelectButtons() {
    document.querySelectorAll('.node-item').forEach(element => {
        const btn = element.querySelector('.btn.btn-small');
        if (!btn) return;
        // Check if this node-item is the selected one
        if (element.classList.contains('selected')) {
            btn.textContent = 'Unselect';
        } else {
            btn.textContent = 'Select';
        }
    });
},

/**
 * Show detailed information for a selected node.
 */
async showNodeDetail(nodeId) {
    const panel = document.getElementById('nodeDetailPanel');
    const content = document.getElementById('nodeDetailContent');
    const title = document.getElementById('nodeDetailTitle');
    if (!panel || !content) return;

    content.innerHTML = '<div style="color: var(--text-secondary); padding: 4px;">Loading...</div>';
    panel.style.display = 'block';

    try {
        const response = await fetch(`/api/nodes/${encodeURIComponent(nodeId)}`, {
            headers: { 'X-Session-ID': this.sessionId }
        });
        const data = await response.json();

        if (!data.success || !data.data || !data.data.node) {
            content.innerHTML = '<div style="color: var(--text-secondary);">No details available</div>';
            return;
        }

        const node = data.data.node;
        title.textContent = node.longName || node.shortName || node.name || nodeId;
        content.innerHTML = this._buildNodeDetailHtml(node, nodeId);

    } catch (error) {
        console.error('Error loading node detail:', error);
        content.innerHTML = '<div style="color: var(--text-secondary);">Failed to load details</div>';
    }
},

/** Build the full HTML for the node detail panel. */
_buildNodeDetailHtml(node, nodeId) {
    let html = '';

    // Basic info
    html += this._detailRow('Node ID', nodeId);
    if (node.shortName) html += this._detailRow('Short Name', node.shortName);
    if (node.hwModel && node.hwModel !== 'Unknown') html += this._detailRow('Hardware', node.hwModel);
    if (node.role) html += this._detailRow('Role', node.role);
    if (node.hopsAway !== undefined && node.hopsAway !== null) {
        html += this._detailRow('Hops Away', node.hopsAway === 0 ? 'Direct' : node.hopsAway);
    }

    // Signal info
    if (node.snr !== undefined && node.snr !== null) {
        html += this._detailRow('SNR', this._renderSignalIndicator(node.snr) + ` ${node.snr} dB`);
    }
    if (node.rssi !== undefined && node.rssi !== null) {
        html += this._detailRow('RSSI', `${node.rssi} dBm`);
    }

    // Last heard
    if (node.lastHeard || node.lastSeen) {
        html += this._detailRow('Last Heard', this._timeAgo(node.lastHeard || node.lastSeen));
    }

    // Device metrics
    html += this._buildDeviceMetricsHtml(node.deviceMetrics);

    // Position
    html += this._buildPositionHtml(node.position, nodeId);

    return html;
},

/** Build device metrics section HTML. */
_buildDeviceMetricsHtml(dm) {
    if (!dm) return '';
    let html = '<div class="detail-group"><div class="detail-group-title">Device Metrics</div>';
    if (dm.batteryLevel !== undefined && dm.batteryLevel !== null) {
        html += this._detailRow('Battery', this._renderBatteryIndicator(dm.batteryLevel));
    }
    if (dm.voltage !== undefined && dm.voltage !== null && dm.voltage > 0) {
        html += this._detailRow('Voltage', `${dm.voltage.toFixed(2)}V`);
    }
    if (dm.channelUtilization !== undefined && dm.channelUtilization !== null) {
        html += this._detailRow('Ch Util', `${dm.channelUtilization.toFixed(1)}%`);
    }
    if (dm.airUtilTx !== undefined && dm.airUtilTx !== null) {
        html += this._detailRow('Air TX', `${dm.airUtilTx.toFixed(2)}%`);
    }
    if (dm.uptimeSeconds !== undefined && dm.uptimeSeconds !== null) {
        html += this._detailRow('Uptime', this._formatUptime(dm.uptimeSeconds));
    }
    html += '</div>';
    return html;
},

/** Build position section HTML. */
_buildPositionHtml(pos, nodeId) {
    if (!pos || pos.latitude === undefined || pos.longitude === undefined) return '';
    let html = '<div class="detail-group"><div class="detail-group-title">Position</div>';
    html += this._detailRow('Latitude', pos.latitude.toFixed(6));
    html += this._detailRow('Longitude', pos.longitude.toFixed(6));
    if (pos.altitude !== undefined && pos.altitude !== null) {
        html += this._detailRow('Altitude', `${pos.altitude}m`);
    }
    html += this._detailRow('Map', `<span class="position-link" onclick="window.meshtasticClient.openNodeOnMap('${nodeId}')">View on Map</span>`);
    html += '</div>';
    return html;
},

/**
 * Hide the node detail panel.
 */
hideNodeDetail() {
    const panel = document.getElementById('nodeDetailPanel');
    if (panel) panel.style.display = 'none';
},

/**
 * Helper: render a detail row.
 */
_detailRow(label, value) {
    // Value may contain pre-built HTML (e.g., signal/battery indicators),
    // so only escape plain string values (no HTML tags)
    const safeValue = typeof value === 'string' && !value.includes('<') ? this.escapeHtml(value) : value;
    return `<div class="detail-row"><span class="detail-label">${this.escapeHtml(String(label))}</span><span class="detail-value">${safeValue}</span></div>`;
},

/**
 * Helper: render a battery indicator.
 */
_renderBatteryIndicator(level) {
    const pct = Math.min(100, Math.max(0, level));
    let cls = 'high';
    if (pct <= 20) cls = 'low';
    else if (pct <= 50) cls = 'medium';
    const display = level > 100 ? 'USB' : `${pct}%`;
    return `<span class="battery-indicator"><span class="battery-bar"><span class="battery-fill ${cls}" style="width: ${Math.min(pct, 100)}%;"></span></span> ${display}</span>`;
},

/**
 * Helper: render signal indicator bars based on SNR.
 */
_renderSignalIndicator(snr) {
    // SNR ranges: <-5 poor, -5 to 0 fair, 0 to 5 good, >5 excellent
    let bars = 1;
    if (snr >= 5) bars = 4;
    else if (snr >= 0) bars = 3;
    else if (snr >= -5) bars = 2;

    let html = '<span class="signal-indicator">';
    for (let i = 1; i <= 4; i++) {
        const h = 3 + (i * 2);
        html += `<span class="signal-bar${i <= bars ? ' active' : ''}" style="height: ${h}px;"></span>`;
    }
    html += '</span>';
    return html;
},

/**
 * Helper: format timestamp as relative "time ago".
 */
_timeAgo(unixTimestamp) {
    const now = Math.floor(Date.now() / 1000);
    const diff = now - unixTimestamp;
    if (diff < 0) return 'just now';
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
},

/**
 * Helper: format uptime seconds into human-readable string.
 */
_formatUptime(seconds) {
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    if (h < 24) return `${h}h ${m}m`;
    const d = Math.floor(h / 24);
    return `${d}d ${h % 24}h`;
},

/**
 * Show the node map modal with all nodes that have positions.
 */
async showNodeMap() {
    const modal = document.getElementById('nodeMapModal');
    if (!modal) {
        this.showMessage('Map modal not found', 'error');
        return;
    }

    // Check Leaflet availability
    if (typeof L === 'undefined') {
        this.showMessage('Map library (Leaflet) not loaded. Check internet connection.', 'error');
        return;
    }

    modal.style.display = 'flex';

    // Close button
    const closeBtn = document.getElementById('closeMapModal');
    if (closeBtn) {
        closeBtn.onclick = () => {
            modal.style.display = 'none';
            if (this._map) {
                this._map.remove();
                this._map = null;
            }
        };
    }

    // My Location button
    const myLocBtn = document.getElementById('mapMyLocation');
    if (myLocBtn) {
        myLocBtn.onclick = () => this._zoomToUserLocation();
    }

    // Click outside to close
    modal.onclick = (e) => {
        if (e.target === modal) {
            modal.style.display = 'none';
            if (this._map) {
                this._map.remove();
                this._map = null;
            }
        }
    };

    // Fetch all nodes
    try {
        const response = await fetch('/api/nodes', {
            headers: { 'X-Session-ID': this.sessionId }
        });
        const data = await response.json();

        if (!data.success || !data.data || !data.data.nodes) {
            this.showMessage('Failed to load nodes for map', 'error');
            return;
        }

        const allNodes = data.data.nodes;
        const nodesWithPosition = allNodes.filter(n => n.position && n.position.latitude !== undefined && n.position.longitude !== undefined);

        const countEl = document.getElementById('mapNodeCount');
        if (countEl) countEl.textContent = `${nodesWithPosition.length} of ${allNodes.length} nodes with position`;

        // Initialize map after a short delay to allow modal to render
        setTimeout(() => this._initMap(nodesWithPosition), 100);

    } catch (error) {
        console.error('Error loading nodes for map:', error);
        this.showMessage('Failed to load map data: ' + error.message, 'error');
    }
},

/**
 * Initialize Leaflet map with node markers (with optional clustering).
 * Centers on user location if available, otherwise on node positions.
 */
_initMap(nodes) {
    const mapContainer = document.getElementById('nodeMap');
    if (!mapContainer) return;

    // Clean up previous map and user location state
    if (this._map) {
        this._map.remove();
        this._map = null;
    }
    this._userLocationMarker = null;
    this._userLocationCircle = null;
    this._userLatLng = null;

    // Default center: first node with position, or Singapore
    let centerLat = 1.3521;
    let centerLng = 103.8198;
    if (nodes.length > 0) {
        centerLat = nodes[0].position.latitude;
        centerLng = nodes[0].position.longitude;
    }

    this._map = L.map('nodeMap').setView([centerLat, centerLng], 12);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        maxZoom: 19
    }).addTo(this._map);

    // Add markers (clustered if available)
    const useCluster = typeof L.markerClusterGroup === 'function';
    const clusterGroup = useCluster ? L.markerClusterGroup({
        maxClusterRadius: 50,
        spiderfyOnMaxZoom: true,
        showCoverageOnHover: false,
        zoomToBoundsOnClick: true
    }) : null;

    const markers = [];
    nodes.forEach(node => {
        const marker = this._createNodeMarker(node);
        if (!marker) return;
        if (clusterGroup) {
            clusterGroup.addLayer(marker);
        } else {
            marker.addTo(this._map);
        }
        markers.push(marker);
    });

    if (clusterGroup) this._map.addLayer(clusterGroup);
    this._nodeMarkers = markers;

    // Add user location marker and zoom to it (primary view)
    this._addUserLocationMarker(markers);

    setTimeout(() => {
        if (this._map) this._map.invalidateSize();
    }, 200);
},

/**
 * Add the user's current location to the map using browser Geolocation API.
 * Centers map on user location. Shows a pulsing blue circle distinct from node markers.
 */
_addUserLocationMarker(existingMarkers) {
    if (!this._map || !navigator.geolocation) {
        // No geolocation - fall back to fitting node bounds
        this._fitNodeBounds(existingMarkers);
        return;
    }

    navigator.geolocation.getCurrentPosition(
        (position) => {
            if (!this._map) return;

            const lat = position.coords.latitude;
            const lng = position.coords.longitude;
            const accuracy = position.coords.accuracy;
            this._userLatLng = L.latLng(lat, lng);

            // Pulsing blue dot for user location
            const userIcon = L.divIcon({
                className: 'user-location-marker',
                html: `<div class="user-location-dot">
                    <div class="user-location-pulse"></div>
                    <div class="user-location-center"></div>
                </div>`,
                iconSize: [24, 24],
                iconAnchor: [12, 12],
                popupAnchor: [0, -14]
            });

            this._userLocationMarker = L.marker([lat, lng], { icon: userIcon, zIndexOffset: 1000 });
            this._userLocationMarker.bindPopup(`<div class="node-popup">
                <div class="node-popup-name">Your Location</div>
                <div class="node-popup-detail"><span class="node-popup-label">Accuracy:</span> ${accuracy < 1000 ? Math.round(accuracy) + 'm' : (accuracy / 1000).toFixed(1) + 'km'}</div>
                <div style="margin-top: 4px; font-size: 0.7rem; color: var(--text-tertiary, #999);">${lat.toFixed(5)}, ${lng.toFixed(5)}</div>
            </div>`);
            this._userLocationMarker.addTo(this._map);

            // Accuracy circle
            if (accuracy < 5000) {
                this._userLocationCircle = L.circle([lat, lng], {
                    radius: accuracy,
                    color: '#4285f4',
                    fillColor: '#4285f4',
                    fillOpacity: 0.1,
                    weight: 1
                }).addTo(this._map);
            }

            // Center map on user location with nearby nodes visible
            if (existingMarkers.length > 0) {
                const allPoints = existingMarkers.map(m => m.getLatLng());
                allPoints.push(this._userLatLng);
                const group = L.featureGroup(allPoints.map(p => L.marker(p)));
                this._map.fitBounds(group.getBounds().pad(0.1));
            }
            // Always zoom to user location as primary view
            this._map.setView([lat, lng], 14);
        },
        (error) => {
            console.warn('Geolocation unavailable:', error.message);
            // Fall back to fitting node bounds
            this._fitNodeBounds(existingMarkers);
        },
        { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
    );
},

/**
 * Fit map bounds to node markers only (fallback when no user location).
 */
_fitNodeBounds(markers) {
    if (!this._map || !markers || markers.length === 0) return;
    if (markers.length > 1) {
        const group = L.featureGroup(markers);
        this._map.fitBounds(group.getBounds().pad(0.1));
    } else if (markers.length === 1) {
        this._map.setView(markers[0].getLatLng(), 14);
    }
},

/**
 * Zoom to the user's current location on the map.
 * Called by "My Location" button. Re-requests geolocation for freshness.
 */
_zoomToUserLocation() {
    if (!this._map) return;

    if (!navigator.geolocation) {
        this.showMessage('Geolocation is not supported by this browser', 'error');
        return;
    }

    const btn = document.getElementById('mapMyLocation');
    if (btn) {
        btn.textContent = 'Locating...';
        btn.disabled = true;
    }

    navigator.geolocation.getCurrentPosition(
        (position) => {
            if (!this._map) return;

            const lat = position.coords.latitude;
            const lng = position.coords.longitude;
            const accuracy = position.coords.accuracy;
            this._userLatLng = L.latLng(lat, lng);

            // Remove old user marker/circle if they exist
            if (this._userLocationMarker) {
                this._map.removeLayer(this._userLocationMarker);
            }
            if (this._userLocationCircle) {
                this._map.removeLayer(this._userLocationCircle);
            }

            // Create new marker
            const userIcon = L.divIcon({
                className: 'user-location-marker',
                html: `<div class="user-location-dot">
                    <div class="user-location-pulse"></div>
                    <div class="user-location-center"></div>
                </div>`,
                iconSize: [24, 24],
                iconAnchor: [12, 12],
                popupAnchor: [0, -14]
            });

            this._userLocationMarker = L.marker([lat, lng], { icon: userIcon, zIndexOffset: 1000 });
            this._userLocationMarker.bindPopup(`<div class="node-popup">
                <div class="node-popup-name">Your Location</div>
                <div class="node-popup-detail"><span class="node-popup-label">Accuracy:</span> ${accuracy < 1000 ? Math.round(accuracy) + 'm' : (accuracy / 1000).toFixed(1) + 'km'}</div>
                <div style="margin-top: 4px; font-size: 0.7rem; color: var(--text-tertiary, #999);">${lat.toFixed(5)}, ${lng.toFixed(5)}</div>
            </div>`);
            this._userLocationMarker.addTo(this._map);
            this._userLocationMarker.openPopup();

            if (accuracy < 5000) {
                this._userLocationCircle = L.circle([lat, lng], {
                    radius: accuracy,
                    color: '#4285f4',
                    fillColor: '#4285f4',
                    fillOpacity: 0.1,
                    weight: 1
                }).addTo(this._map);
            }

            // Zoom to user location
            this._map.setView([lat, lng], 15);

            if (btn) {
                btn.textContent = 'My Location';
                btn.disabled = false;
            }
        },
        (error) => {
            console.warn('Geolocation error:', error.message);
            this.showMessage('Could not get your location: ' + error.message, 'error');
            if (btn) {
                btn.textContent = 'My Location';
                btn.disabled = false;
            }
        },
        { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
    );
},

/** Create a Leaflet marker for a single node. Returns null for invalid positions. */
_createNodeMarker(node) {
    const lat = node.position.latitude;
    const lng = node.position.longitude;
    if (lat === 0 && lng === 0) return null;

    const name = node.longName || node.shortName || node.name || node.id;
    const isFav = node.isFavorite ? '⭐ ' : '';

    // Color: favorites=orange, online=green, default=blue
    const lastHeard = node.lastHeard || node.lastSeen;
    const oneHourAgo = Math.floor(Date.now() / 1000) - 3600;
    const isOnline = lastHeard && lastHeard > oneHourAgo;
    let markerColor = '#3b82f6';
    if (node.isFavorite) markerColor = '#F97316';
    else if (isOnline) markerColor = '#059669';

    const icon = L.divIcon({
        className: 'custom-node-marker',
        html: `<div style="
            background: ${markerColor};
            width: 12px; height: 12px;
            border-radius: 50%;
            border: 2px solid white;
            box-shadow: 0 1px 3px rgba(0,0,0,0.4);
        "></div>`,
        iconSize: [16, 16],
        iconAnchor: [8, 8],
        popupAnchor: [0, -10]
    });

    const marker = L.marker([lat, lng], { icon });
    marker.bindPopup(this._buildNodePopupHtml(node, name, isFav, lat, lng));
    return marker;
},

/** Build popup HTML for a map marker. */
_buildNodePopupHtml(node, name, isFav, lat, lng) {
    const safeName = this.escapeHtml(name);
    const safeId = this.escapeHtml(node.id || '');
    let html = `<div class="node-popup">`;
    html += `<div class="node-popup-name">${isFav}${safeName}</div>`;
    html += `<div class="node-popup-id">${safeId}</div>`;
    if (node.hwModel && node.hwModel !== 'Unknown') {
        html += `<div class="node-popup-detail"><span class="node-popup-label">HW:</span> ${this.escapeHtml(node.hwModel)}</div>`;
    }
    if (node.snr !== undefined && node.snr !== null) {
        html += `<div class="node-popup-detail"><span class="node-popup-label">SNR:</span> ${node.snr} dB</div>`;
    }
    if (node.position.altitude !== undefined) {
        html += `<div class="node-popup-detail"><span class="node-popup-label">Alt:</span> ${node.position.altitude}m</div>`;
    }
    if (node.deviceMetrics && node.deviceMetrics.batteryLevel !== undefined) {
        const bl = node.deviceMetrics.batteryLevel;
        html += `<div class="node-popup-detail"><span class="node-popup-label">Battery:</span> ${bl > 100 ? 'USB' : bl + '%'}</div>`;
    }
    if (node.hopsAway !== undefined && node.hopsAway !== null) {
        html += `<div class="node-popup-detail"><span class="node-popup-label">Hops:</span> ${node.hopsAway === 0 ? 'Direct' : node.hopsAway}</div>`;
    }
    if (node.lastHeard || node.lastSeen) {
        html += `<div class="node-popup-detail"><span class="node-popup-label">Heard:</span> ${this._timeAgo(node.lastHeard || node.lastSeen)}</div>`;
    }
    html += `<div style="margin-top: 4px; font-size: 0.7rem; color: var(--text-tertiary, #999);">${lat.toFixed(5)}, ${lng.toFixed(5)}</div>`;
    html += `</div>`;
    return html;
},

/**
 * Open the map centered on a specific node.
 */
async openNodeOnMap(nodeId) {
    await this.showNodeMap();
    // After map loads, try to center on the specific node
    setTimeout(async () => {
        try {
            const response = await fetch(`/api/nodes/${encodeURIComponent(nodeId)}`, {
                headers: { 'X-Session-ID': this.sessionId }
            });
            const data = await response.json();
            if (data.success && data.data && data.data.node && data.data.node.position) {
                const pos = data.data.node.position;
                if (this._map && pos.latitude !== undefined && pos.longitude !== undefined) {
                    this._map.setView([pos.latitude, pos.longitude], 15);
                }
            }
        } catch (err) {
            console.error('Error centering map on node:', err);
        }
    }, 500);
}
});
