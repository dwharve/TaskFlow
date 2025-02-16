let blockValidationCache = new Map();  // Store validation state for each block
let isPanning = false;
let startPoint = { x: 0, y: 0 };
let currentTranslate = { x: 0, y: 0 };  // Start at center
let currentZoom = 1;  // Current zoom level
const MIN_ZOOM = 0.4;  // Minimum zoom level (40%)
const MAX_ZOOM = 2;    // Maximum zoom level (200%)
const ZOOM_SPEED = 0.1; // How much to zoom per scroll

// Calculate block layout dimensions
function calculateBlocksBoundingBox(blocks) {
    if (blocks.length === 0) return { minX: 2400, minY: 2400, maxX: 2600, maxY: 2600 };
    
    let minX = Infinity, minY = Infinity;
    let maxX = -Infinity, maxY = -Infinity;
    
    blocks.forEach(block => {
        const x = block.position_x || 0;
        const y = block.position_y || 0;
        minX = Math.min(minX, x);
        minY = Math.min(minY, y);
        maxX = Math.max(maxX, x + 200); // 200 is block width
        maxY = Math.max(maxY, y + 100); // Approximate block height
    });
    
    return { minX, minY, maxX, maxY };
}

// Load existing blocks if editing
async function loadBlocksFromApi() {
    const taskId = document.getElementById('taskId')?.value;
    if (!taskId) return;  // Not editing an existing task
    
    try {
        const response = await fetch(`/api/tasks/${taskId}/blocks`, {
            headers: {
                'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
            }
        });
        
        if (!response.ok) {
            throw new Error('Failed to load block data');
        }
        
        const blocksData = await response.json();
        loadExistingBlocks(blocksData);
    } catch (error) {
        console.error('Error loading blocks:', error);
        showToast('Failed to load block data', 'danger');
    }
}

