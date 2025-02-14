from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

class BaseBlock(ABC):
    """Base class for all blocks"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of the block"""
        pass
    
    @property
    @abstractmethod
    def version(self) -> str:
        """Return the version of the block"""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Return a description of the block"""
        pass
    
    @property
    @abstractmethod
    def block_type(self) -> str:
        """Return the type of block (input, processing, or action)"""
        pass
    
    @property
    @abstractmethod
    def parameters(self) -> Dict[str, Dict[str, Any]]:
        """Return a dictionary of parameters required by the block
        
        Format:
        {
            "parameter_name": {
                "type": "string|int|float|boolean",
                "required": True|False,
                "description": "Parameter description",
                "default": default_value  # Optional
            }
        }
        """
        pass

class InputBlock(BaseBlock):
    """Base class for input blocks (formerly scraping plugins)"""
    
    @property
    def block_type(self) -> str:
        return "input"
    
    @property
    def target_url(self) -> Optional[str]:
        """Return the fixed target URL for this block, if any.
        If None, the user can specify any URL.
        """
        return None
    
    @abstractmethod
    async def collect(self, url: str, parameters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Collect data from the given source
        
        Args:
            url: The URL or source identifier to collect from
            parameters: Dictionary of parameter values
            
        Returns:
            List of dictionaries containing the collected data
        """
        pass

class ProcessingBlock(BaseBlock):
    """Base class for processing blocks"""
    
    @property
    def block_type(self) -> str:
        return "processing"
    
    @abstractmethod
    async def process(self, data: List[Dict[str, Any]], parameters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Process the input data
        
        Args:
            data: List of dictionaries containing the input data
            parameters: Dictionary of parameter values
            
        Returns:
            List of dictionaries containing the processed data
        """
        pass

class ActionBlock(BaseBlock):
    """Base class for action blocks that handle individual items"""
    
    @property
    def block_type(self) -> str:
        return "action"
    
    @abstractmethod
    async def execute(self, item: Dict[str, Any], parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an action for a single item
        
        Args:
            item: Dictionary containing the item data to process
            parameters: Dictionary of parameter values
            
        Returns:
            Dictionary containing the result of the action
        """
        pass 