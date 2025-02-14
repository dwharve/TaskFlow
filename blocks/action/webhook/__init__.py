import requests
from typing import Dict, Any
from blocks.base import ActionBlock
import json

class Webhook(ActionBlock):
    """Block for calling webhooks with item data"""
    
    @property
    def name(self) -> str:
        return 'Webhook'
    
    @property
    def version(self) -> str:
        return '1.0'
    
    @property
    def description(self) -> str:
        return 'Calls a webhook URL with item data'
    
    @property
    def parameters(self) -> Dict[str, Dict[str, Any]]:
        return {
            'webhook_url': {
                'type': 'string',
                'required': True,
                'description': 'URL of the webhook to post the input data to'
            },
            'headers': {
                'type': 'string',
                'required': False,
                'description': 'JSON string of headers to include in the request',
                'default': '{}'
            }
        }

    async def execute(self, item: Dict[str, Any], parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the webhook call for a single item
        
        Args:
            item: Dictionary containing the item data
            parameters: Dictionary containing webhook parameters
            
        Returns:
            Dictionary containing the result of the webhook call
        """
        try:
            # Make the webhook call
            response = requests.request(
                method='POST',
                url=parameters['webhook_url'],
                json=item,
                headers=json.loads(parameters.get('headers', '{}'))
            )
            
            # Return result
            return {
                'status_code': response.status_code,
                'success': response.ok,
                'response': response.text,
                'item': item
            }
            
        except Exception as e:
            return {
                'status_code': None,
                'success': False,
                'error': str(e),
                'item': item
            } 