// Handle panning
function initializePanning() {
    const canvas = document.getElementById('blockCanvas');
    const container = canvas.parentElement;
    let lastX = 0;
    let lastY = 0;
    let animationFrameId = null;

    // Set initial styles for container
    container.style.overflow = 'hidden';
    container.style.position = 'relative';
    canvas.style.position = 'absolute';
    
    // Set initial transform
    updateCanvasTransform();
    canvas.style.cursor = 'grab';

    // Pan start
    canvas.addEventListener('mousedown', function(e) {
        // Only start panning if not clicking on a block or endpoint
        if (e.target === canvas) {
            isPanning = true;
            canvas.style.cursor = 'grabbing';
            lastX = e.clientX;
            lastY = e.clientY;
            e.preventDefault();
        }
    });

    // Pan move
    document.addEventListener('mousemove', function(e) {
        if (!isPanning) return;

        // Cancel any pending animation frame
        if (animationFrameId) {
            cancelAnimationFrame(animationFrameId);
        }

        // Schedule the update on the next animation frame
        animationFrameId = requestAnimationFrame(() => {
            const deltaX = e.clientX - lastX;
            const deltaY = e.clientY - lastY;
            lastX = e.clientX;
            lastY = e.clientY;

            const containerRect = container.getBoundingClientRect();
            
            // Calculate the visible canvas dimensions at current zoom
            const visibleWidth = containerRect.width;
            const visibleHeight = containerRect.height;
            
            // Calculate the scaled canvas dimensions
            const scaledCanvasWidth = 5000 * currentZoom;
            const scaledCanvasHeight = 5000 * currentZoom;
            
            // Calculate the maximum allowed translation to keep canvas in view
            const maxTranslateX = Math.max(0, (scaledCanvasWidth - visibleWidth) / 2);
            const maxTranslateY = Math.max(0, (scaledCanvasHeight - visibleHeight) / 2);
            
            // Calculate new translation with boundaries
            let newTranslateX = currentTranslate.x + deltaX;
            let newTranslateY = currentTranslate.y + deltaY;
            
            // Restrict horizontal movement
            newTranslateX = Math.max(-maxTranslateX, Math.min(maxTranslateX, newTranslateX));
            
            // Restrict vertical movement
            newTranslateY = Math.max(-maxTranslateY, Math.min(maxTranslateY, newTranslateY));
            
            currentTranslate = {
                x: newTranslateX,
                y: newTranslateY
            };

            updateCanvasTransform();
            
            // Throttle jsPlumb repaints to reduce performance impact
            if (!window.isRepainting) {
                window.isRepainting = true;
                setTimeout(() => {
                    window.jsPlumbInstance?.repaintEverything();
                    window.isRepainting = false;
                }, 100);
            }
        });
    });

    // Pan end
    document.addEventListener('mouseup', function() {
        if (isPanning) {
            isPanning = false;
            canvas.style.cursor = 'grab';
            if (animationFrameId) {
                cancelAnimationFrame(animationFrameId);
            }
            // Final repaint to ensure connections are correct
            window.jsPlumbInstance?.repaintEverything();
        }
    });

    // Prevent panning when interacting with blocks
    document.querySelectorAll('.block-node').forEach(block => {
        block.addEventListener('mousedown', e => e.stopPropagation());
    });

    // Zoom with mouse wheel
    container.addEventListener('wheel', function(e) {
        e.preventDefault();
        
        const rect = container.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;
        
        // Calculate zoom
        const delta = -Math.sign(e.deltaY) * ZOOM_SPEED;
        const newZoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, currentZoom + delta));
        
        // Only update if zoom level actually changed
        if (newZoom !== currentZoom) {
            // Calculate the mouse position relative to the canvas center
            const canvasWidth = rect.width;
            const canvasHeight = rect.height;
            const canvasCenterX = canvasWidth / 2;
            const canvasCenterY = canvasHeight / 2;
            
            // Get the mouse position relative to the canvas center
            const mouseFromCenterX = mouseX - canvasCenterX;
            const mouseFromCenterY = mouseY - canvasCenterY;
            
            // Calculate how much the mouse point will move at the new scale
            const scaleFactor = newZoom / currentZoom;
            const scaledMouseX = mouseFromCenterX * scaleFactor;
            const scaledMouseY = mouseFromCenterY * scaleFactor;
            
            // Calculate the required translation to keep the mouse point fixed
            const translateX = mouseFromCenterX - scaledMouseX;
            const translateY = mouseFromCenterY - scaledMouseY;
            
            // Update the translation to maintain mouse position
            currentTranslate.x += translateX;
            currentTranslate.y += translateY;
            
            // Calculate boundaries for new zoom level
            const visibleWidth = rect.width;
            const visibleHeight = rect.height;
            const scaledCanvasWidth = 5000 * newZoom;
            const scaledCanvasHeight = 5000 * newZoom;
            const maxTranslateX = Math.max(0, (scaledCanvasWidth - visibleWidth) / 2);
            const maxTranslateY = Math.max(0, (scaledCanvasHeight - visibleHeight) / 2);
            
            // Apply boundaries
            currentTranslate.x = Math.max(-maxTranslateX, Math.min(maxTranslateX, currentTranslate.x));
            currentTranslate.y = Math.max(-maxTranslateY, Math.min(maxTranslateY, currentTranslate.y));
            
            // Update zoom level
            currentZoom = newZoom;
            
            // Apply transform
            updateCanvasTransform();
            window.jsPlumbInstance?.setZoom(currentZoom);
            
            // Update CSS variable for grid scaling
            canvas.style.setProperty('--zoom', currentZoom);
        }
    }, { passive: false });
}

// Helper function to update canvas transform
function updateCanvasTransform() {
    const canvas = document.getElementById('blockCanvas');
    canvas.style.transform = `translate(calc(-50% + ${currentTranslate.x}px), calc(-50% + ${currentTranslate.y}px)) scale(${currentZoom})`;
}

