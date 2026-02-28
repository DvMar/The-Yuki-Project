// Chat Interface Manager
class ChatInterface {
    constructor() {
        this.apiBase = 'http://localhost:8000';
        this.chatWindow = document.getElementById('chat-messages');
        this.chatInput = document.getElementById('chat-input');
        this.sendButton = document.getElementById('send-button');
        this.connectionStatus = document.getElementById('connection-status');
        
        this.conversationHistory = [];
        this.isConnected = false;
        this.isTyping = false;
        
        this.initialize();
        this.loadConversationHistory();
    }
    
    initialize() {
        this.setupEventListeners();
        this.checkConnection();
        this.startHeartbeat();
    }
    
    loadConversationHistory() {
        try {
            const saved = localStorage.getItem('yuki-conversation-history');
            if (saved) {
                this.conversationHistory = JSON.parse(saved);
                this.restoreMessages();
            }
        } catch (error) {
            console.warn('Failed to load conversation history:', error);
        }
    }
    
    saveConversationHistory() {
        try {
            localStorage.setItem('yuki-conversation-history', JSON.stringify(this.conversationHistory));
        } catch (error) {
            console.warn('Failed to save conversation history:', error);
        }
    }
    
    restoreMessages() {
        // Clear welcome message
        this.chatWindow.innerHTML = '';
        
        // Restore all messages
        this.conversationHistory.forEach(msg => {
            if (msg.role === 'user') {
                this.addMessage(msg.content, 'user', false, false);
            } else if (msg.role === 'assistant') {
                this.addMessage(msg.content, 'ai', false, false);
            } else if (msg.role === 'system') {
                this.addMessage(msg.content, 'system', false, false);
            }
        });
        
        // If no messages, show welcome
        if (this.conversationHistory.length === 0) {
            this.showWelcomeMessage();
        }
    }
    
    showWelcomeMessage() {
        this.chatWindow.innerHTML = `
            <div class="welcome-block">
                <p class="welcome-text">Hello. I'm Yuki — start the conversation below.</p>
            </div>
        `;
    }
    
