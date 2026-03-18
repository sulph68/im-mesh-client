/**
 * HTML5 Local Storage for Meshtastic Web Client
 * Replaces server-side SQLite database per architecture requirements
 */

class MeshtasticStorage {
    constructor(sessionId) {
        this.sessionId = sessionId;
        this.storagePrefix = `meshtastic_${sessionId}_`;
        this.init();
    }
    
    init() {
        // Initialize storage structure if not exists
        if (!this.getItem('initialized')) {
            this.setItem('initialized', true);
            this.setItem('nodes', []);
            this.setItem('channels', []);
            this.setItem('messages', []);
            this.setItem('device_config', {});
            this.setItem('session_info', {});
            this.setItem('favorites', []);
        }
    }
    
    // Generic storage methods
    getItem(key) {
        const item = localStorage.getItem(this.storagePrefix + key);
        try {
            return item ? JSON.parse(item) : null;
        } catch (e) {
            console.error('Error parsing storage item:', key, e);
            return null;
        }
    }
    
    setItem(key, value) {
        try {
            localStorage.setItem(this.storagePrefix + key, JSON.stringify(value));
            return true;
        } catch (e) {
            console.error('Error saving to storage:', key, e);
            return false;
        }
    }
    
    removeItem(key) {
        localStorage.removeItem(this.storagePrefix + key);
    }
    
    // Clear specific data type or all data for this session
    clear(key) {
        if (key) {
            // Clear specific item
            this.removeItem(key);
        } else {
            // Clear all items for this session
            this.clearAll();
        }
    }
    
    // Node management
    getNodes() {
        return this.getItem('nodes') || [];
    }
    
    addOrUpdateNode(nodeData) {
        const nodes = this.getNodes();
        // Use 'id' field from API response, but also handle 'node_id' for compatibility
        const nodeId = nodeData.id || nodeData.node_id;
        const existingIndex = nodes.findIndex(n => (n.id || n.node_id) === nodeId);
        
        if (existingIndex >= 0) {
            // Update existing node
            nodes[existingIndex] = { ...nodes[existingIndex], ...nodeData };
        } else {
            // Add new node
            nodes.push(nodeData);
        }
        
        this.setItem('nodes', nodes);
        return nodeData;
    }
    
    removeNode(nodeId) {
        const nodes = this.getNodes().filter(n => n.node_id !== nodeId);
        this.setItem('nodes', nodes);
    }
    
    // Channel management
    getChannels() {
        return this.getItem('channels') || [];
    }
    
    addOrUpdateChannel(channelData) {
        const channels = this.getChannels();
        const existingIndex = channels.findIndex(c => c.index === channelData.index);
        
        if (existingIndex >= 0) {
            channels[existingIndex] = { ...channels[existingIndex], ...channelData };
        } else {
            channels.push(channelData);
        }
        
        this.setItem('channels', channels);
        return channelData;
    }
    
    removeChannel(index) {
        const channels = this.getChannels().filter(c => c.index !== index);
        this.setItem('channels', channels);
    }
    
    // Message management
    getMessages(limit = 100) {
        const messages = this.getItem('messages') || [];
        return messages.slice(-limit); // Get last N messages
    }
    
    addMessage(messageData) {
        // Read raw from localStorage to avoid the slice in getMessages()
        const raw = localStorage.getItem(this.storagePrefix + 'messages');
        let messages;
        try {
            messages = raw ? JSON.parse(raw) : [];
        } catch (e) {
            messages = [];
        }
        
        // Add timestamp if not present
        if (!messageData.timestamp) {
            messageData.timestamp = new Date().toISOString();
        }
        
        // Add unique ID if not present
        if (!messageData.id) {
            messageData.id = Date.now() + '_' + Math.random().toString(36).substr(2, 9);
        }
        
        messages.push(messageData);
        
        // Keep only last 500 messages to prevent storage bloat
        const maxMessages = 500;
        if (messages.length > maxMessages) {
            messages.splice(0, messages.length - maxMessages);
        }
        
        this.setItem('messages', messages);
        return messageData;
    }
    
    // Favorites management
    getFavorites() {
        return this.getItem('favorites') || [];
    }
    
    addFavorite(nodeId) {
        const favorites = this.getFavorites();
        if (!favorites.includes(nodeId)) {
            favorites.push(nodeId);
            this.setItem('favorites', favorites);
            
            // Update node's favorite status
            const nodes = this.getNodes();
            const node = nodes.find(n => n.node_id === nodeId);
            if (node) {
                node.is_favorite = true;
                this.setItem('nodes', nodes);
            }
        }
    }
    
    removeFavorite(nodeId) {
        const favorites = this.getFavorites().filter(id => id !== nodeId);
        this.setItem('favorites', favorites);
        
        // Update node's favorite status
        const nodes = this.getNodes();
        const node = nodes.find(n => n.node_id === nodeId);
        if (node) {
            node.is_favorite = false;
            this.setItem('nodes', nodes);
        }
    }
    
    // Device configuration
    getDeviceConfig() {
        return this.getItem('device_config') || {};
    }
    
    setDeviceConfig(config) {
        this.setItem('device_config', config);
    }
    
    // Session info
    getSessionInfo() {
        return this.getItem('session_info') || {};
    }
    
    setSessionInfo(info) {
        this.setItem('session_info', info);
    }
    
    // Statistics
    getStats() {
        const nodes = this.getNodes();
        const messages = this.getMessages();
        const channels = this.getChannels();
        const favorites = this.getFavorites();
        
        return {
            totalNodes: nodes.length,
            onlineNodes: nodes.filter(n => n.is_online).length,
            favoriteNodes: favorites.length,
            totalChannels: channels.length,
            messageCount: messages.length,
            fragmentCount: 0 // Fragments tracked server-side in SQLite
        };
    }
    
    // Clear all data for this session
    clearAll() {
        const keys = [];
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            if (key.startsWith(this.storagePrefix)) {
                keys.push(key);
            }
        }
        
        keys.forEach(key => localStorage.removeItem(key));
    }
    
    // Export data (for debugging/backup)
    exportData() {
        const data = {};
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            if (key.startsWith(this.storagePrefix)) {
                const shortKey = key.replace(this.storagePrefix, '');
                data[shortKey] = this.getItem(shortKey);
            }
        }
        return data;
    }
}

// Make available globally
window.MeshtasticStorage = MeshtasticStorage;