// Add block with position relative to canvas center
function addBlock(name, type, displayName, description) {
    const id = `block_${++window.blockCounter}`;
    const template = document.getElementById('blockTemplate');
    const clone = template.content.cloneNode(true);
    const blockNode = clone.querySelector('.block-node');
    
    // Set block properties
    blockNode.dataset.blockId = id;
    blockNode.dataset.blockName = name;
    blockNode.dataset.blockType = type;
    blockNode.classList.add(`${type}-block`);
    blockNode.querySelector('.block-type').textContent = displayName;
    
    // Set default block name
    blockNode.querySelector('.block-name').textContent = displayName;
    
    // Add endpoints based on type
    if (type !== 'input') {
        const inputEndpoint = document.createElement('div');
        inputEndpoint.className = 'endpoint input';
        blockNode.appendChild(inputEndpoint);
    }
    
    if (type !== 'action') {
        const outputEndpoint = document.createElement('div');
        outputEndpoint.className = 'endpoint output';
        blockNode.appendChild(outputEndpoint);
    }
    
    // Get current blocks bounding box
    const existingBlocks = Array.from(window.blocks.values()).map(b => ({
        position_x: parseInt(b.element.style.left),
        position_y: parseInt(b.element.style.top)
    }));
    const bbox = calculateBlocksBoundingBox(existingBlocks);
    
    // Position new block relative to existing blocks
    const padding = 50;
    let newX, newY;
    
    if (existingBlocks.length === 0) {
        // First block goes in center
        newX = 2500;
        newY = 2500;
    } else {
        // Add new block to the right or below existing blocks
        if (bbox.maxX - bbox.minX > bbox.maxY - bbox.minY) {
            // Layout is wider than tall, add below
            newX = (bbox.minX + bbox.maxX) / 2;
            newY = bbox.maxY + padding;
        } else {
            // Layout is taller than wide, add to right
            newX = bbox.maxX + padding;
            newY = (bbox.minY + bbox.maxY) / 2;
        }
    }
    
    blockNode.style.left = `${newX}px`;
    blockNode.style.top = `${newY}px`;
    
    // Add block to canvas
    const canvas = document.getElementById('blockCanvas');
    canvas.appendChild(blockNode);
    
    // Prevent block dragging from triggering canvas panning
    blockNode.addEventListener('mousedown', e => e.stopPropagation());
    
    // Make block draggable
    if (window.jsPlumbInstance) {
        window.jsPlumbInstance.draggable(blockNode, {
            grid: [10, 10],
            drag: function() {
                window.jsPlumbInstance.repaintEverything();
            }
        });
        
        // Add endpoints
        if (type !== 'input') {
            window.jsPlumbInstance.addEndpoint(blockNode, {
                anchor: 'Left',
                isTarget: true,
                maxConnections: -1
            });
        }
        
        if (type !== 'action') {
            window.jsPlumbInstance.addEndpoint(blockNode, {
                anchor: 'Right',
                isSource: true,
                maxConnections: -1
            });
        }
    }
    
    // Store block data
    window.blocks.set(id, {
        element: blockNode,
        data: {
            id,
            name,
            type,
            display_name: displayName,
            parameters: {},
            position_x: newX,
            position_y: newY
        }
    });
    
    // Load parameters modal for immediate configuration
    editBlockParameters(blockNode.querySelector('.btn-primary'));
}

function removeBlock(button) {
    const blockNode = button.closest('.block-node');
    const id = blockNode.dataset.blockId;
    
    // Remove all connections
    if (window.jsPlumbInstance) {
        window.jsPlumbInstance.removeAllEndpoints(blockNode);
    }
    
    // Remove block
    blockNode.remove();
    window.blocks.delete(id);
    // Clear validation cache for this block
    blockValidationCache.delete(id);
}

