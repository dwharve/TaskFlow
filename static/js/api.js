/**
 * Handle API response and extract data
 * @param {Response} response - Fetch API response
 * @param {string} dataField - Optional field name to extract from response
 * @returns {Promise<any>} Extracted data or entire response data
 * @throws {Error} If response indicates an error
 */
async function handleApiResponse(response, dataField = null) {
    if (!response.ok) {
        const data = await response.json();
        throw new Error(data.message || 'An error occurred');
    }
    
    const data = await response.json();
    
    if (data.status === 'error') {
        throw new Error(data.message);
    }
    
    return dataField ? data[dataField] : data;
}

/**
 * Load blocks for a task
 * @param {number} taskId - Task ID
 * @returns {Promise<{blocks: Array, connections: Array}>}
 */
async function loadTaskBlocks(taskId) {
    const response = await fetch(`/api/tasks/${taskId}/blocks`, {
        headers: {
            'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
        }
    });
    
    const data = await handleApiResponse(response);
    return {
        blocks: data.blocks || [],
        connections: data.connections || []
    };
}

/**
 * Load block parameters
 * @param {string} blockType - Type of block
 * @param {string} blockName - Name of block
 * @returns {Promise<Object>}
 */
async function loadBlockParameters(blockType, blockName) {
    const response = await fetch(`/api/blocks/${blockType}/${blockName}/parameters`, {
        headers: {
            'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
        }
    });
    
    const data = await handleApiResponse(response);
    return data.parameters || {};
}

/**
 * Get task status
 * @param {number} taskId - Task ID
 * @returns {Promise<Object>}
 */
async function getTaskStatus(taskId) {
    const response = await fetch(`/api/tasks/${taskId}/status`, {
        headers: {
            'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
        }
    });
    
    const data = await handleApiResponse(response);
    return {
        status: data.status,
        status_class: data.status_class,
        last_run: data.last_run,
        block_data: data.block_data
    };
}

/**
 * Get multiple task statuses
 * @param {Array<number>} taskIds - Array of task IDs
 * @returns {Promise<Object>}
 */
async function getTasksStatus(taskIds) {
    const response = await fetch(`/api/tasks/status?ids=${taskIds.join(',')}`, {
        headers: {
            'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
        }
    });
    
    const data = await handleApiResponse(response);
    return data.tasks || {};
}

/**
 * Run a task
 * @param {number} taskId - Task ID
 * @returns {Promise<void>}
 */
async function runTask(taskId) {
    const response = await fetch(`/api/tasks/${taskId}/run`, {
        method: 'POST',
        headers: {
            'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
        }
    });
    
    await handleApiResponse(response);
}

/**
 * Delete a task
 * @param {number} taskId - Task ID
 * @returns {Promise<void>}
 */
async function deleteTask(taskId) {
    const response = await fetch(`/api/tasks/${taskId}`, {
        method: 'DELETE',
        headers: {
            'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
        }
    });
    
    await handleApiResponse(response);
} 