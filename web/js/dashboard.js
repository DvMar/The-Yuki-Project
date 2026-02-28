// Dashboard Manager
class Dashboard {
    constructor() {
        this.apiBase = 'http://localhost:8000';
        this.data = null;
        this.autopoieticData = null;
        this.autoRefresh = true;
        this.refreshInterval = null;
        
        this.initialize();
    }
    
    initialize() {
        this.setupEventListeners();
        this.loadData();
        this.startAutoRefresh();

        // Live sidebar updates via telemetry subscription
        if (window.telemetryManager) {
            window.telemetryManager.subscribe(data => this.updateSidebar(data));
        }
    }
    
    setupEventListeners() {
        // Manual refresh button
        const refreshBtn = document.getElementById('refresh-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.loadData(true));
        }
        
        // Auto-refresh toggle
        const autoRefreshToggle = document.getElementById('auto-refresh');
        if (autoRefreshToggle) {
            autoRefreshToggle.addEventListener('change', (e) => {
                this.autoRefresh = e.target.checked;
                if (this.autoRefresh) {
                    this.startAutoRefresh();
                } else {
                    this.stopAutoRefresh();
                }
            });
        }
    }
    
    async loadData(manual = false) {
        const refreshBtn = document.getElementById('refresh-btn');
        
        try {
            if (manual && refreshBtn) {
                refreshBtn.classList.add('loading');
                refreshBtn.disabled = true;
            }
            
            // Use telemetry manager to fetch all data with persistence
            this.data = await window.telemetryManager.fetchAllData();
            this.updateUI();
            this.updateLastRefresh();
            
        } catch (error) {
            console.error('Dashboard load error:', error);
            this.showError(error.message);
        } finally {
            if (refreshBtn) {
                refreshBtn.classList.remove('loading');
                refreshBtn.disabled = false;
            }
        }
    }
    
    updateUI() {
        if (!this.data) return;
        
        // Use telemetry manager getters
        const identityCore = window.telemetryManager.getIdentityCore();
        const emotionalState = window.telemetryManager.getEmotionalState();
        const memoryStats = window.telemetryManager.getMemoryStats();
        const taskReminders = window.telemetryManager.getTaskReminders();
        const dreamcycleStatus = window.telemetryManager.getDreamcycleStatus();
        
        this.updatePersonalityTraits(identityCore);
        this.updateEmotionalState(emotionalState);
        this.updateSystemStats(memoryStats);
        this.updateMemoryInfo();
        this.updateDreamcycleStatus(dreamcycleStatus);
        this.updateSidebar(this.data);
    }
    
    updatePersonalityTraits(traits = null) {
        const container = document.getElementById('personality-traits');
        if (!container) return;
        
        const data = traits || window.telemetryManager.getIdentityCore();
        if (!data || Object.keys(data).length === 0) return;
        
        container.innerHTML = '';
        
        Object.entries(data).forEach(([name, value]) => {
            const traitCard = this.createTraitCard(name, value);
            container.appendChild(traitCard);
        });
    }
    
    updateEmotionalState(emotions = null) {
        const container = document.getElementById('emotional-state');
        if (!container) return;
        
        const data = emotions || window.telemetryManager.getEmotionalState();
        if (!data || Object.keys(data).length === 0) return;
        
        container.innerHTML = '';
        
        Object.entries(data).forEach(([name, value]) => {
            const emotionCard = this.createTraitCard(name, value, 'emotion');
            container.appendChild(emotionCard);
        });
    }
    
    createTraitCard(name, value, type = 'trait') {
        const card = document.createElement('div');
        card.className = 'trait-card fade-in';
        
        const displayName = name.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
        const percentage = Math.round(value * 100);
        const colorClass = this.getValueColorClass(value);
        
        card.innerHTML = `
            <div class="trait-header">
                <div class="trait-name">${displayName}</div>
                <div class="trait-value-display ${colorClass}">${percentage}%</div>
            </div>
            <div class="progress-bar">
                <div class="progress-fill" style="width: ${percentage}%"></div>
            </div>
        `;
        
        return card;
    }
    
    updateSystemStats() {
        const activeTasks = this.data.memory_stats?.active_tasks ?? this.data.task_reminders?.length ?? 0;
        const stats = [
            { id: 'interaction-count', value: this.data.interaction_count || 0, label: 'Interactions' },
            { id: 'user-facts', value: this.data.memory_stats?.user_facts || 0, label: 'User Facts' },
            { id: 'memories', value: this.data.memory_stats?.episodic_memories || 0, label: 'Memories' },
            { id: 'graph-nodes', value: this.data.knowledge_graph_stats?.total_nodes || 0, label: 'Graph Nodes' },
            { id: 'active-tasks', value: activeTasks, label: 'Active Tasks' },
            { id: 'session-messages', value: this.data.session_state?.total_messages || 0, label: 'Session Msgs' }
        ];
        
        stats.forEach(stat => {
            const element = document.getElementById(stat.id);
            if (element) {
                const valueEl = element.querySelector('.stat-value');
                const labelEl = element.querySelector('.stat-label');
                if (valueEl) valueEl.textContent = stat.value;
                if (labelEl) labelEl.textContent = stat.label;
            }
        });
    }
    
