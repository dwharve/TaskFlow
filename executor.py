import logging
from typing import Dict, List, Any, Set
from collections import defaultdict
import asyncio
from datetime import datetime

from models import Task, Block, db
from blocks.manager import manager

logger = logging.getLogger(__name__)

class TaskExecutor:
    """Executes tasks by running blocks in the correct order based on their connections"""
    
    def __init__(self):
        self._running_tasks = {}
    
    async def execute_task(self, task: Task):
        """Execute a task by running all its blocks in the correct order
        
        Args:
            task: Task to execute
        """
        logger.info(f"Executing task {task.id}")
        
        try:
            # Build execution graph
            blocks_by_id = {block.id: block for block in task.blocks}
            input_blocks = []
            processing_blocks = []
            action_blocks = []
            
            # Group blocks by type
            for block in task.blocks:
                if block.type == 'input':
                    input_blocks.append(block)
                elif block.type == 'processing':
                    processing_blocks.append(block)
                elif block.type == 'action':
                    action_blocks.append(block)
            
            # Build dependency graph
            dependencies = defaultdict(set)  # block_id -> set of block_ids it depends on
            dependents = defaultdict(set)    # block_id -> set of block_ids that depend on it
            
            for block in task.blocks:
                for conn in block.inputs:
                    dependencies[block.id].add(conn.source_block_id)
                    dependents[conn.source_block_id].add(block.id)
            
            # Execute blocks in order
            executed_blocks = set()
            block_outputs = {}
            
            # First execute all input blocks (they have no dependencies)
            logger.info(f"Executing {len(input_blocks)} input blocks")
            for block in input_blocks:
                block_instance = manager.get_block("input", block.name)()
                try:
                    # Get parameters and extract URL if present
                    block_params = block.get_parameters()
                    url = block_params.pop('url', None) if block_params else None
                    
                    # Use URL from parameters or let block handle default
                    result = await block_instance.collect(url, block_params)
                    block.set_data(result)
                    block_outputs[block.id] = result
                    executed_blocks.add(block.id)
                except Exception as e:
                    logger.error(f"Error executing input block {block.name}: {str(e)}")
                    raise
            
            # Execute processing blocks in dependency order
            while processing_blocks:
                # Find blocks whose dependencies are all satisfied
                ready_blocks = [
                    block for block in processing_blocks
                    if dependencies[block.id].issubset(executed_blocks)
                ]
                
                if not ready_blocks and processing_blocks:
                    # We have blocks but none are ready - must be a cycle
                    raise ValueError("Cycle detected in processing block dependencies")
                
                logger.info(f"Executing {len(ready_blocks)} processing blocks")
                for block in ready_blocks:
                    processing_blocks.remove(block)
                    
                    # Get input data from dependencies
                    input_data = []
                    for conn in block.inputs:
                        input_data.extend(block_outputs[conn.source_block_id])
                    
                    # Execute block
                    block_instance = manager.get_block("processing", block.name)()
                    try:
                        block_params = block.get_parameters()
                        block_params['task_id'] = task.id
                        result = await block_instance.process(input_data, block_params)
                        block.set_data(result)
                        block_outputs[block.id] = result
                        executed_blocks.add(block.id)
                    except Exception as e:
                        logger.error(f"Error executing processing block {block.name}: {str(e)}")
                        raise
            
            # Finally execute action blocks
            logger.info(f"Executing {len(action_blocks)} action blocks")
            for block in action_blocks:
                # Get input data from dependencies
                input_data = []
                for conn in block.inputs:
                    input_data.extend(block_outputs[conn.source_block_id])
                
                # Execute block
                block_instance = manager.get_block("action", block.name)()
                try:
                    # Action blocks work on individual items
                    action_results = []
                    for item in input_data:
                        try:
                            result = await block_instance.execute(item, block.get_parameters())
                            action_results.append(result)
                        except Exception as e:
                            logger.error(f"Error executing action block {block.name} for item: {str(e)}")
                            action_results.append({
                                "error": str(e),
                                "item": item
                            })
                    block.set_data(action_results)
                except Exception as e:
                    logger.error(f"Error executing action block {block.name}: {str(e)}")
                    raise
            
            # Update task status
            task.last_run = datetime.utcnow()
            task.update_status('completed')
            db.session.commit()
            
        except Exception as e:
            logger.error(f"Error executing task {task.id}: {str(e)}")
            task.update_status('failed')
            db.session.commit()
            raise

# Create global executor instance
executor = TaskExecutor() 