// Initialize modal with proper focus management
document.addEventListener('DOMContentLoaded', function() {
    const blockParamsModalEl = document.getElementById('blockParamsModal');
    const mainContent = document.getElementById('mainContent');
    
    if (blockParamsModalEl) {
        window.blockParamsModal = new bootstrap.Modal(blockParamsModalEl, {
            backdrop: true,  // Allow clicking outside to close
            keyboard: true   // Allow closing with Escape key
        });
        
        // Store the element that had focus before opening the modal
        let previousActiveElement = null;
        
        // Handle focus management when modal opens
        blockParamsModalEl.addEventListener('show.bs.modal', function() {
            // Store the currently focused element before making content inert
            previousActiveElement = document.activeElement;
            
            // First move focus to the modal to ensure no focused element when setting inert
            blockParamsModalEl.focus();
            
            // Make main content inert
            if (mainContent) {
                mainContent.inert = true;
            }
        });
        
        blockParamsModalEl.addEventListener('shown.bs.modal', function() {
            // Set focus to the block name input when modal opens
            const blockNameInput = document.getElementById('block_name');
            if (blockNameInput) {
                blockNameInput.focus();
            }
        });
        
        // Handle focus management when modal closes
        blockParamsModalEl.addEventListener('hide.bs.modal', function() {
            // Remove inert from main content
            if (mainContent) {
                mainContent.inert = false;
            }
        });
        
        blockParamsModalEl.addEventListener('hidden.bs.modal', function() {
            // Clear currentEditingBlock
            window.currentEditingBlock = null;
            
            // Return focus to the previous element
            if (previousActiveElement && document.contains(previousActiveElement)) {
                previousActiveElement.focus();
            }
            previousActiveElement = null;
        });
        
        // Handle tab key in modal
        blockParamsModalEl.addEventListener('keydown', function(e) {
            if (e.key === 'Tab') {
                const focusableElements = blockParamsModalEl.querySelectorAll(
                    'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
                );
                const firstFocusableElement = focusableElements[0];
                const lastFocusableElement = focusableElements[focusableElements.length - 1];
                
                if (e.shiftKey) {
                    if (document.activeElement === firstFocusableElement) {
                        e.preventDefault();
                        lastFocusableElement.focus();
                    }
                } else {
                    if (document.activeElement === lastFocusableElement) {
                        e.preventDefault();
                        firstFocusableElement.focus();
                    }
                }
            }
        });
    }
});

async function editBlockParameters(button) {
    const blockNode = button.closest('.block-node');
    const blockId = blockNode.dataset.blockId;
    const blockName = blockNode.dataset.blockName;
    const blockType = blockNode.dataset.blockType;
    
    window.currentEditingBlock = window.blocks.get(blockId);
    
    try {
        const response = await fetch(`/api/blocks/${blockType}/${blockName}/parameters`, {
            headers: {
                'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
            }
        });
        if (!response.ok) throw new Error('Failed to load parameters');
        
        const parameters = await response.json();
        
        // Set block name in modal
        const blockNameInput = document.getElementById('block_name');
        blockNameInput.value = window.currentEditingBlock.data.display_name;
        
        const container = document.getElementById('modalBlockParams');
        container.innerHTML = '';
        
        // Add block info
        const blockInfo = document.createElement('div');
        blockInfo.className = 'alert alert-info alert-permanent';
        blockInfo.innerHTML = `
            <h6 class="alert-heading">${blockNode.querySelector('.block-type').textContent}</h6>
            <small class="text-muted">${blockType} block</small>
        `;
        container.appendChild(blockInfo);
        
        // Add parameters
        for (const [name, config] of Object.entries(parameters)) {
            const formGroup = document.createElement('div');
            formGroup.className = 'mb-3';
            
            const label = document.createElement('label');
            label.className = 'form-label';
            label.htmlFor = `param_${name}`;
            label.textContent = config.description;
            
            let input;
            if (config.type === 'boolean') {
                input = document.createElement('div');
                input.className = 'form-check';
                const checkbox = document.createElement('input');
                checkbox.type = 'checkbox';
                checkbox.className = 'form-check-input';
                checkbox.id = `param_${name}`;
                checkbox.checked = window.currentEditingBlock.data.parameters[name] ?? config.default ?? false;
                input.appendChild(checkbox);
            } else if (config.type === 'template') {
                input = document.createElement('textarea');
                input.className = 'form-control font-monospace';
                input.id = `param_${name}`;
                input.value = window.currentEditingBlock.data.parameters[name] ?? config.default ?? '';
                input.required = config.required;
                input.rows = 10;
                input.setAttribute('aria-describedby', `help_${name}`);
            } else {
                input = document.createElement('input');
                input.type = config.type === 'integer' ? 'number' : 'text';
                input.className = 'form-control';
                input.id = `param_${name}`;
                input.value = window.currentEditingBlock.data.parameters[name] ?? config.default ?? '';
                input.required = config.required;
                input.setAttribute('aria-describedby', `help_${name}`);
            }
            
            formGroup.appendChild(label);
            formGroup.appendChild(input);
            
            if (config.description) {
                const helpText = document.createElement('div');
                helpText.className = 'form-text';
                helpText.id = `help_${name}`;
                helpText.textContent = config.description;
                formGroup.appendChild(helpText);
            }
            
            container.appendChild(formGroup);
        }
        
        // Show modal
        window.blockParamsModal.show();
        
    } catch (error) {
        console.error('Error loading parameters:', error);
        alert('Failed to load block parameters');
    }
}

