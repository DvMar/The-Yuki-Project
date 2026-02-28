// Unified telemetry and state manager for all web UI pages
class TelemetryManager {
    constructor() {
        this.apiBase = 'http://localhost:8000';
        this.data = null;
        this.lastUpdate = null;
        this.updateInterval = 5000; // 5 seconds
        this.listeners = [];
        
        // Initialize from localStorage
        this.loadPersistedData();
    }
    
    // ============================================================
    // Data Loading
    // ============================================================
    
    async fetchAllData() {
        try {
            // Test server connectivity first
            const healthCheck = await fetch(`${this.apiBase}/performance/stats`, { 
                signal: AbortSignal.timeout(2000) // 2-second timeout
            }).catch(() => null);
            
            // If server is down, return cached data without wiping dreams
            if (!healthCheck || !healthCheck.ok) {
                console.warn('Server unreachable, using cached data');
                return this.data || {};
            }
            
            const [
                latestLog,
                perfStats,
                autopoieticStatus,
                dreamcycleDebug,
                dreamMessages,
                reflectionSummary
            ] = await Promise.all([
                fetch(`${this.apiBase}/latest_log`).then(r => r.json()).catch(() => ({})),
                fetch(`${this.apiBase}/performance/stats`).then(r => r.json()).catch(() => ({})),
                fetch(`${this.apiBase}/autopoietic/status`).then(r => r.json()).catch(() => ({})),
                fetch(`${this.apiBase}/debug/dreamcycle`).then(r => r.json()).catch(() => ({})),
                this.fetchDreamMessages(),
                fetch(`${this.apiBase}/reflection/summary`).then(r => r.json()).catch(() => ({}))
            ]);
            
            // Auto-clear stale localStorage when server has restarted fresh
            const serverCount = latestLog.interaction_count || 0;
            const cachedCount = (this.data && this.data.interaction_count) || 0;
            if (serverCount === 0 && cachedCount > 0) {
                console.info('[Telemetry] Server restart detected — clearing stale local data');
                localStorage.removeItem('yuki-dreams');
                localStorage.removeItem('yuki-conversation-history');
                this.data = null;
            }

            this.data = {
                timestamp: new Date().toISOString(),
                latestLog,
                perfStats,
                autopoieticStatus,
                dreamcycleDebug,
                dreamMessages: dreamMessages || [],
                reflectionSummary,
                identity_core: latestLog.identity_core || {},
                emotional_state: latestLog.emotional_state || {},
                interaction_count: latestLog.interaction_count || 0,
                memory_stats: latestLog.memory_stats || {},
                session_state: latestLog.session_state || {},
                task_reminders: latestLog.task_reminders || [],
                proactive_messages: latestLog.proactive_messages || [],
                postprocess_telemetry: latestLog.postprocess_telemetry || {},
                llm_performance: latestLog.llm_performance || {},
                buffer_stats: latestLog.buffer_stats || {},
                knowledge_graph_stats: latestLog.knowledge_graph_stats || {},
                dreamcycle_status: latestLog.dreamcycle_status || {},
                enactive_nexus:    latestLog.enactive_nexus    || {},
                // Synthetic-life extensions (not auto-promoted from latestLog by default)
                circadian:         latestLog.circadian          || {},
                cognitive_load:    latestLog.cognitive_load     || {},
                user_model_stats:  latestLog.user_model_stats   || {},
                temporal_policy_trace: latestLog.temporal_policy_trace || {},
                proactive_intentions:  latestLog.proactive_intentions  || {},
                recent_state_signatures: latestLog.recent_state_signatures || [],
            };
            
            this.lastUpdate = new Date();
            this.persistData();
            this.notifyListeners();
            
            return this.data;
        } catch (error) {
            console.error('Telemetry fetch error:', error);
            return this.data || {};
        }
    }
    
    // ============================================================
    // Dream Message Management (Persistent)
    // ============================================================
    
