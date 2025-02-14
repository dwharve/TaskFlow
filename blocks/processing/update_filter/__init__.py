import json
import hashlib
from typing import Dict, Any, List
from datetime import datetime
from blocks.base import ProcessingBlock
from models import db, ItemState
import logging

# Set up logging
logger = logging.getLogger(__name__)

class UpdateFilter(ProcessingBlock):
    """Block for monitoring and filtering items based on whether they've been seen before"""
    
    @property
    def name(self) -> str:
        return 'Update Filter'
    
    @property
    def version(self) -> str:
        return '1.0'
    
    @property
    def description(self) -> str:
        return 'Monitors items and only passes through new ones that have not been seen before'
    
    @property
    def parameters(self) -> Dict[str, Dict[str, Any]]:
        return {
            'exclude_fields': {
                'type': 'string',
                'required': False,
                'description': 'Comma-separated list of fields to exclude when calculating uniqueness',
                'default': ''
            }
        }

    def _get_item_hash(self, item: Dict[str, Any], exclude_fields: List[str]) -> str:
        """Generate a unique hash for an item, excluding specified fields
        
        Args:
            item: Dictionary containing the item data
            exclude_fields: List of fields to exclude from the hash
            
        Returns:
            String hash that uniquely identifies the item content
        """
        try:
            # Create a new dict excluding the specified fields
            key_data = {
                key: str(value)
                for key, value in item.items()
                if key not in exclude_fields
            }
            # Convert to JSON string with sorted keys for consistent serialization
            item_str = json.dumps(key_data, sort_keys=True)
            # Generate SHA-256 hash of the string
            return hashlib.sha256(item_str.encode()).hexdigest()
        except Exception as e:
            logger.error(f"Error generating hash for item: {item}")
            logger.error(f"Error details: {str(e)}")
            # Return a fallback hash based on string representation
            return hashlib.sha256(str(item).encode()).hexdigest()

    async def process(self, data: List[Dict[str, Any]], parameters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Process items and only pass through new ones
        
        Args:
            data: List of dictionaries containing items to process
            parameters: Dictionary containing processing parameters
            
        Returns:
            List of dictionaries containing only new items
        """
        exclude_fields = [f.strip() for f in parameters.get('exclude_fields', '').split(',') if f.strip()]
        task_id = parameters.get('task_id')
        
        if not task_id:
            logger.warning("task_id not provided, cannot track item state")
            return data
        
        logger.info(f"Processing {len(data)} items for task {task_id}")
        
        # Process each item
        new_items = []
        for item in data:
            # Create hash from all fields except excluded ones
            item_hash = self._get_item_hash(item, exclude_fields)
            
            # Check if this item has been seen before
            existing_state = ItemState.query.filter_by(
                task_id=task_id,
                item_hash=item_hash
            ).first()
            
            # Only include new items in the output
            if existing_state is None:
                logger.debug(f"New item found with hash {item_hash}")
                new_items.append(item)
                
                # Create state record for the new item
                state = ItemState(
                    task_id=task_id,
                    item_hash=item_hash
                )
                db.session.add(state)
            else:
                logger.debug(f"Skipping previously seen item with hash {item_hash}")
        
        # Commit all new states
        try:
            db.session.commit()
            logger.info(f"Found {len(new_items)} new items out of {len(data)} total items")
        except Exception as e:
            logger.error(f"Error saving state to database: {e}")
            db.session.rollback()
        
        return new_items 