async function saveBlockParameters() {
    if (!window.currentEditingBlock) return;
    
    // Save block name
    const blockNameInput = document.getElementById('block_name');
    const newBlockName = blockNameInput.value.trim() || window.currentEditingBlock.data.display_name;
    window.currentEditingBlock.data.display_name = newBlockName;
    window.currentEditingBlock.element.querySelector('.block-name').textContent = newBlockName;
    
    // Save parameters
    const parameters = {};
    const container = document.getElementById('modalBlockParams');
    
    try {
        // Collect all parameter values
        container.querySelectorAll('input, textarea').forEach(input => {
            const paramName = input.id.replace('param_', '');
            let value;
            
            if (input.type === 'checkbox') {
                value = input.checked;
            } else {
                value = input.value.trim();
                // Try to parse JSON for parameters that should be objects
                if (['headers', 'post_data'].includes(paramName)) {
                    try {
                        // Replace single quotes with double quotes for JSON parsing
                        const jsonStr = value.replace(/'/g, '"');
                        value = JSON.parse(jsonStr);
                    } catch (e) {
                        console.warn(`Failed to parse JSON for ${paramName}, using as string`);
                    }
                }
            }
            parameters[paramName] = value;
        });

        // Validate parameters before saving
        const response = await fetch(`/api/blocks/${window.currentEditingBlock.data.type}/${window.currentEditingBlock.data.name}/parameters`, {
            headers: {
                'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
            }
        });
        if (!response.ok) throw new Error('Failed to load parameters');
        
        const parameterDefs = await response.json();
        let isValid = true;
        let firstInvalidParam = null;

        for (const [paramName, config] of Object.entries(parameterDefs)) {
            if (config.required && (parameters[paramName] === undefined || parameters[paramName] === null || 
                (typeof parameters[paramName] === 'string' && parameters[paramName].trim() === ''))) {
                isValid = false;
                firstInvalidParam = paramName;
                break;
            }
        }

        if (!isValid) {
            showToast(`Required parameter "${firstInvalidParam}" cannot be empty`, 'warning');
            blockValidationCache.set(window.currentEditingBlock.data.id, false);
            return;
        }

        // Store validation state
        blockValidationCache.set(window.currentEditingBlock.data.id, true);
        
        // Update block data
        window.currentEditingBlock.data.parameters = parameters;
        
        // Close modal and return focus to the block's edit button
        window.blockParamsModal.hide();
        const blockNode = window.currentEditingBlock.element;
        const editButton = blockNode.querySelector('.btn-primary');
        if (editButton) {
            editButton.focus();
        }
    } catch (error) {
        console.error('Error validating parameters:', error);
        showToast('Failed to validate parameters', 'danger');
        blockValidationCache.set(window.currentEditingBlock.data.id, false);
    }
}

// Update loadExistingBlocks to handle centered positioning
function loadExistingBlocks(blocksData) {
    if (!window.jsPlumbInstance) return;
    
    // Create a mapping of database block IDs to generated IDs
    const blockIdMap = new Map();
    
    // Calculate bounding box of existing blocks
    const bbox = calculateBlocksBoundingBox(blocksData.blocks);
    const centerX = (bbox.minX + bbox.maxX) / 2;
    const centerY = (bbox.minY + bbox.maxY) / 2;
    
    // Calculate offset to center blocks
    const offsetX = 2500 - centerX;
    const offsetY = 2500 - centerY;
    
    // First create all blocks
    for (const blockData of blocksData.blocks) {
        const generatedId = `block_${++window.blockCounter}`;
        blockIdMap.set(blockData.id, generatedId);
        
        const template = document.getElementById('blockTemplate');
        const clone = template.content.cloneNode(true);
        const blockNode = clone.querySelector('.block-node');
        
        // Set block properties
        blockNode.dataset.blockId = generatedId;
        blockNode.dataset.dbId = blockData.id;
        blockNode.dataset.blockName = blockData.name;
        blockNode.dataset.blockType = blockData.type;
        blockNode.classList.add(`${blockData.type}-block`);
        
        // Set the display name and block type text
        const displayName = blockData.display_name || blockData.name;
        blockNode.querySelector('.block-type').textContent = blockData.name;
        blockNode.querySelector('.block-name').textContent = displayName;
        
        // Add endpoints based on type
        if (blockData.type !== 'input') {
            const inputEndpoint = document.createElement('div');
            inputEndpoint.className = 'endpoint input';
            blockNode.appendChild(inputEndpoint);
        }
        
        if (blockData.type !== 'action') {
            const outputEndpoint = document.createElement('div');
            outputEndpoint.className = 'endpoint output';
            blockNode.appendChild(outputEndpoint);
        }
        
        // Position block with offset to center
        const newX = blockData.position_x + offsetX;
        const newY = blockData.position_y + offsetY;
        blockNode.style.left = `${newX}px`;
        blockNode.style.top = `${newY}px`;
        
        // Add block to canvas
        document.getElementById('blockCanvas').appendChild(blockNode);
        
        // Prevent block dragging from triggering canvas panning
        blockNode.addEventListener('mousedown', e => e.stopPropagation());
        
        // Make block draggable
        window.jsPlumbInstance.draggable(blockNode, {
            grid: [10, 10],
            drag: function() {
                window.jsPlumbInstance.repaintEverything();
            }
        });
        
        // Add endpoints
        if (blockData.type !== 'input') {
            window.jsPlumbInstance.addEndpoint(blockNode, {
                anchor: 'Left',
                isTarget: true,
                maxConnections: -1
            });
        }
        
        if (blockData.type !== 'action') {
            window.jsPlumbInstance.addEndpoint(blockNode, {
                anchor: 'Right',
                isSource: true,
                maxConnections: -1
            });
        }
        
        // Store block data
        window.blocks.set(generatedId, {
            element: blockNode,
            data: {
                id: generatedId,
                db_id: blockData.id,
                name: blockData.name,
                type: blockData.type,
                display_name: displayName,
                parameters: blockData.parameters || {},
                position_x: newX,
                position_y: newY
            }
        });
        
        // Initialize validation cache for this block
        // Since this is an existing block with parameters, we can assume it was valid
        blockValidationCache.set(generatedId, true);
    }
    
    // Then create connections
    for (const connData of blocksData.connections) {
        const sourceId = blockIdMap.get(connData.source);
        const targetId = blockIdMap.get(connData.target);
        
        if (sourceId && targetId) {
            const sourceBlock = window.blocks.get(sourceId)?.element;
            const targetBlock = window.blocks.get(targetId)?.element;
            
            if (sourceBlock && targetBlock) {
                window.jsPlumbInstance.connect({
                    source: sourceBlock,
                    target: targetBlock,
                    anchors: ['Right', 'Left']
                });
            }
        }
    }
}

// Handle form submission
document.addEventListener('DOMContentLoaded', function() {
    const taskForm = document.getElementById('taskForm');
    if (taskForm) {
        taskForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            
            // Generate schedule
            if (!generateSchedule()) {
                showToast('Please select at least one day of the week for weekly schedule.', 'warning');
                return;
            }
            
            // Validate block connections
            const connections = window.jsPlumbInstance ? 
                window.jsPlumbInstance.getAllConnections().map(conn => {
                    const sourceElement = conn.source;
                    const targetElement = conn.target;
                    return {
                        source: sourceElement.dataset.dbId || sourceElement.dataset.blockId,
                        target: targetElement.dataset.dbId || targetElement.dataset.blockId
                    };
                }) : [];
            
            // Check that all non-input blocks have inputs
            for (const [id, block] of window.blocks) {
                if (block.data.type !== 'input') {
                    const blockElement = block.element;
                    const blockId = blockElement.dataset.dbId || blockElement.dataset.blockId;
                    const hasInput = connections.some(conn => conn.target === blockId);
                    if (!hasInput) {
                        showToast(`Block "${block.data.display_name}" has no input connection.`, 'warning');
                        return;
                    }
                }
            }

            // Check validation state for all blocks
            for (const [id, block] of window.blocks) {
                if (!blockValidationCache.has(id) || !blockValidationCache.get(id)) {
                    showToast(`Please configure all required parameters for block "${block.data.display_name}"`, 'warning');
                    return;
                }
            }
            
            // Update block positions
            for (const [id, block] of window.blocks) {
                block.data.position_x = parseInt(block.element.style.left);
                block.data.position_y = parseInt(block.element.style.top);
            }
            
            // Prepare blocks data with proper JSON handling
            const blocksData = {
                blocks: Array.from(window.blocks.values()).map(block => {
                    // Create a copy of the block data
                    const blockData = { ...block.data };
                    
                    // Handle parameters that might be objects
                    blockData.parameters = Object.fromEntries(
                        Object.entries(block.data.parameters).map(([key, value]) => {
                            // If the value is already a string representation of an object, parse it first
                            if (typeof value === 'string' && value.startsWith('{')) {
                                try {
                                    value = JSON.parse(value);
                                } catch (e) {
                                    // If parsing fails, keep original string
                                    console.warn(`Failed to parse JSON string for ${key}:`, value);
                                }
                            }
                            
                            // Now properly stringify any objects
                            if (typeof value === 'object' && value !== null) {
                                return [key, JSON.stringify(value)];
                            }
                            return [key, value];
                        })
                    );
                    
                    return blockData;
                }),
                connections: window.jsPlumbInstance ? 
                    window.jsPlumbInstance.getAllConnections().map(conn => {
                        const sourceElement = conn.source;
                        const targetElement = conn.target;
                        
                        // Create a map of block elements to their index in the blocks array
                        const blockElements = Array.from(window.blocks.values()).map(b => b.element);
                        const sourceIndex = blockElements.indexOf(sourceElement);
                        const targetIndex = blockElements.indexOf(targetElement);
                        
                        return {
                            source: sourceIndex,
                            target: targetIndex
                        };
                    }).filter(conn => conn.source !== -1 && conn.target !== -1) : []
            };
            
            // Prepare form data
            const formData = new FormData(taskForm);
            formData.set('blocks_data', JSON.stringify(blocksData));

            // Disable form submission button to prevent double submission
            const submitButton = taskForm.querySelector('button[type="submit"]');
            if (submitButton) {
                submitButton.disabled = true;
            }

            try {
                const response = await fetch(taskForm.action || window.location.href, {
                    method: 'POST',
                    body: formData,
                    headers: {
                        'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content,
                        // Don't set Content-Type header - let the browser set it with the correct boundary for FormData
                    }
                });

                let data;
                try {
                    data = await response.json();
                } catch (e) {
                    throw new Error('Invalid response from server');
                }

                if (!response.ok) {
                    throw new Error(data.error || 'Failed to save task');
                }

                if (data.status === 'success') {
                    // Handle successful response
                    showToast('Task saved successfully', 'success');
                    // Redirect to tasks page after a short delay
                    setTimeout(() => {
                        window.location.href = '/tasks';
                    }, 1000);
                } else {
                    throw new Error(data.error || 'Failed to save task');
                }
            } catch (error) {
                console.error('Error saving task:', error);
                showToast(error.message || 'Failed to save task', 'danger');
                // Re-enable submit button on error
                if (submitButton) {
                    submitButton.disabled = false;
                }
            }
        });
    }
});

