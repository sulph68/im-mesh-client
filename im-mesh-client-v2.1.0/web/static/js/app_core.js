/**
 * Im Mesh Client v2.1 - Multi-tenant
 * Core: Class definition, constructor, init, setup, event listeners.
 * Methods added by js/app_connection.js, js/app_data.js, js/app_nodes.js,
 * js/app_ui.js, js/app_sessions.js, js/app_messages.js, js/app_images.js.
 */

class MeshtasticClient {
    constructor() {
        this.sessionId = null;
        this.ws = null;
        this.connected = false;
        this.storage = null;
        this.selectedNodeId = null;
        this.selectedChannelIndex = 0;
        this.selectedChannelName = 'Primary Channel';
        this.sendTarget = { type: 'channel', id: 0, name: 'Primary Channel' };

        // Message queue: ensures messages are sent 3 seconds apart
        this._messageQueue = [];
        this._messageQueueProcessing = false;
        this._messageQueueDelay = 3000;  // 3 seconds between messages
        this._imageSegmentAckHandler = null;  // Set during image segment sends

        // Unread message tracking: { targetKey: count }
        this._unreadCounts = {};
        // Nodes with unread messages (for sorting)
        this._nodesWithUnread = new Set();

        // WebSocket reconnection tracking
        this._wsReconnectTimer = null;
        this._wsReconnectAttempts = 0;
        this._wsMaxReconnectAttempts = 50;  // Stop after 50 attempts (~500s)
        this._wsReconnectDelay = 10000;  // 10 seconds between attempts
        this._connectionType = 'tcp';  // 'tcp' or 'serial'

        // WebSocket heartbeat tracking
        this._heartbeatInterval = null;
        this._heartbeatTimeout = null;
        this._heartbeatIntervalMs = 30000;  // Ping every 30 seconds
        this._heartbeatTimeoutMs = 10000;   // Pong must arrive within 10s
        this._lastPongTime = null;
        this._lastLatencyMs = null;

        // Statistics auto-refresh
        this._statsRefreshInterval = null;
        this._statsRefreshMs = 60000;  // Refresh stats every 60 seconds

        // Node data cache for filtering
        this._allNodes = [];
        this._nodeSearchQuery = '';

        // Mobile/desktop layout mode
        this._isMobile = null;          // null = auto, true/false = manual override
        this._mobileAutoDetect = true;  // Whether to auto-detect
        this._activeTab = 'chat';       // Current mobile tab: channels, chat, nodes, more

        try {
            this.init();
        } catch (error) {
            console.error('Initialization error:', error);
            this.showMessage('Initialization failed: ' + error.message, 'error');
        }
    }

