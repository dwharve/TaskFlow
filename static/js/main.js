// Initialize all components
document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function(tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Initialize popovers
    var popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    popoverTriggerList.map(function(popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });

    // Set up plugin parameter handlers
    setupPluginParameters();

    // Create toast container
    if (!document.getElementById('toast-container')) {
        const container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'position-fixed bottom-0 end-0 p-3';
        document.body.appendChild(container);
    }

    // Auto-hide alerts after 5 seconds
    setTimeout(function() {
        var alerts = document.querySelectorAll('.alert:not(.alert-permanent)');
        alerts.forEach(function(alert) {
            var bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        });
    }, 5000);

    // Initialize polling for running tasks when page loads
    document.querySelectorAll('[data-task-id]').forEach(element => {
        const taskId = element.dataset.taskId;
        const statusBadge = element.querySelector('.badge');
        if (statusBadge && statusBadge.textContent.trim() === 'running' && taskId) {
            startPollingTask(taskId);
        }
    });
});

// Secure API Client
const api = {
    // Rate limiting configuration
    rateLimit: {
        maxRequests: 50,
        timeWindow: 60000, // 1 minute
        requests: new Map(),
    },

    // Request timeout in milliseconds
    timeout: 30000,

    // Headers setup
    get headers() {
        return {
            'Content-Type': 'application/json',
            'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content,
            // Add a request ID for tracking
            'X-Request-ID': this.generateRequestId()
        };
    },

    // Generate unique request ID
    generateRequestId() {
        return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    },

    // Check rate limit
    checkRateLimit() {
        const now = Date.now();
        const windowStart = now - this.rateLimit.timeWindow;
        
        // Clean up old requests
        for (const [timestamp] of this.rateLimit.requests) {
            if (timestamp < windowStart) {
                this.rateLimit.requests.delete(timestamp);
            }
        }
        
        // Check if we're over the limit
        if (this.rateLimit.requests.size >= this.rateLimit.maxRequests) {
            throw new Error('Rate limit exceeded. Please try again later.');
        }
        
        // Add current request
        this.rateLimit.requests.set(now, true);
    },

    // Sanitize input
    sanitizeInput(data) {
        if (typeof data === 'string') {
            return this.escapeHtml(data);
        } else if (Array.isArray(data)) {
            return data.map(item => this.sanitizeInput(item));
        } else if (typeof data === 'object' && data !== null) {
            const sanitized = {};
            for (const [key, value] of Object.entries(data)) {
                sanitized[this.escapeHtml(key)] = this.sanitizeInput(value);
            }
            return sanitized;
        }
        return data;
    },

    // Escape HTML special characters
    escapeHtml(str) {
        if (typeof str !== 'string') return str;
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    },

    // Main API call method
    async call(endpoint, options = {}) {
        try {
            // Check rate limit
            this.checkRateLimit();

            // Sanitize request data
            if (options.body) {
                options.body = JSON.stringify(this.sanitizeInput(JSON.parse(options.body)));
            }

            // Setup request with timeout
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), this.timeout);

            const response = await fetch(endpoint, {
                ...options,
                headers: { ...this.headers, ...options.headers },
                signal: controller.signal
            });

            clearTimeout(timeoutId);

            // Handle response
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.message || 'API call failed');
            }

            const data = await response.json();
            return this.sanitizeInput(data);
        } catch (error) {
            if (error.name === 'AbortError') {
                throw new Error('Request timed out');
            }
            throw error;
        }
    }
};

// Session management
const session = {
    // Check if session is valid
    async checkSession() {
        try {
            await api.call('/api/auth/check');
            return true;
        } catch (error) {
            if (error.message === 'Session expired') {
                this.handleExpiredSession();
            }
            return false;
        }
    },

    // Handle expired session
    handleExpiredSession() {
        showToast('Your session has expired. Please log in again.', 'warning');
        setTimeout(() => {
            window.location.href = '/login?redirect=' + encodeURIComponent(window.location.pathname);
        }, 2000);
    }
};

// Task status badge colors
function getStatusBadgeClass(status) {
    switch (status.toLowerCase()) {
        case 'pending':
            return 'badge-pending';
        case 'running':
            return 'badge-running';
        case 'completed':
            return 'badge-completed';
        case 'failed':
            return 'badge-failed';
        default:
            return 'badge-secondary';
    }
}

