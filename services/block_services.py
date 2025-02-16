from typing import Any, Dict, Optional, Tuple, Union

from models import Block, BlockConnection
from blocks.manager import manager

class BlockValidationService:
    """Service for validating blocks and their connections"""
    
    @staticmethod
    def validate_parameters(
        block_name: str,
        block_type: str,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate and convert block parameters
        
        Args:
            block_name: Name of the block
            block_type: Type of block (input, processing, or action)
            parameters: Dictionary of parameter values
            
        Returns:
            Dictionary of validated and converted parameters
            
        Raises:
            ValueError: If required parameters are missing or invalid
        """
        block_class = manager.get_block(block_type, block_name)
        if not block_class:
            raise ValueError(f"{block_type.title()} block {block_name} not found")
        
        block = block_class()
        validated_params = {}
        block_params = block.parameters
        
        for name, config in block_params.items():
            if name in parameters:
                try:
                    validated_params[name] = BlockValidationService._convert_parameter_value(
                        parameters[name], config['type'])
                except (ValueError, TypeError) as e:
                    raise ValueError(f"Invalid value for parameter {name}: {str(e)}")
            elif config.get('required', False):
                raise ValueError(f"Required parameter {name} is missing")
            elif 'default' in config:
                validated_params[name] = config['default']
        
        return validated_params
    
    @staticmethod
    def _convert_parameter_value(value: str, param_type: str) -> Union[str, int, float, bool]:
        """Convert parameter value to the correct type
        
        Args:
            value: Value to convert
            param_type: Target type ('integer', 'float', 'boolean', or 'string')
            
        Returns:
            Converted value
            
        Raises:
            ValueError: If value cannot be converted to target type
        """
        if param_type == 'integer':
            return int(value)
        elif param_type == 'float':
            return float(value)
        elif param_type == 'boolean':
            return value.lower() == 'true'
        return value
    
    @staticmethod
    def validate_connection(source_block: Block, target_block: Block) -> bool:
        """Validate if two blocks can be connected
        
        Args:
            source_block: Source block
            target_block: Target block
            
        Returns:
            True if connection is valid, False otherwise
        """
        # Input blocks can only connect to processing or action blocks
        if source_block.type == 'input':
            return target_block.type in ['processing', 'action']
        
        # Processing blocks can only connect to processing or action blocks
        if source_block.type == 'processing':
            return target_block.type in ['processing', 'action']
        
        # Action blocks cannot have outgoing connections
        if source_block.type == 'action':
            return False
        
        return True

class BlockProcessor:
    """Service for processing block data"""
    
    @staticmethod
    def process_blocks(
        task: 'Task',  # Forward reference to avoid circular import
        blocks_data: Dict[str, Any],
        session: Any,
        existing_blocks: Optional[Dict[Tuple[str, str], Block]] = None
    ) -> Tuple[Dict[str, Block], list]:
        """Process block data for a task
        
        Args:
            task: Task instance
            blocks_data: Dictionary containing block data
            session: Database session
            existing_blocks: Optional dictionary of existing blocks
            
        Returns:
            Tuple of (dictionary of processed blocks, list of errors)
        """
        blocks = {}
        errors = []
        used_blocks = set()
        
        for block_data in blocks_data['blocks']:
            try:
                block_key = (block_data['name'], block_data['type'])
                
                if existing_blocks and block_key in existing_blocks:
                    # Update existing block
                    block = existing_blocks[block_key]
                    block.display_name = block_data.get('display_name')
                    block.position_x = block_data.get('position_x', 0)
                    block.position_y = block_data.get('position_y', 0)
                    used_blocks.add(block_key)
                else:
                    # Create new block
                    block = Block(
                        task_id=task.id,
                        name=block_data['name'],
                        type=block_data['type'],
                        display_name=block_data.get('display_name'),
                        position_x=block_data.get('position_x', 0),
                        position_y=block_data.get('position_y', 0)
                    )
                    session.add(block)
                
                # Validate and set parameters
                if 'parameters' in block_data:
                    try:
                        block_params = BlockValidationService.validate_parameters(
                            block.name, block.type, block_data['parameters'])
                        block.set_parameters(block_params)
                    except ValueError as e:
                        errors.append(str(e))
                        continue
                
                session.flush()
                blocks[block_data['id']] = block
                
            except Exception as e:
                errors.append(f"Error processing block {block_data.get('name')}: {str(e)}")
        
        # Remove unused blocks if updating
        if existing_blocks:
            for block_key, block in existing_blocks.items():
                if block_key not in used_blocks:
                    session.delete(block)
        
        return blocks, errors
    
    @staticmethod
    def process_connections(
        blocks_data: Dict[str, Any],
        blocks: Dict[str, Block],
        session: Any
    ) -> list:
        """Process block connections
        
        Args:
            blocks_data: Dictionary containing connection data
            blocks: Dictionary of processed blocks
            session: Database session
            
        Returns:
            List of errors encountered during processing
        """
        errors = []
        blocks_list = list(blocks.values())
        
        # Delete existing connections if updating
        for block in blocks_list:
            for conn in block.inputs:
                session.delete(conn)
        
        # Process new connections
        for conn_data in blocks_data['connections']:
            try:
                source_index = int(conn_data['source'])
                target_index = int(conn_data['target'])
                
                if not (0 <= source_index < len(blocks_list) and 0 <= target_index < len(blocks_list)):
                    error_msg = f"Invalid connection indices: source={source_index}, target={target_index}"
                    errors.append(error_msg)
                    continue
                
                source_block = blocks_list[source_index]
                target_block = blocks_list[target_index]
                
                if not BlockValidationService.validate_connection(source_block, target_block):
                    error_msg = f"Invalid connection between {source_block.type} block and {target_block.type} block"
                    errors.append(error_msg)
                    continue
                
                conn = BlockConnection(
                    source_block_id=source_block.id,
                    target_block_id=target_block.id,
                    input_name=conn_data.get('input_name')
                )
                session.add(conn)
                
            except (ValueError, KeyError) as e:
                errors.append(f"Error processing connection: {str(e)}")
        
        return errors 