    async fetchDreamMessages() {
        try {
            // Get all available dreams from queue
            const dreams = [];
            let attempts = 0;
            const maxAttempts = 5;
            
            while (attempts < maxAttempts) {
                const response = await fetch(`${this.apiBase}/dreamcycle/pop`);
                
                // If server is unreachable, clear stale dreams and return empty
                if (!response.ok) {
                    console.warn('Server unreachable, using persisted dreams');
                    return this.getPersistedDreams();
                }
                
                const data = await response.json();
                
                if (data.message) {
                    dreams.push({
                        text: data.message.text || data.message,
                        timestamp: data.message.timestamp || new Date().toISOString(),
                        metadata: data.message.metadata || {},
                        id: `dream-${Date.now()}-${Math.random()}`
                    });
                } else {
                    break;
                }
                
                attempts++;
            }
            
            // Load persisted dreams from localStorage
            const persistedDreams = this.getPersistedDreams();
            
            // Combine and deduplicate
            const allDreams = [...persistedDreams, ...dreams];
            const uniqueDreams = Array.from(
                new Map(allDreams.map(d => [d.id || d.text + d.timestamp, d])).values()
            );
            
            // Keep only last 20 dreams
            const recentDreams = uniqueDreams.slice(-20);
            this.persistDreams(recentDreams);
            
            return recentDreams;
        } catch (error) {
            // Network error — return persisted dreams, do not wipe them
            console.warn('Network error fetching dreams, using persisted data');
            return this.getPersistedDreams();
        }
    }
    
    persistDreams(dreams) {
        try {
            localStorage.setItem('yuki-dreams', JSON.stringify(dreams));
        } catch (error) {
            console.warn('Failed to persist dreams:', error);
        }
    }
    
    getPersistedDreams() {
        try {
            const dreams = localStorage.getItem('yuki-dreams');
            return dreams ? JSON.parse(dreams) : [];
        } catch (error) {
            console.warn('Failed to load persisted dreams:', error);
            return [];
        }
    }
    
    addDream(text, metadata = {}) {
        const dream = {
            text,
            timestamp: new Date().toISOString(),
            metadata,
            id: `dream-${Date.now()}-${Math.random()}`
        };
        
        const dreams = this.getPersistedDreams();
        dreams.push(dream);
        
        // Keep only last 20
        const recent = dreams.slice(-20);
        this.persistDreams(recent);
        
        return dream;
    }
    
    // ============================================================
    // Data Persistence
    // ============================================================
    
    persistData() {
        try {
            const toStore = {
                timestamp: this.data.timestamp,
                identity_core: this.data.identity_core,
                emotional_state: this.data.emotional_state,
                interaction_count: this.data.interaction_count,
                memory_stats: this.data.memory_stats,
                task_reminders: this.data.task_reminders,
                llm_performance: this.data.llm_performance
            };
            localStorage.setItem('yuki-telemetry', JSON.stringify(toStore));
        } catch (error) {
            console.warn('Failed to persist telemetry:', error);
        }
    }
    
    loadPersistedData() {
        try {
            const stored = localStorage.getItem('yuki-telemetry');
            if (stored) {
                this.data = JSON.parse(stored);
            }
        } catch (error) {
            console.warn('Failed to load persisted telemetry:', error);
        }
    }
    
    // ============================================================
    // Listener Pattern
    // ============================================================
    
    subscribe(listener) {
        this.listeners.push(listener);
        return () => {
            this.listeners = this.listeners.filter(l => l !== listener);
        };
    }
    
    notifyListeners() {
        this.listeners.forEach(listener => {
            try {
                listener(this.data);
            } catch (error) {
                console.error('Listener error:', error);
            }
        });
    }
    
    // ============================================================
    // Getters for UI Components
    // ============================================================
    
    getIdentityCore() {
        return this.data?.identity_core || {};
    }
    
    getEmotionalState() {
        return this.data?.emotional_state || {};
    }
    
    getDreams() {
        return this.data?.dreamMessages || this.getPersistedDreams();
    }
    
    getMemoryStats() {
        return this.data?.memory_stats || {};
    }
    
    getLLMStats() {
        return {
            ...this.data?.llm_performance,
            ...this.data?.perfStats?.llm
        };
    }
    
    getBufferStats() {
        return {
            ...this.data?.buffer_stats,
            ...this.data?.perfStats?.memory_buffer
        };
    }
    
    getAutopoieticStatus() {
        return this.data?.autopoieticStatus || {};
    }
    
    getDreamcycleStatus() {
        return this.data?.dreamcycleDebug?.daemon_status || {};
    }

    getEnactiveNexusStatus() {
        return this.data?.enactive_nexus || {};
    }
    
    getTaskReminders() {
        return this.data?.task_reminders || [];
    }
    
    clearDreams() {
        try {
            localStorage.removeItem('yuki-dreams');
        } catch (error) {
            console.warn('Failed to clear dreams:', error);
        }
    }

