// Autopoietic Systems Dashboard Manager
class AutopoieticDashboard {
    constructor() {
        this.apiBase = 'http://localhost:8000';
        this.data = null;
        this.autoRefresh = true;
        this.refreshInterval = null;
        
        this.initialize();
    }
    
    initialize() {
        this.setupEventListeners();
        this.loadData();
        this.startAutoRefresh();

        // Tab switching
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
                document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
                btn.classList.add('active');
                const panel = document.getElementById('panel-' + btn.dataset.panel);
                if (panel) panel.classList.add('active');
            });
        });

        // Live updates via telemetry subscription
        if (window.telemetryManager) {
            window.telemetryManager.subscribe(data => {
                this.updateSidebarFromTelemetry(data);
                this.updatePerformanceTab();
            });
        }
    }
    
    setupEventListeners() {
        // Manual refresh button
        const refreshBtn = document.getElementById('refresh-autopoietic-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.loadData(true));
        }

        // Enhancement toggle button
        const toggleBtn = document.getElementById('toggle-enhancement-btn');
        if (toggleBtn) {
            toggleBtn.addEventListener('click', () => this.toggleEnhancement());
        }

        // Flush buffer button
        const flushBtn = document.getElementById('flush-buffer-btn');
        if (flushBtn) {
            flushBtn.addEventListener('click', () => this.flushBuffer());
        }
    }
    
    async loadData(manual = false) {
        const refreshBtn = document.getElementById('refresh-autopoietic-btn');
        
        try {
            if (manual && refreshBtn) {
                refreshBtn.classList.add('loading');
                refreshBtn.disabled = true;
            }
            
            // Use unified telemetry manager instead of direct API calls
            if (window.telemetryManager) {
                await window.telemetryManager.fetchAllData();
                this.data = window.telemetryManager.getAutopoieticStatus();
            } else {
                // Fallback to direct fetch if telemetry manager not available
                const statusResponse = await fetch(`${this.apiBase}/autopoietic/status`);
                if (statusResponse.ok) {
                    this.data = await statusResponse.json();
                }
            }
            
            this.updateUI();
            this.updateLastRefresh();
            this.updateConnectionStatus(true);
            this.updatePerformanceTab();
            this.updateSidebarFromTelemetry(window.telemetryManager?.data || {});
            
        } catch (error) {
            console.error('Autopoietic data load error:', error);
            this.updateConnectionStatus(false, error.message);
        } finally {
            if (refreshBtn) {
                refreshBtn.classList.remove('loading');
                refreshBtn.disabled = false;
            }
        }
    }
    
    updateUI() {
        if (!this.data) {
            this.showNotInitialized();
            return;
        }
        
        this.updateSystemOverview();
        this.updateArchitecturalPlasticity();
        this.updateGoalFormation();
        this.updateRecursiveReflection();
        this.updateMetaLearning();
        this.updateRecentActivity();
        this.updateEnhancementStatus();
        this.updatePerformanceTab();
    }
    
    showNotInitialized() {
        this.updateElement('total-cycles', '0');
        this.updateElement('active-subsystems', '0');
        this.updateElement('last-cycle-time', 'Not Init');
        this.updateElement('system-health', 'N/A');
        
        const statusBadge = document.getElementById('enhancement-status');
        if (statusBadge) {
            statusBadge.textContent = 'Not Initialized';
            statusBadge.className = 'badge badge-warning';
        }
    }
    
    updateSystemOverview() {
        this.updateElement('total-cycles', this.data.cycles_completed || 0);
        
        // Count active subsystems
        let activeCount = 0;
        if (this.data.architectural_plasticity) activeCount++;
        if (this.data.goal_formation) activeCount++;
        if (this.data.recursive_reflection) activeCount++;
        if (this.data.meta_learning) activeCount++;
        
        this.updateElement('active-subsystems', activeCount);
        
        // Format last cycle time
        const lastCycle = this.data.last_cycle;
        if (lastCycle) {
            const date = new Date(lastCycle);
            this.updateElement('last-cycle-time', date.toLocaleTimeString());
        } else {
            this.updateElement('last-cycle-time', 'Never');
        }
        
        // System health (simple heuristic)
        const health = this.data.enhancement_active && activeCount > 0 ? 100 : 0;
        this.updateElement('system-health', health + '%');
    }
    
    updateArchitecturalPlasticity() {
        const arch = this.data.architectural_plasticity || {};
        
        this.updateElement('arch-active-patterns', arch.active_patterns || 0);
        const effectiveness = arch.average_effectiveness;
        if (effectiveness !== undefined) {
            this.updateElement('arch-effectiveness', Math.round(effectiveness * 100) + '%');
        } else {
            this.updateElement('arch-effectiveness', 'N/A');
        }
        
        // Update suggestions (placeholder)
        const suggestionElement = document.getElementById('arch-suggestions');
        if (suggestionElement) {
            if (arch.active_patterns > 0) {
                suggestionElement.innerHTML = `
                    <div class="detail-item">
                        <span class="detail-label">Status:</span>
                        <span class="detail-value">Patterns Active</span>
                    </div>
                `;
            } else {
                suggestionElement.innerHTML = `
                    <div class="detail-item">
                        <span class="detail-label">Status:</span>
                        <span class="detail-value">Initializing</span>
                    </div>
                `;
            }
        }
    }
    
    updateGoalFormation() {
        const goals = this.data.goal_formation || {};
        
        this.updateElement('goal-active', goals.active_goals || 0);
        this.updateElement('goal-completed', goals.completed_goals || 0);
        
        // Update goal list
        const goalListElement = document.getElementById('goal-list');
        if (goalListElement) {
            const activeGoals = goals.active_goals || 0;
            if (activeGoals > 0) {
                goalListElement.innerHTML = `
                    <div class="detail-item">
                        <span class="detail-label">Current Focus:</span>
                        <span class="detail-value">Growth & Exploration</span>
                    </div>
                `;
            } else {
                goalListElement.innerHTML = `
                    <div class="detail-item">
                        <span class="detail-label">Status:</span>
                        <span class="detail-value">Awaiting Emergence</span>
                    </div>
                `;
            }
        }
    }
    
    updateRecursiveReflection() {
        const reflection = this.data.recursive_reflection || {};
        
        this.updateElement('reflection-depth', reflection.max_depth || 0);
        
        const quality = reflection.average_quality;
        if (quality !== undefined) {
            this.updateElement('reflection-quality', Math.round(quality * 100) + '%');
        } else {
            this.updateElement('reflection-quality', 'N/A');
        }
        
        // Update reflection traces
        const tracesElement = document.getElementById('reflection-traces');
        if (tracesElement) {
            tracesElement.innerHTML = `
                <div class="detail-item">
                    <span class="detail-label">Status:</span>
                    <span class="detail-value">Monitoring Reflections</span>
                </div>
            `;
        }
    }
    
    updateMetaLearning() {
        const meta = this.data.meta_learning || {};
        
        this.updateElement('meta-experiments', meta.total_experiments || 0);
        
        const effectiveness = meta.current_effectiveness;
        if (effectiveness !== undefined) {
            this.updateElement('meta-learning-rate', Math.round(effectiveness * 100) + '%');
        } else {
            this.updateElement('meta-learning-rate', 'N/A');
        }
        
        // Update optimizations
        const optimizationsElement = document.getElementById('meta-optimizations');
        if (optimizationsElement) {
            optimizationsElement.innerHTML = `
                <div class="detail-item">
                    <span class="detail-label">Status:</span>
                    <span class="detail-value">Optimizing Learning</span>
                </div>
            `;
        }
    }
    
    updateRecentActivity() {
        const activityElement = document.getElementById('recent-activity');
        if (!activityElement) return;

        const items = [];

        if (this.data.cycles_completed > 0) {
            items.push(`
                <div class="activity-item">
                    <div class="activity-icon">🔄</div>
                    <div class="activity-content">
                        <div class="activity-title">Autopoietic Cycle ${this.data.cycles_completed} Completed</div>
                        <div class="activity-time">${new Date().toLocaleTimeString()}</div>
                    </div>
                </div>
            `);
            items.push(`
                <div class="activity-item">
                    <div class="activity-icon">🧠</div>
                    <div class="activity-content">
                        <div class="activity-title">System Enhancement Active</div>
                        <div class="activity-time">Continuous</div>
                    </div>
                </div>
            `);
        }

        const signatures = window.telemetryManager?.data?.recent_state_signatures || [];
        signatures.slice(-3).reverse().forEach(sig => {
            items.push(`
                <div class="activity-item">
                    <div class="activity-icon">🧬</div>
                    <div class="activity-content">
                        <div class="activity-title">${this.formatSignatureTitle(sig)}</div>
                        <div class="activity-time">${this.formatSignatureTime(sig)}</div>
                    </div>
                </div>
            `);
        });

        if (items.length === 0) {
            items.push(`
                <div class="activity-item">
                    <div class="activity-icon">⏳</div>
                    <div class="activity-content">
                        <div class="activity-title">Awaiting First Interaction</div>
                        <div class="activity-time">System Ready</div>
                    </div>
                </div>
            `);
        }

        activityElement.innerHTML = items.join('');
    }

    formatSignatureTitle(sig = {}) {
        const phase = sig.phase || sig.origin || sig.source || 'cycle';
        const policy = sig.policy || sig.last_policy || '—';
        const band = sig.circadian_band || sig.band_label || sig.band || '—';
        const exhausted = sig.is_exhausted ?? sig.cognitive_exhausted;
        return `${phase} • ${policy} • ${band}${exhausted ? ' • exhausted' : ''}`;
    }

    formatSignatureTime(sig = {}) {
        const stampRaw = sig.timestamp || sig.at;
        if (!stampRaw) return 'state signature';
        const parsed = new Date(stampRaw);
        if (Number.isNaN(parsed.getTime())) return 'state signature';
        return parsed.toLocaleTimeString();
    }
    
    updateEnhancementStatus() {
        const statusBadge = document.getElementById('enhancement-status');
        const toggleBtn = document.getElementById('toggle-enhancement-btn');
        
        if (statusBadge && toggleBtn) {
            if (this.data && this.data.enhancement_active) {
                statusBadge.textContent = 'Enhancement Active';
                statusBadge.className = 'badge badge-success';
                toggleBtn.textContent = 'Disable Enhancement';
                toggleBtn.className = 'btn btn-warning';
            } else {
                statusBadge.textContent = 'Enhancement Inactive';
                statusBadge.className = 'badge badge-warning';
                toggleBtn.textContent = 'Enable Enhancement';
                toggleBtn.className = 'btn btn-primary';
            }
        }
    }
    
    async toggleEnhancement() {
        const toggleBtn = document.getElementById('toggle-enhancement-btn');
        
        try {
            toggleBtn.disabled = true;
            
            const isActive = this.data && this.data.enhancement_active;
            const endpoint = isActive ? '/autopoietic/disable' : '/autopoietic/enable';
            
            const response = await fetch(`${this.apiBase}${endpoint}`, {
                method: 'POST'
            });
            
            const result = await response.json();
            
            if (result.success) {
                // Refresh data to reflect the change
                await this.loadData();
            } else {
                console.error('Toggle failed:', result.error);
            }
            
        } catch (error) {
            console.error('Enhancement toggle error:', error);
        } finally {
            toggleBtn.disabled = false;
        }
    }
    
    updateElement(id, value) {
        const element = document.getElementById(id);
        if (element) {
            element.textContent = value;
        }
    }
    
    updateLastRefresh() {
        const element = document.getElementById('last-updated-autopoietic');
        if (element) {
            element.textContent = `Last updated: ${new Date().toLocaleTimeString()}`;
        }
    }
    
    updateConnectionStatus(connected, error = null) {
        const connEl = document.getElementById('sys-connection-status');
        if (!connEl) return;
        if (connected) {
            connEl.className = 'connection-status connected';
            connEl.innerHTML = '<span class="status-dot status-online"></span>Connected';
        } else {
            connEl.className = 'connection-status disconnected';
            connEl.innerHTML = '<span class="status-dot status-offline"></span>Disconnected';
            if (error) console.error('Connection error:', error);
        }
    }

    updateSidebarFromTelemetry(data) {
        if (!data) return;
        const set = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.textContent = val;
        };

        const auto = data.autopoieticStatus || {};
        set('sb-cycles',      auto.cycles_completed ?? '—');
        set('sb-goals',       auto.goal_formation?.active_goals ?? '—');
        set('sb-patterns',    auto.architectural_plasticity?.active_patterns ?? '—');
        set('sb-effectiveness',
            auto.meta_learning?.current_effectiveness != null
                ? Math.round(auto.meta_learning.current_effectiveness * 100) + '%'
                : '—');
        set('sb-auto-status', auto.enhancement_active ? 'Active' : 'Inactive');

        const llm = window.telemetryManager?.getLLMStats() || {};
        set('sb-llm-calls',   llm.total_requests ?? '—');
        set('sb-llm-success', llm.success_rate != null ? Math.round(llm.success_rate) + '%' : '—');
        set('sb-avg-ms',      llm.avg_response_time_ms != null ? Math.round(llm.avg_response_time_ms) + 'ms' : '—');
    }

    updatePerformanceTab() {
        if (!window.telemetryManager) return;
        this.updateRealTimePerformance();
        this.updateLLMPerformance();
        this.updateBufferPerformance();
        this.updateSystemInformation();
    }

    updateRealTimePerformance() {
        const llm = window.telemetryManager.getLLMStats();
        const buf = window.telemetryManager.getBufferStats();
        const perf = window.telemetryManager.data?.perfStats || {};

        this.updateScalar('total-requests',   llm.total_requests || 0);
        const sr = llm.success_rate_percent ?? llm.success_rate ?? 100;
        this.updateScalar('success-rate',     `${Math.round(sr)}%`);
        this.updateScalar('avg-response-time',`${Math.round(llm.avg_response_time_ms || 0)}ms`);
        this.updateScalar('buffer-writes',    buf.total_writes || 0);
        this.updateScalar('batch-efficiency', `${Math.round(buf.batch_efficiency_percent || buf.batch_efficiency || 0)}%`);
        const overall = perf.overall_performance_score || ((sr + (buf.batch_efficiency || 0)) / 2);
        this.updateScalar('performance-score',`${Math.round(overall)}%`);
    }

    updateLLMPerformance() {
        const llm = window.telemetryManager.getLLMStats();
        const total  = llm.total_requests || 0;
        const failed = llm.failed_requests || 0;
        const successRate = total > 0 ? ((total - failed) / total * 100) : 100;

        this.updateElement('llm-total',          total);
        this.updateElement('llm-failed',         failed);
        this.updateElement('llm-success-rate',   `${Math.round(successRate)}%`);
        this.updateElement('llm-batched',        llm.batched_requests || 0);
        this.updateElement('concurrent-limit',   llm.concurrent_limit || 4);
        this.updateElement('llm-batch-efficiency',`${Math.round(llm.batch_efficiency || 0)}%`);
    }

    updateBufferPerformance() {
        const buf = window.telemetryManager.getBufferStats();

        this.updateElement('buffer-total-writes',    buf.total_writes || 0);
        this.updateElement('buffer-batched-writes',  buf.batched_writes || 0);
        this.updateElement('buffer-immediate-writes',buf.immediate_writes || 0);
        this.updateElement('buffer-pending',         buf.pending_count || 0);
        this.updateElement('buffer-efficiency',      `${Math.round(buf.batch_efficiency || 0)}%`);
        this.updateElement('buffer-status',          buf.running ? 'Running' : 'Stopped');
    }

    updateSystemInformation() {
        const d = window.telemetryManager.data || {};
        this.updateElement('backend-type',    d.memory_stats?.backend_type || 'Unknown');
        this.updateElement('session-reset',   String(d.session_reset ?? false));
        this.updateElement('buffer-running',  String(d.buffer_stats?.running ?? true));

        const session = d.session_state || {};
        const sid = session.session_id || 'unknown';
        this.updateElement('session-id',       sid.length > 8 ? sid.substring(0, 8) + '…' : sid);
        this.updateElement('session-created',  this.formatDate(session.created_at));
        this.updateElement('session-exchanges',session.total_exchanges || 0);

        // Status badge
        const badge = document.getElementById('status-badge');
        if (badge) {
            badge.className = 'badge badge-success';
            badge.textContent = 'System Online';
        }
    }

    async flushBuffer() {
        const flushBtn = document.getElementById('flush-buffer-btn');
        if (!flushBtn) return;
        try {
            flushBtn.disabled = true;
            flushBtn.textContent = 'Flushing…';
            const response = await fetch(`${this.apiBase}/performance/flush_buffer`, { method: 'POST' });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            flushBtn.textContent = 'Flushed!';
            setTimeout(() => {
                this.loadData();
                flushBtn.textContent = 'Flush Buffer';
                flushBtn.disabled = false;
            }, 1500);
        } catch (err) {
            console.error('Flush error:', err);
            flushBtn.textContent = 'Error';
            setTimeout(() => { flushBtn.textContent = 'Flush Buffer'; flushBtn.disabled = false; }, 2000);
        }
    }

    formatDate(dateStr) {
        if (!dateStr) return 'Unknown';
        try { return new Date(dateStr).toLocaleTimeString(); }
        catch { return 'Invalid'; }
    }

    // updateScalar: updates .stat-value child or falls back to element text
    updateScalar(id, value) {
        const el = document.getElementById(id);
        if (!el) return;
        const child = el.querySelector('.stat-value');
        if (child) child.textContent = value;
        else el.textContent = value;
    }
    
    startAutoRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
        }
        
        if (this.autoRefresh) {
            this.refreshInterval = setInterval(() => {
                this.loadData();
            }, 5000); // Aligned with telemetry manager refresh (5 seconds)
        }
    }
    
    stopAutoRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
            this.refreshInterval = null;
        }
    }
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', () => {
    window.autopoieticDashboard = new AutopoieticDashboard();
});