    setupEventListeners() {
        // Send message on button click
        this.sendButton.addEventListener('click', () => this.sendMessage());
        
        // Send message on Enter (but not Shift+Enter)
        this.chatInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });
        
        // Auto-resize textarea
        this.chatInput.addEventListener('input', () => this.autoResizeInput());
        
        // Focus input on page load
        this.chatInput.focus();
    }
    
    autoResizeInput() {
        this.chatInput.style.height = 'auto';
        this.chatInput.style.height = Math.min(this.chatInput.scrollHeight, 128) + 'px';
    }
    
    async checkConnection() {
        try {
            const response = await fetch(`${this.apiBase}/performance/stats`);
            if (response.ok) {
                this.updateConnectionStatus(true);
            } else {
                this.updateConnectionStatus(false);
            }
        } catch (error) {
            this.updateConnectionStatus(false);
        }
    }
    
    startHeartbeat() {
        setInterval(() => this.checkConnection(), 5000); // Check every 5 seconds to quickly detect disconnection
    }
    
    updateConnectionStatus(connected) {
        this.isConnected = connected;
        const status = this.connectionStatus;
        if (!status) return;
        if (connected) {
            status.className = 'connection-status connected';
            status.innerHTML = '<span class="status-dot status-online"></span>Online';
        } else {
            status.className = 'connection-status disconnected';
            status.innerHTML = '<span class="status-dot status-offline"></span>Offline';
        }
    }
    
    async sendMessage() {
        const text = this.chatInput.value.trim();
        if (!text || this.isTyping) return;
        
        // Add user message to chat
        this.addMessage(text, 'user');
        this.conversationHistory.push({
            role: 'user',
            content: text,
            timestamp: new Date().toISOString()
        });
        
        // Save to localStorage
        this.saveConversationHistory();
        
        // Clear input and disable send button
        this.chatInput.value = '';
        this.autoResizeInput();
        this.setTypingState(true);
        
        try {
            const response = await fetch(`${this.apiBase}/chat`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ message: text, stream_raw: false, stream_strategy: 'token' })
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            // Handle streaming response
            await this.handleStreamingResponse(response);
            
        } catch (error) {
            console.error('Chat error:', error);
            this.addMessage(`Error: ${error.message}`, 'system');
            this.updateConnectionStatus(false);
        } finally {
            this.setTypingState(false);
        }
    }
    
    async handleStreamingResponse(response) {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        
        // Create AI message element
        const messageId = this.addMessage('', 'ai', true);
        const messageElement = document.getElementById(messageId);
        const contentElement = messageElement.querySelector('.message-text');
        
        let fullResponse = '';
        
        try {
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                
                const chunk = decoder.decode(value, { stream: true });
                fullResponse += chunk;
                
                // Update message content in real-time (plain text during streaming)
                contentElement.textContent = fullResponse;
                this.scrollToBottom();
            }
            
            // Render markdown once streaming is complete
            if (typeof marked !== 'undefined') {
                contentElement.innerHTML = marked.parse(fullResponse);
            } else {
                contentElement.textContent = fullResponse;
            }
            this.scrollToBottom();
            
            // Store complete response
            this.conversationHistory.push({
                role: 'assistant',
                content: fullResponse,
                timestamp: new Date().toISOString()
            });
        
            // Save to localStorage
            this.saveConversationHistory();
        } catch (error) {
            console.error('Error in streaming response:', error);
            // Handle error appropriately
            const errorMessage = 'Sorry, there was an error processing the response.';
            contentElement.textContent = errorMessage;
        }
    }
    
    addMessage(content, sender, isStreaming = false, shouldSave = true) {
        const messageId = `msg-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
        const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

        // Remove welcome block on first real message
        const welcome = this.chatWindow.querySelector('.welcome-block');
        if (welcome) welcome.remove();

        const messageDiv = document.createElement('div');
        messageDiv.id = messageId;

        if (sender === 'system') {
            // Dream / spontaneous thought
            messageDiv.className = 'message dream';
            messageDiv.innerHTML = `
                <div class="message-label">Yuki &middot; thought &middot; ${timestamp}</div>
                <div class="message-text">${this.escapeHtml(content)}</div>
            `;
        } else if (sender === 'user') {
            messageDiv.className = 'message user';
            messageDiv.innerHTML = `
                <div class="message-label">You &middot; ${timestamp}</div>
                <div class="message-text">${this.escapeHtml(content)}</div>
            `;
        } else {
            // AI
            messageDiv.className = 'message ai';
            const textContent = isStreaming
                ? '<div class="typing-indicator"><span></span><span></span><span></span></div>'
                : this.escapeHtml(content);
            messageDiv.innerHTML = `
                <div class="message-label">Yuki &middot; ${timestamp}</div>
                <div class="message-text">${textContent}</div>
            `;
        }

        this.chatWindow.appendChild(messageDiv);
        this.scrollToBottom();
        return messageId;
    }
    
    setTypingState(typing) {
        this.isTyping = typing;
        this.sendButton.disabled = typing;
        this.chatInput.disabled = typing;
        this.sendButton.textContent = typing ? '...' : 'Send';
    }
    
    scrollToBottom() {
        this.chatWindow.scrollTop = this.chatWindow.scrollHeight;
    }
    
    clearChat() {
        if (confirm('Clear all messages?')) {
            this.showWelcomeMessage();
            this.conversationHistory = [];

            // Clear localStorage — conversation history and any cached dreams
            localStorage.removeItem('yuki-conversation-history');
            if (window.telemetryManager) window.telemetryManager.clearDreams();
        }
    }
    
    exportChat() {
        if (this.conversationHistory.length === 0) {
            alert('No conversation to export.');
            return;
        }
        
        const data = {
            exported_at: new Date().toISOString(),
            message_count: this.conversationHistory.length,
            conversation: this.conversationHistory
        };
        
        const blob = new Blob([JSON.stringify(data, null, 2)], {
            type: 'application/json'
        });
        
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `yuki-conversation-${new Date().toISOString().split('T')[0]}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Auto-polling for system messages
class SystemMessagePoller {
    constructor(chatInterface) {
        this.chatInterface = chatInterface;
        this.pollInterval = null;
        this.isPolling = false;
        this.lastDisplayedDreamId = null; // Track which dreams have been displayed
    }
    
    start() {
        if (this.isPolling) return;
        
        this.isPolling = true;
        this.pollInterval = setInterval(() => this.poll(), 10000); // Poll every 10 seconds
    }
    
    stop() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
        this.isPolling = false;
    }
    
    async poll() {
        try {
            // Check if server is connected first
            if (!this.chatInterface.isConnected) {
                return;
            }
            
            const dreams = window.telemetryManager.getDreams();
            if (!dreams || dreams.length === 0) return;
            
            // Build set of dream IDs already in conversation history (survives page refresh)
            const shownIds = new Set(
                this.chatInterface.conversationHistory
                    .filter(m => m.dreamId)
                    .map(m => m.dreamId)
            );
            
            // New dreams = not in history AND not the last one we showed this session
            const newDreams = dreams.filter(
                d => d.id && !shownIds.has(d.id) && d.id !== this.lastDisplayedDreamId
            );
            
            if (newDreams.length > 0) {
                for (const dream of newDreams) {
                    this.chatInterface.addMessage(dream.text, 'system');
                    this.chatInterface.conversationHistory.push({
                        role: 'system',
                        content: dream.text,
                        timestamp: dream.timestamp || new Date().toISOString(),
                        dreamId: dream.id
                    });
                    this.lastDisplayedDreamId = dream.id;
                    console.log('[DREAM] System message received:', dream.text);
                }
                this.chatInterface.saveConversationHistory();
            }
        } catch (error) {
            // Silently fail - don't spam console with polling errors
        }
    }
}