document.addEventListener('DOMContentLoaded', function() {
    // Wait for jsPlumb to be fully loaded
    if (typeof jsPlumb !== 'undefined') {
        window.jsPlumbInstance = jsPlumb.getInstance({
            Container: 'blockCanvas',
            ConnectionsDetachable: true,
            Connector: ['Bezier', { curviness: 50 }],
            Endpoint: ['Dot', { radius: 8 }],
            PaintStyle: { stroke: '#6c757d', strokeWidth: 2 },
            HoverPaintStyle: { stroke: '#007bff', strokeWidth: 3 },
            EndpointStyle: { 
                fill: '#6c757d', 
                stroke: '#6c757d',
                strokeWidth: 2,
                radius: 8
            },
            EndpointHoverStyle: { 
                fill: '#007bff', 
                stroke: '#007bff',
                strokeWidth: 2,
                radius: 10
            }
        });
        
        // Initialize panning
        initializePanning();
        
        // Load existing blocks if editing
        loadBlocksFromApi();
    }
});

async function loadBlockData() {
    try {
        const taskId = document.getElementById('task-id').value;
        const { blocks, connections } = await loadTaskBlocks(taskId);
        loadExistingBlocks(blocks, connections);
    } catch (error) {
        console.error('Failed to load block data:', error);
        showError('Failed to load block data: ' + error.message);
    }
}

