import importlib
import os
import pkgutil
from typing import Dict, List, Type, Optional
import logging

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
    
    async def execute_block_chain(self, task) -> Dict[str, List[Dict]]:
        """Execute a chain of blocks for a task
        
        Args:
            task: Task model instance containing block chain configuration
            
        Returns:
            Dictionary containing the results of each block in the chain
        """
        logger.info(f"Executing block chain for task {task.id}")
        results = {}
        
        # Execute input block
        input_block_class = self.get_block("input", task.input_block)
        if not input_block_class:
            error_msg = f"Input block {task.input_block} not found"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        logger.info(f"Executing input block: {task.input_block}")
        input_block = input_block_class()
        
        # Get parameters from the block itself
        block_params = {}
        for block in task.blocks:
            if block.type == 'input' and block.name == task.input_block:
                block_params = block.get_parameters()
                break
        
        results["input"] = await input_block.collect(
            task.target_url,
            block_params
        )
        logger.debug(f"Input block results: {len(results['input'])} items")
        
        # Initialize processing and action results
        results["processing"] = {}
        results["action"] = {}
        
        # Get current data to pass to next block
        current_data = results["input"]
        
        # Execute block chain
        block_chain = task.get_block_chain()
        logger.debug(f"Block chain: {block_chain}")
        
        # Group blocks by chain
        chains = []
        current_chain = []
        
        for block in block_chain:
            if block['type'] == 'action' and current_chain:
                current_chain.append(block)
                chains.append(current_chain)
                current_chain = []
            else:
                current_chain.append(block)
        
        if current_chain:
            chains.append(current_chain)
        
        logger.info(f"Found {len(chains)} processing chains")
        
        # Process each chain independently with the input data
        for chain_index, chain in enumerate(chains):
            logger.info(f"Processing chain {chain_index + 1}")
            chain_data = current_data.copy()
            
            for block_config in chain:
                block_type = block_config["type"]
                block_name = block_config["name"]
                logger.debug(f"Executing {block_type} block: {block_name}")
                
                block_class = self.get_block(block_type, block_name)
                if not block_class:
                    error_msg = f"{block_type.title()} block {block_name} not found"
                    logger.error(error_msg)
                    raise ValueError(error_msg)
                
                block = block_class()
                try:
                    if block_type == "processing":
                        # Add task_id to processing block parameters
                        block_params = block.get_parameters()
                        block_params['task_id'] = task.id
                        
                        # Processing blocks work on lists of items
                        chain_data = await block.process(
                            chain_data,
                            block_params
                        )
                        results["processing"][block_name] = chain_data
                        logger.debug(f"Processing block {block_name} results: {len(chain_data)} items")
                    elif block_type == "action":
                        # Action blocks work on individual items
                        action_results = []
                        for item in chain_data:
                            try:
                                result = await block.execute(
                                    item,
                                    block.get_parameters()
                                )
                                action_results.append(result)
                            except Exception as e:
                                logger.error(f"Error executing action block {block_name} for item: {str(e)}")
                                action_results.append({
                                    "error": str(e),
                                    "item": item
                                })
                        results["action"][block_name] = action_results
                        chain_data = action_results
                        logger.debug(f"Action block {block_name} results: {len(action_results)} items")
                except Exception as e:
                    error_msg = f"Error executing {block_type} block {block_name}: {str(e)}"
                    logger.error(error_msg, exc_info=True)
                    raise ValueError(error_msg)
        
        return results

# Global instance
manager = BlockManager() 