    init() {
        // Wait for DOM to be ready
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this.setup());
        } else {
            this.setup();
        }
    }

    setup() {
        try {
            this.setupFormHandler();
            this.setupEventListeners();
            this._initMobileLayout();
            this.loadExistingSessions();
            this._tryAutoRestore();

            // Clear (*) notification in title when tab is focused
            window.addEventListener('focus', () => {
                if (document.title.startsWith('(*)')) {
                    document.title = document.title.replace(/^\(\*\)\s*/, '');
                }
            });
        } catch (error) {
            console.error('Setup error:', error);
            this.showMessage('Setup failed: ' + error.message, 'error');
        }
    }

    setupFormHandler() {
        const form = document.getElementById('sessionForm');
        const button = document.querySelector('button[type="submit"]');

        if (form) {
            // Prevent default form submission
            form.addEventListener('submit', (e) => {
                e.preventDefault();
                e.stopPropagation();
                this.handleLogin();
            });
        } else {
            console.error('Form element #sessionForm not found!');
        }

        if (button) {
            // Backup button handler
            button.addEventListener('click', (e) => {
                // Only prevent default if this is a form submit
                if (e.target.type === 'submit') {
                    e.preventDefault();
                    e.stopPropagation();
                    this.handleLogin();
                }
            });
        } else {
            console.error('Submit button not found!');
        }
    }

    setupEventListeners() {
        try {
            this._setupMessageInputListeners();
            this._setupLogListeners();
            this._setupNavigationListeners();
            this._setupImageUploadListeners();
            this._setupSettingsListeners();
            this._setupModalBackdropListeners();
            this._setupNodeSearchListener();
            this._setupKeyboardShortcuts();
        } catch (error) {
            console.error('Event listener setup error:', error);
        }
    }

    /** Message input: Enter-to-send and send button. */
    _setupMessageInputListeners() {
        const messageInput = document.getElementById('messageInput');
        const sendButton = document.getElementById('sendButton');
        if (messageInput) {
            messageInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendMessage();
                }
            });
        }
        if (sendButton) {
            sendButton.addEventListener('click', () => this.sendMessage());
        }
    }

    /** Communication log: show/toggle/clear buttons, log modal, resize handle. */
    _setupLogListeners() {
        const showLogBtn = document.getElementById('showLogBtn');
        const toggleLogBtn = document.getElementById('toggleLog');
        const clearLogBtn = document.getElementById('clearLog');
        if (showLogBtn) showLogBtn.addEventListener('click', () => this.toggleCommunicationLog());
        if (toggleLogBtn) toggleLogBtn.addEventListener('click', () => this.toggleCommunicationLog());
        if (clearLogBtn) clearLogBtn.addEventListener('click', () => this.clearCommunicationLog());

        const closeLogModalBtn = document.getElementById('closeLogModal');
        if (closeLogModalBtn) closeLogModalBtn.addEventListener('click', () => this._closeLogModal());
        const clearLogModalBtn = document.getElementById('clearLogModal');
        if (clearLogModalBtn) clearLogModalBtn.addEventListener('click', () => this.clearCommunicationLog());

        this._initLogResize();
    }

    /** Disconnect, layout toggle, mobile tab bar. */
    _setupNavigationListeners() {
        const disconnectBtn = document.getElementById('disconnectBtn');
        if (disconnectBtn) disconnectBtn.addEventListener('click', () => this.disconnect());

        const toggleLayoutBtn = document.getElementById('toggleLayoutBtn');
        if (toggleLayoutBtn) toggleLayoutBtn.addEventListener('click', () => this._toggleMobileLayout());

        document.querySelectorAll('.mobile-tab').forEach(tab => {
            tab.addEventListener('click', (e) => {
                const tabName = e.currentTarget.dataset.tab;
                if (tabName) this._switchMobileTab(tabName);
            });
        });
    }

    /** Image upload modal: open/close, file select, encode preview, size change, send. */
    _setupImageUploadListeners() {
        const uploadImageBtn = document.getElementById('uploadImageButton');
        if (uploadImageBtn) uploadImageBtn.addEventListener('click', () => this.openImageUploadModal());

        const closeImageModal = document.getElementById('closeImageModal');
        if (closeImageModal) closeImageModal.addEventListener('click', () => this.closeImageUploadModal());

        const imageFileInput = document.getElementById('imageFileInput');
        if (imageFileInput) imageFileInput.addEventListener('change', (e) => this.handleImageSelected(e));

        const encodePreviewBtn = document.getElementById('encodePreviewBtn');
        if (encodePreviewBtn) encodePreviewBtn.addEventListener('click', () => this.encodeImagePreview());

        const encImageSize = document.getElementById('encImageSize');
        if (encImageSize) {
            encImageSize.addEventListener('change', () => {
                if (this._selectedImageFile) this.encodeImagePreview();
            });
        }

        const confirmImageUpload = document.getElementById('confirmImageUpload');
        if (confirmImageUpload) confirmImageUpload.addEventListener('click', () => this.sendImageSegments());
    }

    /** Settings modal: open/close/save, export messages. */
    _setupSettingsListeners() {
        const settingsBtn = document.getElementById('settingsBtn');
        if (settingsBtn) settingsBtn.addEventListener('click', () => this.openSettingsModal());

        const closeSettingsModal = document.getElementById('closeSettingsModal');
        if (closeSettingsModal) closeSettingsModal.addEventListener('click', () => this.closeSettingsModal());

        const cancelSettingsBtn = document.getElementById('cancelSettingsBtn');
        if (cancelSettingsBtn) cancelSettingsBtn.addEventListener('click', () => this.closeSettingsModal());

        const saveSettingsBtn = document.getElementById('saveSettingsBtn');
        if (saveSettingsBtn) saveSettingsBtn.addEventListener('click', () => this.saveSettings());

        const exportMessagesBtn = document.getElementById('exportMessagesBtn');
        if (exportMessagesBtn) exportMessagesBtn.addEventListener('click', () => this.exportMessages());
    }

    /** Close any modal on backdrop click. */
    _setupModalBackdropListeners() {
        document.querySelectorAll('.modal').forEach(modal => {
            modal.addEventListener('click', (e) => {
                if (e.target === modal) modal.style.display = 'none';
            });
        });
    }

    /** Node search input with debounced filtering. */
    _setupNodeSearchListener() {
        const nodeSearchInput = document.getElementById('nodeSearchInput');
        if (nodeSearchInput) {
            let _searchDebounce = null;
            nodeSearchInput.addEventListener('input', (e) => {
                this._nodeSearchQuery = e.target.value.trim().toLowerCase();
                if (_searchDebounce) clearTimeout(_searchDebounce);
                _searchDebounce = setTimeout(() => this._renderFilteredNodes(), 150);
            });
        }
    }

    /** Escape closes modals; Ctrl+K focus message; Ctrl+Shift+F focus search; Ctrl+Shift+L toggle log. */
    _setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                document.querySelectorAll('.modal').forEach(modal => {
                    if (modal.style.display !== 'none') modal.style.display = 'none';
                });
            }
            if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                e.preventDefault();
                const input = document.getElementById('messageInput');
                if (input) input.focus();
            }
            if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'F') {
                e.preventDefault();
                const search = document.getElementById('nodeSearchInput');
                if (search) search.focus();
            }
            if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'L') {
                e.preventDefault();
                const logPanel = document.getElementById('logPanel');
                if (logPanel) {
                    logPanel.style.display = logPanel.style.display === 'none' ? 'block' : 'none';
                }
            }
        });
    }
}