async function loadBlockParametersForm(blockType, blockName) {
    try {
        const parameters = await loadBlockParameters(blockType, blockName);
        populateParametersForm(parameters);
    } catch (error) {
        console.error('Failed to load block parameters:', error);
        showError('Failed to load block parameters: ' + error.message);
    }
}

async function updateTaskStatus() {
    try {
        const taskId = document.getElementById('task-id').value;
        const taskStatus = await getTaskStatus(taskId);
        updateStatusDisplay(taskStatus);
    } catch (error) {
        console.error('Failed to update task status:', error);
        showError('Failed to update task status: ' + error.message);
    }
}

async function runCurrentTask() {
    try {
        const taskId = document.getElementById('task-id').value;
        await runTask(taskId);
        showSuccess('Task started successfully');
        updateTaskStatus();
    } catch (error) {
        console.error('Failed to run task:', error);
        showError('Failed to run task: ' + error.message);
    }
}

async function deleteCurrentTask() {
    if (!confirm('Are you sure you want to delete this task?')) {
        return;
    }
    
    try {
        const taskId = document.getElementById('task-id').value;
        await deleteTask(taskId);
        window.location.href = '/tasks';
    } catch (error) {
        console.error('Failed to delete task:', error);
        showError('Failed to delete task: ' + error.message);
    }
} 