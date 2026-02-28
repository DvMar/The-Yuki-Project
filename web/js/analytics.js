// Analytics Manager
class Analytics {
    constructor() {
        this.apiBase = 'http://localhost:8000';
        this.performanceData = null;
        this.systemData = null;
        this.refreshInterval = null;
        
        this.initialize();
    }
    
    initialize() {
        this.setupEventListeners();
        this.loadAnalytics();
        this.startAutoRefresh();
    }
    
    setupEventListeners() {
        // Refresh analytics button
        const refreshBtn = document.getElementById('refresh-analytics-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.loadAnalytics(true));
        }
        
        // Flush buffer button
        const flushBtn = document.getElementById('flush-buffer-btn');
        if (flushBtn) {
            flushBtn.addEventListener('click', () => this.flushBuffer());
        }
    }
    
    async loadAnalytics(manual = false) {
        const refreshBtn = document.getElementById('refresh-analytics-btn');
        
        try {
            if (manual && refreshBtn) {
                refreshBtn.classList.add('loading');
                refreshBtn.disabled = true;
            }
            
            // Use telemetry manager to fetch all data
            await window.telemetryManager.fetchAllData();
            this.performanceData = window.telemetryManager.data?.perfStats || {};
            this.systemData = window.telemetryManager.data || {};
            
            this.updateAnalyticsUI();
            this.updateLastRefresh();
            this.updateConnectionStatus(true);
            
        } catch (error) {
            console.error('Analytics load error:', error);
            this.updateConnectionStatus(false, error.message);
        } finally {
            if (refreshBtn) {
                refreshBtn.classList.remove('loading');
                refreshBtn.disabled = false;
            }
        }
    }
    
    async flushBuffer() {
        const flushBtn = document.getElementById('flush-buffer-btn');
        
        try {
            flushBtn.disabled = true;
            flushBtn.textContent = '🔄 Flushing...';
            
            const response = await fetch(`${this.apiBase}/performance/flush_buffer`, {
                method: 'POST'
            });
            
            if (!response.ok) {
                throw new Error(`Flush failed: ${response.status}`);
            }
            
            const result = await response.json();
            
            // Show success feedback
            flushBtn.textContent = '✓ Flushed';
            flushBtn.classList.add('btn-success');
            
            // Refresh analytics after flush
            setTimeout(() => {
                this.loadAnalytics();
                flushBtn.textContent = '🔄 Flush Buffer';
                flushBtn.classList.remove('btn-success');
                flushBtn.disabled = false;
            }, 1500);
            
        } catch (error) {
            console.error('Buffer flush error:', error);
            flushBtn.textContent = '❌ Error';
            setTimeout(() => {
                flushBtn.textContent = '🔄 Flush Buffer';
                flushBtn.disabled = false;
            }, 2000);
        }
    }
    
    updateAnalyticsUI() {
        if (!this.performanceData || !this.systemData) return;
        
        this.updateRealTimePerformance();
        this.updateLLMPerformance();
        this.updateBufferPerformance();
        this.updateSystemInformation();
    }
    
    updateRealTimePerformance() {
        const llmStats = window.telemetryManager.getLLMStats();
        const bufferStats = window.telemetryManager.getBufferStats();
        
        // Real-time stats
        this.updateElement('total-requests', llmStats.total_requests || 0);
        this.updateElement('success-rate', `${llmStats.success_rate_percent || llmStats.success_rate || 100}%`);
        this.updateElement('avg-response-time', `${Math.round(llmStats.avg_response_time_ms || 0)}ms`);
        this.updateElement('buffer-writes', bufferStats.total_writes || 0);
        this.updateElement('batch-efficiency', `${bufferStats.batch_efficiency_percent || bufferStats.batch_efficiency || 0}%`);
        
        const overall = this.performanceData.overall_performance_score || 
            (llmStats.success_rate || 100) * 0.5 + (bufferStats.batch_efficiency || 0) * 0.5;
        this.updateElement('performance-score', `${Math.round(overall)}%`);
    }
    