    clearAllData() {
        try {
            localStorage.removeItem('yuki-telemetry');
            localStorage.removeItem('yuki-dreams');
            this.data = null;
        } catch (error) {
            console.warn('Failed to clear persisted data:', error);
        }
    }
}

// Global telemetry manager instance
window.telemetryManager = new TelemetryManager();

// Auto-fetch data at intervals
setInterval(() => {
    window.telemetryManager.fetchAllData();
}, window.telemetryManager.updateInterval);

// Initial fetch
window.telemetryManager.fetchAllData();

// ============================================================
// WsTelemetryBridge
// Real-time WebSocket overlay at /ws/telemetry.
// Fires custom window events consumed by connectome.js:
//   • 'ws:heartbeat'           — server heartbeat tick
//   • 'ws:telemetry_update'    — node/synapse value update
//   • 'ws:chroma_retrieval'    — high-salience memory hit (spawn neuron)
//   • 'ws:status'              — connection state change
//
// Falls back gracefully when the endpoint is absent — the
// REST-polling TelemetryManager above continues to work.
// ============================================================
class WsTelemetryBridge {
    constructor(path = '/ws/telemetry') {
        this.path          = path;
        this.ws            = null;
        this.reconnectDelay = 2000;
        this.maxDelay       = 30000;
        this._currentDelay  = this.reconnectDelay;
        this._stopped       = false;
        this._connect();
    }

    _connect() {
        if (this._stopped) return;
        const proto = location.protocol === 'https:' ? 'wss' : 'ws';
        const url   = `${proto}://${location.host}${this.path}`;

        try {
            this.ws = new WebSocket(url);
        } catch (e) {
            console.warn('[WsBridge] Cannot open WebSocket:', e);
            this._scheduleReconnect();
            return;
        }

        this.ws.onopen = () => {
            console.info('[WsBridge] Connected →', url);
            this._currentDelay = this.reconnectDelay;
            this._emit('ws:status', { connected: true });
        };

        this.ws.onclose = () => {
            this._emit('ws:status', { connected: false });
            this._scheduleReconnect();
        };

        this.ws.onerror = (err) => {
            console.warn('[WsBridge] Error', err);
        };

        this.ws.onmessage = (event) => {
            let packet;
            try { packet = JSON.parse(event.data); }
            catch { return; }
            this._dispatch(packet);
        };
    }

    _dispatch(packet) {
        const type = packet.type || '';

        if (type === 'heartbeat' || type === 'server_heartbeat') {
            this._emit('ws:heartbeat', packet);
            return;
        }

        if (type === 'telemetry_update') {
            this._emit('ws:telemetry_update', packet);
            // Bridge into REST-based TelemetryManager so sidebar updates too
            if (window.telemetryManager && packet.data) {
                _deepMerge(window.telemetryManager.data ||= {}, packet.data);
                window.telemetryManager.notifyListeners();
            }
            return;
        }

        if (type === 'chroma_retrieval') {
            const salience = Number(packet.salience ?? packet.score ?? 0);
            if (salience > 0.6) {
                this._emit('ws:chroma_retrieval', {
                    label:    packet.label || packet.summary || packet.text || 'Memory fragment',
                    salience,
                    metadata: packet.metadata || {}
                });
            }
            return;
        }

        // Generic forward — broadcast any other typed telemetry packet
        this._emit('ws:' + type, packet);
    }

    _emit(eventName, detail) {
        window.dispatchEvent(new CustomEvent(eventName, { detail }));
    }

    _scheduleReconnect() {
        if (this._stopped) return;
        setTimeout(() => this._connect(), this._currentDelay);
        this._currentDelay = Math.min(this._currentDelay * 1.6, this.maxDelay);
    }

    stop() {
        this._stopped = true;
        this.ws && this.ws.close();
    }
}

/** Deep-merge src into dst (shallow for nested objects, non-destructive for arrays). */
function _deepMerge(dst, src) {
    for (const [k, v] of Object.entries(src)) {
        if (v && typeof v === 'object' && !Array.isArray(v) &&
            dst[k] && typeof dst[k] === 'object') {
            _deepMerge(dst[k], v);
        } else {
            dst[k] = v;
        }
    }
}

// Start the WebSocket bridge only on pages that need live synapse events
// (currently the connectome page). Other pages continue with REST polling.
window.wsTelemetryBridge = null;
document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('connectome-svg')) {
        window.wsTelemetryBridge = new WsTelemetryBridge('/ws/telemetry');
    }
});