// ============================================================
// Sidebar data binding
// ============================================================
function updateSidebar(data) {
    if (!data) return;

    function set(id, val) {
        const el = document.getElementById(id);
        if (el) el.textContent = (val !== undefined && val !== null && val !== '') ? String(val) : '—';
    }

    // Session
    set('sb-interactions', data.interaction_count ?? '—');
    if (data.timestamp) {
        const d = new Date(data.timestamp);
        set('sb-updated', d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
    }

    // Affective state — dynamic rows (keys: stability, engagement, intellectual_energy, warmth)
    const affect = data.emotional_state || {};
    const affectContainer = document.getElementById('sb-affect-container');
    if (affectContainer && Object.keys(affect).length > 0) {
        affectContainer.innerHTML = Object.entries(affect).map(([k, v]) =>
            `<div class="sb-row"><span class="sb-key">${k.replace(/_/g, ' ')}</span><span class="sb-val">${Number(v).toFixed(2)}</span></div>`
        ).join('');
    }

    // Memory — keys from get_memory_stats()
    const ms = data.memory_stats || {};
    set('sb-facts',    ms.user_facts         ?? '—');
    set('sb-episodic', ms.episodic_memories  ?? '—');
    set('sb-entities',
        data.knowledge_graph_stats?.total_nodes ??
        data.knowledge_graph_stats?.nodes ??
        ms.knowledge_graph_nodes ??
        '—');

    // Dream cycle
    const dc = data.dreamcycle_status || (data.latestLog || {}).dreamcycle_status || {};
    set('sb-dream-mode', dc.last_dream_mode || '—');
    set('sb-idle',       dc.idle_seconds !== undefined ? `${dc.idle_seconds}s` : '—');
    set('sb-desire',     dc.desire_to_connect !== undefined ? Number(dc.desire_to_connect).toFixed(2) : '—');
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', () => {
    window.chatInterface = new ChatInterface();
    window.systemPoller = new SystemMessagePoller(window.chatInterface);
    
    // Start system message polling
    window.systemPoller.start();
    
    // Expose functions for buttons
    window.clearChat = () => window.chatInterface.clearChat();
    window.exportChat = () => window.chatInterface.exportChat();

    // Subscribe sidebar to live telemetry updates
    if (window.telemetryManager) {
        window.telemetryManager.subscribe(updateSidebar);
        // Populate immediately from any cached data
        updateSidebar(window.telemetryManager.data);
    }
});