    updateLLMPerformance() {
        const llmStats = window.telemetryManager.getLLMStats();
        
        const total = llmStats.total_requests || 0;
        const failed = llmStats.failed_requests || 0;
        const successRate = total > 0 ? ((total - failed) / total * 100) : 100;
        
        this.updateElement('llm-total', total);
        this.updateElement('llm-failed', failed);
        this.updateElement('llm-success-rate', `${Math.round(successRate)}%`);
        this.updateElement('llm-batched', llmStats.batched_requests || 0);
        this.updateElement('concurrent-limit', llmStats.concurrent_limit || 4);
        this.updateElement('llm-batch-efficiency', `${Math.round(llmStats.batch_efficiency || 0)}%`);
    }
    
    updateBufferPerformance() {
        const bufferStats = window.telemetryManager.getBufferStats();
        
        this.updateElement('buffer-total-writes', bufferStats.total_writes || 0);
        this.updateElement('buffer-batched-writes', bufferStats.batched_writes || 0);
        this.updateElement('buffer-immediate-writes', bufferStats.immediate_writes || 0);
        this.updateElement('buffer-pending', bufferStats.pending_count || 0);
        this.updateElement('buffer-efficiency', `${Math.round(bufferStats.batch_efficiency || 0)}%`);
        this.updateElement('buffer-status', bufferStats.running ? 'Running' : 'Stopped');
        
        // Update buffer status color
        const statusEl = document.getElementById('buffer-status');
        if (statusEl) {
            statusEl.className = bufferStats.running ? 'stat-value text-success' : 'stat-value text-warning';
        }
    }
    
    updateSystemInformation() {
        const system = this.systemData;
        
        // Backend info
        this.updateElement('backend-type', system.memory_stats?.backend_type || 'Unknown');
        this.updateElement('buffer-running', system.buffer_stats?.running ? 'true' : 'false');
        
        // Session info
        const session = system.session_state || {};
        this.updateElement('session-id', this.truncateId(session.session_id || 'unknown'));
        this.updateElement('session-created', this.formatDate(session.created_at));
        this.updateElement('session-exchanges', session.total_exchanges || 0);
    }
    
    updateConnectionStatus(connected, errorMsg = null) {
        const statusBadge = document.getElementById('status-badge');
        if (!statusBadge) return;
        
        if (connected) {
            statusBadge.className = 'badge badge-success';
            statusBadge.textContent = 'System Online';
        } else {
            statusBadge.className = 'badge badge-warning';
            statusBadge.textContent = errorMsg ? `Error: ${errorMsg.substring(0, 20)}...` : 'Connection Lost';
        }
    }
    
    updateElement(id, value) {
        const element = document.getElementById(id);
        if (element) {
            // Look for stat-value child element first
            const valueElement = element.querySelector('.stat-value');
            if (valueElement) {
                valueElement.textContent = value;
            } else {
                // Fallback to updating the element itself
                element.textContent = value;
            }
        }
    }
    
    updateLastRefresh() {
        const element = document.getElementById('last-analytics-update');
        if (element) {
            const now = new Date();
            element.textContent = `Last updated: ${now.toLocaleTimeString()}`;
        }
    }
    
    truncateId(id) {
        return id.length > 8 ? `${id.substring(0, 8)}...` : id;
    }
    
    formatDate(dateStr) {
        if (!dateStr) return 'Unknown';
        
        try {
            const date = new Date(dateStr);
            return date.toLocaleTimeString();
        } catch (error) {
            return 'Invalid';
        }
    }
    
    startAutoRefresh() {
        if (this.refreshInterval) return;
        
        this.refreshInterval = setInterval(() => {
            this.loadAnalytics();
        }, 10000); // Refresh every 10 seconds for analytics
    }
    
    stopAutoRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
            this.refreshInterval = null;
        }
    }
}

// Initialize analytics when page loads
document.addEventListener('DOMContentLoaded', () => {
    window.analytics = new Analytics();
    
    // Cleanup on page unload
    window.addEventListener('beforeunload', () => {
        if (window.analytics) {
            window.analytics.stopAutoRefresh();
        }
    });
});