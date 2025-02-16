import importlib
import os
import pkgutil
from typing import Dict, List, Type, Optional, Any
import logging
from datetime import datetime

from blocks.base import BaseBlock, InputBlock, ProcessingBlock, ActionBlock

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class BlockManager:
    """Manager for loading and accessing blocks"""
    
    def __init__(self):
        self._blocks: Dict[str, Dict[str, Type[BaseBlock]]] = {
            "input": {},
            "processing": {},
            "action": {}
        }
        self._load_blocks()
    
    def _load_blocks(self):
        """Load all available blocks from the blocks directory"""
        blocks_dir = os.path.dirname(__file__)
        logger.debug(f"Loading blocks from directory: {blocks_dir}")
        
        # Load input blocks
        self._load_blocks_from_dir(os.path.join(blocks_dir, 'input'), InputBlock, "input")
        
        # Load processing blocks
        self._load_blocks_from_dir(os.path.join(blocks_dir, 'processing'), ProcessingBlock, "processing")
        
        # Load action blocks
        self._load_blocks_from_dir(os.path.join(blocks_dir, 'action'), ActionBlock, "action")
        
        # Log loaded blocks
        logger.debug("Loaded blocks:")
        for block_type, blocks in self._blocks.items():
            logger.debug(f"{block_type}: {list(blocks.keys())}")
    
    def _load_blocks_from_dir(self, directory: str, base_class: Type[BaseBlock], block_type: str):
        """Load blocks from a directory
        
        Args:
            directory: Directory to load blocks from
            base_class: Base class that blocks should inherit from
            block_type: Type of block being loaded (input, processing, or action)
        """
        if not os.path.exists(directory):
            logger.warning(f"Directory does not exist: {directory}")
            return
            
        logger.debug(f"Loading {block_type} blocks from {directory}")
            
        # Get all subdirectories (potential block packages)
        for item in os.listdir(directory):
            item_path = os.path.join(directory, item)
            if not os.path.isdir(item_path) or item.startswith('__'):
                continue
                
            logger.debug(f"Found potential block package: {item}")
                
            # Try to import the block module
            try:
                module = importlib.import_module(f"blocks.{block_type}.{item}")
                logger.debug(f"Successfully imported module: blocks.{block_type}.{item}")
                
                # Look for a class that inherits from the base class
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    try:
                        if (isinstance(attr, type) and 
                            issubclass(attr, base_class) and 
                            attr != base_class):
                            # Create an instance to verify it works
                            block = attr()
                            logger.debug(f"Found block class: {attr_name}")
                            # Store using the directory name as the key
                            self._blocks[block_type][item] = attr
                            break
                    except TypeError:
                        continue
                        
            except (ImportError, AttributeError) as e:
                logger.error(f"Failed to load block from {item_path}: {str(e)}")
    
    def get_block(self, block_type: str, name: str) -> Optional[Type[BaseBlock]]:
        """Get a block by type and name
        
        Args:
            block_type: Type of block (input, processing, or action)
            name: Name of the block
            
        Returns:
            Block class if found, None otherwise
        """
        return self._blocks.get(block_type, {}).get(name)
    
    def get_blocks_by_type(self, block_type: str) -> Dict[str, Type[BaseBlock]]:
        """Get all blocks of a given type
        
        Args:
            block_type: Type of block (input, processing, or action)
            
        Returns:
            Dictionary of block name to block class
        """
        return self._blocks.get(block_type, {})
    
    def get_all_blocks(self) -> Dict[str, Dict[str, Type[BaseBlock]]]:
        """Get all available blocks
        
        Returns:
            Dictionary of block types to dictionaries of block names and classes
        """
        return self._blocks
    
    async def _handle_block_execution(self, block_instance, input_data, block_params, block_name, block_type):
        """Helper function to handle block execution with consistent error handling
        
        Args:
            block_instance: Instance of the block to execute
            input_data: Input data for the block
            block_params: Parameters for the block
            block_name: Name of the block
            block_type: Type of the block
            
        Returns:
            Tuple of (success, result)
            success: Boolean indicating if execution was successful
            result: Result data or error information
        """
        try:
            if block_type == "action":
                result = await block_instance.execute(input_data, block_params)
            else:
                result = await block_instance.process(input_data, block_params)
            return True, result
        except Exception as e:
            error_msg = f"Error executing {block_type} block {block_name}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, {
                "error": str(e),
                "input": input_data,
                "block_name": block_name,
                "block_type": block_type,
                "timestamp": datetime.utcnow().isoformat()
            }

    async def execute_block_chain(self, task) -> Dict[str, Dict[str, List[Any]]]:
        """Execute a chain of blocks for a task
        
        Args:
            task: Task to execute
            
        Returns:
            Dictionary of results by block type and name
        """
        results = {
            "input": {},
            "processing": {},
            "action": {}
        }
        block_outputs = {}
        
        for block in task.blocks:
            logger.info(f"Executing {block.type} block {block.name}")
            block_instance = self.get_block(block.type, block.name)()
            block_params = block.get_parameters()
            block_params['task_id'] = task.id
            
            try:
                if block.type == "input":
                    success, result = await self._handle_block_execution(
                        block_instance, None, block_params, block.name, block.type
                    )
                    if success:
                        results["input"][block.name] = result
                        block_outputs[block.id] = result
                    else:
                        raise ValueError(f"Input block {block.name} failed: {result['error']}")
                
                elif block.type == "processing":
                    # Get input data from dependencies
                    input_data = []
                    for conn in block.inputs:
                        if conn.source_block_id in block_outputs:
                            input_data.extend(block_outputs[conn.source_block_id])
                    
                    success, result = await self._handle_block_execution(
                        block_instance, input_data, block_params, block.name, block.type
                    )
                    if success:
                        results["processing"][block.name] = result
                        block_outputs[block.id] = result
                    else:
                        raise ValueError(f"Processing block {block.name} failed: {result['error']}")
                
                elif block.type == "action":
                    # Get input data from dependencies
                    input_data = []
                    for conn in block.inputs:
                        if conn.source_block_id in block_outputs:
                            input_data.extend(block_outputs[conn.source_block_id])
                    
                    # Execute action block for each input item
                    action_results = []
                    for item in input_data:
                        success, result = await self._handle_block_execution(
                            block_instance, item, block_params, block.name, block.type
                        )
                        action_results.append(result if success else {"error": result["error"], "item": item})
                    
                    results["action"][block.name] = action_results
                    block_outputs[block.id] = action_results
                
                logger.debug(f"{block.type.title()} block {block.name} results: {len(block_outputs[block.id])} items")
                
            except Exception as e:
                error_msg = f"Error executing {block.type} block {block.name}: {str(e)}"
                logger.error(error_msg, exc_info=True)
                raise ValueError(error_msg)
        
        return results

# Global instance
manager = BlockManager() 