// Format dates
function formatDate(dateString) {
    if (!dateString) return '';
    const date = new Date(dateString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
}

// Copy to clipboard
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(function() {
        showToast('Copied to clipboard!');
    }).catch(function(err) {
        console.error('Failed to copy text: ', err);
    });
}

// Show toast notification
function showToast(message, type = 'success') {
    const toastContainer = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast align-items-center text-white bg-${type}`;
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'assertive');
    toast.setAttribute('aria-atomic', 'true');
    
    toast.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">
                ${message}
            </div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
        </div>
    `;
    
    toastContainer.appendChild(toast);
    const bsToast = new bootstrap.Toast(toast);
    bsToast.show();
    
    toast.addEventListener('hidden.bs.toast', function() {
        toast.remove();
    });
}

// Confirm action
function confirmAction(message, callback) {
    if (confirm(message)) {
        callback();
    }
}

// Form validation with security
function validateForm(form, options = {}) {
    const defaults = {
        showToast: true,
        scrollToError: true,
        sanitizeInputs: true
    };
    const settings = { ...defaults, ...options };
    
    if (settings.sanitizeInputs) {
        // Sanitize all input values
        form.querySelectorAll('input, textarea, select').forEach(input => {
            if (input.type !== 'password') {
                input.value = api.sanitizeInput(input.value);
            }
        });
    }

    if (!form.checkValidity()) {
        event.preventDefault();
        event.stopPropagation();
        
        if (settings.showToast) {
            showToast('Please check the form for errors', 'warning');
        }
        
        if (settings.scrollToError) {
            const firstError = form.querySelector(':invalid');
            if (firstError) {
                firstError.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        }
    }
    form.classList.add('was-validated');
    return form.checkValidity();
}

// Dynamic form fields
function addFormField(containerId, template) {
    const container = document.getElementById(containerId);
    const index = container.children.length;
    const newField = template.replace(/\{index\}/g, index);
    container.insertAdjacentHTML('beforeend', newField);
}

function removeFormField(element) {
    element.closest('.form-field').remove();
}

// Task polling system
let pollingTasks = new Set();
let pollInterval;

async function pollTaskStatus(taskId) {
    try {
        const response = await fetch(`/api/tasks/${taskId}/status`);
        if (!response.ok) throw new Error('Failed to fetch task status');
        
        const data = await response.json();
        
        // Update task status in all relevant places
        updateTaskStatus(taskId, data);
        
        // Stop polling if task is completed or failed
        if (!['pending', 'running'].includes(data.status)) {
            stopPollingTask(taskId);
        }
    } catch (error) {
        console.error('Error polling task status:', error);
        stopPollingTask(taskId);
    }
}

async function pollTaskStatuses() {
    const taskIds = Array.from(pollingTasks);
    if (taskIds.length === 0) {
        stopPolling();
        return;
    }

    try {
        const response = await fetch(`/api/tasks/status?ids=${taskIds.join(',')}`);
        if (!response.ok) throw new Error('Failed to fetch task statuses');
        
        const data = await response.json();
        
        // Update each task's status
        for (const [taskId, taskData] of Object.entries(data)) {
            updateTaskStatus(taskId, taskData);
            
            // Stop polling this task if it's completed or failed
            if (!['pending', 'running'].includes(taskData.status)) {
                pollingTasks.delete(parseInt(taskId));
            }
        }

        // Stop polling if no tasks remain
        if (pollingTasks.size === 0) {
            stopPolling();
        }
    } catch (error) {
        console.error('Error polling task statuses:', error);
    }
}

function updateTaskStatus(taskId, data) {
    // Find all elements that need updating for this task
    const elements = document.querySelectorAll(`[data-task-id="${taskId}"]`);
    
    elements.forEach(element => {
        // Update status badge
        const statusBadge = element.querySelector('.badge');
        if (statusBadge) {
            statusBadge.className = `badge ${data.status_class}`;
            statusBadge.textContent = data.status;
        }
        
        // Update last run time if provided
        if (data.last_run) {
            const lastRunElement = element.querySelector('[data-last-run]');
            if (lastRunElement) {
                lastRunElement.textContent = data.last_run;
            }
        }
        
        // Update block data if available (for task view page)
        if (data.block_data && element.classList.contains('task-details')) {
            updateBlockData(data.block_data);
        }
    });
}

function updateBlockData(blockData) {
    // Update input data
    updateTabContent('input-data', blockData.input);
    
    // Update processing data
    if (blockData.processing) {
        Object.entries(blockData.processing).forEach(([blockName, blockData]) => {
            updateTabContent(`processing-${blockName}`, blockData);
        });
    }
    
    // Update action data
    if (blockData.action) {
        Object.entries(blockData.action).forEach(([blockName, blockData]) => {
            updateTabContent('action-data', blockData);
        });
    }
}

function updateTabContent(tabId, data) {
    const tabPane = document.getElementById(tabId);
    if (!tabPane) return;
    
    if (data && (Array.isArray(data) ? data.length > 0 : Object.keys(data).length > 0)) {
        tabPane.innerHTML = `<pre class="data-preview">${JSON.stringify(data, null, 2)}</pre>`;
    } else {
        tabPane.innerHTML = `
            <div class="info-message">
                <i class="fas fa-info-circle me-2"></i>No data available yet.
            </div>`;
    }
}

function startPollingTask(taskId) {
    pollingTasks.add(taskId);
    
    // Add loading indicator to status badge
    const elements = document.querySelectorAll(`[data-task-id="${taskId}"]`);
    elements.forEach(element => {
        const statusBadge = element.querySelector('.badge');
        if (statusBadge) {
            const currentText = statusBadge.textContent.trim();
            statusBadge.innerHTML = `<i class="fas fa-spinner fa-spin me-1"></i>${currentText}`;
        }
    });
    
    // Start polling if not already started
    if (!pollInterval) {
        pollTaskStatuses(); // Initial poll
        pollInterval = setInterval(pollTaskStatuses, 2000);
    }
}

function stopPollingTask(taskId) {
    pollingTasks.delete(taskId);
    if (pollingTasks.size === 0) {
        stopPolling();
    }
}

function stopPolling() {
    if (pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
    }
    pollingTasks.clear();
}

// Stop polling when leaving the page
window.addEventListener('beforeunload', stopPolling);

// Plugin parameter handling with security
function setupPluginParameters() {
    const scrapingSelect = document.getElementById('scraping_plugin');
    const processingSelect = document.getElementById('processing_plugin');
    const targetUrlInput = document.getElementById('target_url');

    function handlePluginChange(select, parametersContainerId, paramPrefix) {
        if (!select) return;
        
        select.addEventListener('change', function() {
            // Validate and sanitize selection
            const selectedOption = this.options[this.selectedIndex];
            if (!selectedOption || !selectedOption.value) return;

            // Update plugin description
            const description = api.sanitizeInput(selectedOption?.dataset.description || '');
            const descriptionElement = this.parentElement.querySelector('.plugin-description');
            if (descriptionElement) {
                descriptionElement.textContent = description;
            }

            // Handle target URL if this is the scraping plugin
            if (select === scrapingSelect) {
                const targetUrl = api.sanitizeInput(selectedOption?.dataset.targetUrl || '');
                if (targetUrl) {
                    targetUrlInput.value = targetUrl;
                    targetUrlInput.readOnly = true;
                    targetUrlInput.classList.add('bg-light');
                } else {
                    targetUrlInput.readOnly = false;
                    targetUrlInput.classList.remove('bg-light');
                    if (!targetUrlInput.value) {
                        targetUrlInput.value = '';
                    }
                }
            }

            try {
                // Safely parse and validate parameters
                const parameters = selectedOption?.dataset.parameters ? 
                    JSON.parse(api.sanitizeInput(selectedOption.dataset.parameters)) : {};
                
                if (typeof parameters !== 'object') {
                    throw new Error('Invalid parameters format');
                }

                generatePluginParameters(parametersContainerId, parameters, paramPrefix);
            } catch (error) {
                console.error('Error parsing plugin parameters:', error);
                showToast('Error loading plugin parameters', 'danger');
            }
        });

        // Initialize with current selection if any
        if (select.value) {
            select.dispatchEvent(new Event('change'));
        }
    }

    handlePluginChange(scrapingSelect, 'scraping_parameters', 'scraping_param_');
    handlePluginChange(processingSelect, 'processing_parameters', 'processing_param_');
}

function generatePluginParameters(containerId, parameters, prefix) {
    const container = document.getElementById(containerId);
    if (!container) return;

    // Store current values before clearing
    const currentValues = {};
    Object.entries(parameters).forEach(([key, _]) => {
        const input = document.getElementById(prefix + key);
        if (input) {
            currentValues[key] = api.sanitizeInput(input.value);
        }
    });

    // Clear existing parameters
    container.innerHTML = '';

    // Generate form fields for each parameter
    Object.entries(parameters).forEach(([key, config]) => {
        try {
            // Validate parameter configuration
            if (!key || typeof config !== 'object') {
                throw new Error('Invalid parameter configuration');
            }

            // Skip fields that depend on unselected values
            if (config.depends_on) {
                const dependentField = document.getElementById(prefix + config.depends_on.field);
                if (!dependentField || dependentField.value !== config.depends_on.value) {
                    return;
                }
            }

            const formGroup = document.createElement('div');
            formGroup.className = 'mb-3';

            // Create label with sanitized text
            const label = document.createElement('label');
            label.className = 'form-label';
            label.htmlFor = prefix + key;
            const displayKey = config.depends_on ? 
                key.replace(config.depends_on.value + '_', '') : key;
            label.textContent = api.sanitizeInput(
                displayKey.charAt(0).toUpperCase() + 
                displayKey.slice(1).replace(/_/g, ' ')
            );

            if (config.required) {
                const requiredSpan = document.createElement('span');
                requiredSpan.className = 'text-danger ms-1';
                requiredSpan.textContent = '*';
                label.appendChild(requiredSpan);
            }

            // Create input with proper validation and sanitization
            let input = createSecureInput(config, prefix + key);
            
            // Set common input attributes
            input.className = 'form-control';
            input.id = prefix + key;
            input.name = prefix + key;
            if (config.required) input.required = true;

            // Restore previous value if it exists
            if (currentValues[key] !== undefined) {
                input.value = currentValues[key];
            } else if (config.default !== undefined && !['list', 'dict'].includes(config.type)) {
                input.value = api.sanitizeInput(config.default);
            }

            // Add description if provided
            if (config.description) {
                const helpText = document.createElement('div');
                helpText.className = 'form-text';
                helpText.textContent = api.sanitizeInput(config.description);
                formGroup.appendChild(helpText);
            }

            formGroup.appendChild(label);
            formGroup.appendChild(input);

            // Add validation feedback
            const invalidFeedback = document.createElement('div');
            invalidFeedback.className = 'invalid-feedback';
            invalidFeedback.textContent = `Please provide a valid ${displayKey.replace(/_/g, ' ')}`;
            formGroup.appendChild(invalidFeedback);

            container.appendChild(formGroup);
        } catch (error) {
            console.error('Error generating parameter field:', error);
            showToast(`Error generating field: ${key}`, 'danger');
        }
    });
}

// Helper function to create secure input elements
function createSecureInput(config, id) {
    let input;
    
    try {
        switch (config.type) {
            case 'integer':
                input = document.createElement('input');
                input.type = 'number';
                input.step = '1';
                if (config.min !== undefined) input.min = config.min;
                if (config.max !== undefined) input.max = config.max;
                
                // Add input validation
                input.addEventListener('input', function() {
                    const value = parseInt(this.value);
                    if (config.min !== undefined && value < config.min) this.value = config.min;
                    if (config.max !== undefined && value > config.max) this.value = config.max;
                });
                break;

            case 'float':
                input = document.createElement('input');
                input.type = 'number';
                input.step = '0.01';
                if (config.min !== undefined) input.min = config.min;
                if (config.max !== undefined) input.max = config.max;
                
                // Add input validation
                input.addEventListener('input', function() {
                    const value = parseFloat(this.value);
                    if (config.min !== undefined && value < config.min) this.value = config.min;
                    if (config.max !== undefined && value > config.max) this.value = config.max;
                });
                break;

            case 'boolean':
                input = document.createElement('select');
                input.innerHTML = `
                    <option value="true">Yes</option>
                    <option value="false" ${config.default === false ? 'selected' : ''}>No</option>
                `;
                break;

            case 'url':
                input = document.createElement('input');
                input.type = 'url';
                input.pattern = '^https?:\\/\\/[\\w\\-]+(\\.[\\w\\-]+)+[/#?]?.*$';
                input.placeholder = 'https://';
                
                // Add URL validation
                input.addEventListener('change', function() {
                    try {
                        new URL(this.value);
                    } catch {
                        this.setCustomValidity('Please enter a valid URL');
                        return;
                    }
                    this.setCustomValidity('');
                });
                break;

            case 'list':
                input = document.createElement('textarea');
                input.placeholder = 'Enter one item per line';
                input.rows = 3;
                if (Array.isArray(config.default)) {
                    input.value = api.sanitizeInput(config.default.join('\n'));
                }
                break;

            case 'dict':
                input = document.createElement('textarea');
                input.placeholder = 'Enter JSON object';
                input.rows = 3;
                if (config.default) {
                    input.value = api.sanitizeInput(JSON.stringify(config.default, null, 2));
                }
                
                // Add JSON validation
                input.addEventListener('change', function() {
                    try {
                        JSON.parse(this.value);
                        this.setCustomValidity('');
                    } catch {
                        this.setCustomValidity('Please enter valid JSON');
                    }
                });
                break;

            default:
                input = document.createElement('input');
                input.type = 'text';
                
                // Add basic XSS protection
                input.addEventListener('input', function() {
                    this.value = api.sanitizeInput(this.value);
                });
        }

        // Add common security features
        input.id = id;
        input.autocomplete = 'off';
        input.spellcheck = false;
        
        // Prevent script injection in attributes
        input.setAttribute('data-original-id', api.sanitizeInput(id));

        return input;
    } catch (error) {
        console.error('Error creating input:', error);
        // Return a safe default input if something goes wrong
        const defaultInput = document.createElement('input');
        defaultInput.type = 'text';
        defaultInput.id = id;
        return defaultInput;
    }
}

// Centralized error handling
function handleApiError(error, userMessage = 'An error occurred') {
    console.error(error);
    showToast(userMessage, 'danger');
}

// Task management functions
async function runTask(taskId) {
    try {
        await api.call(`/api/tasks/${taskId}/run`, {
            method: 'POST'
        });
        
        startPollingTask(taskId);
        showToast('Task started successfully', 'success');
    } catch (error) {
        handleApiError(error, 'Failed to run task');
    }
}

async function deleteTask(taskId) {
    if (!confirm('Are you sure you want to delete this task? This action cannot be undone.')) {
        return;
    }

    try {
        await api.call(`/api/tasks/${taskId}`, {
            method: 'DELETE'
        });
        
        showToast('Task deleted successfully', 'success');
        window.location.href = '/tasks';
    } catch (error) {
        handleApiError(error, 'Failed to delete task');
    }
}

// Optimize task polling with secure API client
let pollTimeouts = new Map();
const POLL_INTERVAL = 5000;
const MAX_RETRIES = 3;

function startPollingTask(taskId) {
    if (pollTimeouts.has(taskId)) {
        return;
    }

    let retryCount = 0;
    const poll = async () => {
        try {
            const data = await api.call(`/api/tasks/${taskId}/status`);
            updateTaskStatus(taskId, data);
            
            if (['completed', 'failed'].includes(data.status.toLowerCase())) {
                stopPollingTask(taskId);
                if (data.status.toLowerCase() === 'completed') {
                    showToast('Task completed successfully', 'success');
                } else {
                    showToast('Task failed', 'danger');
                }
            } else {
                pollTimeouts.set(taskId, setTimeout(poll, POLL_INTERVAL));
            }
            retryCount = 0;
        } catch (error) {
            console.error('Error polling task status:', error);
            retryCount++;
            
            if (retryCount >= MAX_RETRIES) {
                stopPollingTask(taskId);
                handleApiError(error, 'Failed to get task status');
            } else {
                // Exponential backoff
                const backoffTime = POLL_INTERVAL * Math.pow(2, retryCount);
                pollTimeouts.set(taskId, setTimeout(poll, backoffTime));
            }
        }
    };

    // Add loading indicator to status badge
    const elements = document.querySelectorAll(`[data-task-id="${taskId}"]`);
    elements.forEach(element => {
        const statusBadge = element.querySelector('.badge');
        if (statusBadge) {
            const currentText = statusBadge.textContent.trim();
            statusBadge.innerHTML = `<i class="fas fa-spinner fa-spin me-1"></i>${currentText}`;
        }
    });

    poll();
}

function stopPollingTask(taskId) {
    const timeout = pollTimeouts.get(taskId);
    if (timeout) {
        clearTimeout(timeout);
        pollTimeouts.delete(taskId);
    }
} 