    updateMemoryInfo() {
        const container = document.getElementById('recent-memories');
        if (!container) return;
        
        container.innerHTML = '';
        
        // Task reminders
        if (this.data.task_reminders && this.data.task_reminders.length > 0) {
            this.data.task_reminders.slice(0, 3).forEach(task => {
                const item = document.createElement('div');
                item.className = 'memory-item fade-in';
                item.innerHTML = `
                    <div class="memory-topic">Task Reminder</div>
                    ${task}
                `;
                container.appendChild(item);
            });
        }
        
        // Proactive messages
        if (this.data.proactive_messages && this.data.proactive_messages.length > 0) {
            this.data.proactive_messages.slice(0, 2).forEach(msg => {
                const item = document.createElement('div');
                item.className = 'memory-item fade-in';
                item.innerHTML = `
                    <div class="memory-topic">Proactive Thought</div>
                    ${msg.text || msg}
                `;
                container.appendChild(item);
            });
        }

        // Recent state signatures (phase traces)
        if (this.data.recent_state_signatures && this.data.recent_state_signatures.length > 0) {
            this.data.recent_state_signatures.slice(-3).reverse().forEach(sig => {
                const item = document.createElement('div');
                item.className = 'memory-item fade-in';
                item.innerHTML = `
                    <div class="memory-topic">State Signature</div>
                    ${this.formatSignature(sig)}
                `;
                container.appendChild(item);
            });
        }
        
        if (container.children.length === 0) {
            container.innerHTML = `
                <div class="memory-item fade-in">
                    <div class="memory-topic">Status</div>
                    No recent memory activities
                </div>
            `;
        }
    }

    formatSignature(sig = {}) {
        if (!sig || typeof sig !== 'object') return '—';

        const phase = sig.phase || sig.origin || sig.source || 'cycle';
        const policy = sig.policy || sig.last_policy || '—';
        const band = sig.circadian_band || sig.band_label || sig.band || '—';
        const exhausted = sig.is_exhausted ?? sig.cognitive_exhausted;
        const stampRaw = sig.timestamp || sig.at;

        let stamp = '';
        if (stampRaw) {
            const parsed = new Date(stampRaw);
            if (!Number.isNaN(parsed.getTime())) {
                stamp = ` @ ${parsed.toLocaleTimeString()}`;
            }
        }

        return `${phase} • ${policy} • ${band}${exhausted ? ' • exhausted' : ''}${stamp}`;
    }
    
    updateDreamcycleStatus() {
        if (!this.data.dreamcycle_status) return;
        
        const status = this.data.dreamcycle_status;
        
        this.updateElement('dream-idle-time', `${status.idle_seconds || 0}s`);
        this.updateElement('dream-queue-size', status.curiosity_queue_size || 0);
        this.updateElement('dream-desire', Math.round((status.desire_to_connect || 0) * 100) + '%');
        this.updateElement('dream-running', status.running ? 'Active' : 'Stopped');
        
        // Last dream mode
        const modeElement = document.getElementById('dream-mode');
        if (modeElement) {
            const mode = status.last_dream_mode || 'None';
            modeElement.textContent = mode.charAt(0).toUpperCase() + mode.slice(1);
        }
    }
    
    updateSidebar(data) {
        if (!data) return;

        // Connection indicator
        const connEl = document.getElementById('connection-status');
        if (connEl) {
            connEl.className = 'connection-status connected';
            connEl.innerHTML = '<span class="status-dot status-online"></span>Connected';
        }

        const set = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.textContent = val;
        };

        set('sb-interactions',  data.interaction_count ?? '—');
        set('sb-session-msgs',  data.session_state?.total_messages ?? '—');
        set('sb-updated',       new Date().toLocaleTimeString());
        set('sb-facts',         data.memory_stats?.user_facts ?? '—');
        set('sb-episodic',      data.memory_stats?.episodic_memories ?? '—');
        set('sb-entities',      data.knowledge_graph_stats?.total_nodes ?? '—');

        const dc = data.dreamcycle_status || {};
        set('sb-dream-mode',    dc.last_dream_mode || 'None');
        set('sb-idle',          dc.idle_seconds != null ? `${dc.idle_seconds}s` : '—');
        set('sb-desire',        dc.desire_to_connect != null ? Math.round(dc.desire_to_connect * 100) + '%' : '—');
    }

    updateConnectionStatus(connected) {
        const connEl = document.getElementById('connection-status');
        if (!connEl) return;
        if (connected) {
            connEl.className = 'connection-status connected';
            connEl.innerHTML = '<span class="status-dot status-online"></span>Connected';
        } else {
            connEl.className = 'connection-status disconnected';
            connEl.innerHTML = '<span class="status-dot status-offline"></span>Offline';
        }
    }

    updateElement(id, value) {
        const element = document.getElementById(id);
        if (element) {
            element.textContent = value;
        }
    }
    
    getValueColorClass(value) {
        if (value >= 0.7) return 'excellent';
        if (value >= 0.4) return 'good';
        return 'warning';
    }
    
    updateLastRefresh() {
        const element = document.getElementById('last-updated');
        if (element) {
            const now = new Date();
            element.textContent = `Last updated: ${now.toLocaleTimeString()}`;
        }
    }
    
    startAutoRefresh() {
        if (this.refreshInterval) return;
        
        this.refreshInterval = setInterval(() => {
            if (this.autoRefresh) {
                this.loadData();
            }
        }, 15000); // Refresh every 15 seconds
    }
    
    stopAutoRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
            this.refreshInterval = null;
        }
    }
    
    showError(message) {
        // You could implement a toast notification system here
        console.error('Dashboard error:', message);
    }
}

// Initialize dashboard when page loads
document.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new Dashboard();
});