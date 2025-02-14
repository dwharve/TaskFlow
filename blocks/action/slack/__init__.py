import requests
from typing import Dict, Any
from blocks.base import ActionBlock
import json
import logging

logger = logging.getLogger(__name__)

class Slack(ActionBlock):
    """Block for sending messages to Slack"""
    
    @property
    def name(self) -> str:
        return 'Slack'
    
    @property
    def version(self) -> str:
        return '1.0'
    
    @property
    def description(self) -> str:
        return 'Sends messages to Slack channels or users using webhooks'
    
    @property
    def parameters(self) -> Dict[str, Dict[str, Any]]:
        return {
            'webhook_url': {
                'type': 'string',
                'required': True,
                'description': 'Slack Webhook URL (from Slack App configuration)'
            },
            'message_template': {
                'type': 'string',
                'required': True,
                'description': 'Message template with {{field}} placeholders and Slack markdown',
                'default': '''*New Item: {{title}}*
> {{description}}

Posted on: {{posted_on}}
<{{url}}|View Original>'''
            },
            'username': {
                'type': 'string',
                'required': False,
                'description': 'Custom bot username to display',
                'default': 'Web Scraper Bot'
            },
            'icon_emoji': {
                'type': 'string',
                'required': False,
                'description': 'Emoji to use as bot icon (e.g., :robot_face:)',
                'default': ':spider_web:'
            },
            'mention_users': {
                'type': 'string',
                'required': False,
                'description': 'Comma-separated list of users to mention (e.g., @user1,@user2)',
                'default': ''
            }
        }

    def _replace_placeholders(self, template: str, data: Dict[str, Any]) -> str:
        """Replace {{field}} placeholders with actual values"""
        result = template
        for key, value in data.items():
            placeholder = f'{{{{{key}}}}}'
            if isinstance(value, (dict, list)):
                value = json.dumps(value, indent=2)
            result = result.replace(placeholder, str(value))
        return result

    async def execute(self, item: Dict[str, Any], parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Send a message to Slack based on the input item
        
        Args:
            item: Dictionary containing the item data
            parameters: Dictionary containing webhook URL and message template
            
        Returns:
            Dictionary containing the result of the Slack send operation
        """
        try:
            # Validate required parameters
            if 'webhook_url' not in parameters:
                raise ValueError("Missing required parameter: webhook_url")
            if 'message_template' not in parameters:
                raise ValueError("Missing required parameter: message_template")

            # Handle list input by converting to dict
            if isinstance(item, list):
                item = {"items": item}
            elif not isinstance(item, dict):
                item = {"value": str(item)}

            # Only send if there are new items
            if not item.get('is_new', True):
                logger.info("Skipping Slack message for non-new item")
                return {
                    'success': True,
                    'message': 'Skipped sending (not a new item)',
                    'item': item
                }

            # Replace placeholders in message template
            try:
                message = self._replace_placeholders(parameters['message_template'], item)
            except Exception as e:
                logger.error(f"Error replacing placeholders: {str(e)}")
                logger.error(f"Template: {parameters['message_template']}")
                logger.error(f"Data: {item}")
                raise ValueError(f"Error formatting message: {str(e)}")

            # Add user mentions if specified
            mentions = parameters.get('mention_users', '').strip()
            if mentions:
                mentions = ' '.join(mention.strip() for mention in mentions.split(','))
                message = f"{mentions}\n{message}"

            # Prepare payload
            payload = {
                'text': message,
                'username': parameters.get('username', 'Web Scraper Bot'),
                'icon_emoji': parameters.get('icon_emoji', ':spider_web:'),
                'mrkdwn': True
            }

            # Send to Slack
            response = requests.post(
                parameters['webhook_url'],
                json=payload,
                headers={'Content-Type': 'application/json'}
            )
            response.raise_for_status()

            logger.info("Message sent to Slack successfully")
            return {
                'success': True,
                'message': 'Message sent to Slack successfully',
                'status_code': response.status_code,
                'item': item
            }

        except ValueError as e:
            error_msg = str(e)
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'item': item
            }
        except requests.exceptions.RequestException as e:
            error_msg = f"Failed to send message to Slack: {str(e)}"
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'item': item
            }
        except Exception as e:
            error_msg = f"Unexpected error sending to Slack: {str(e)}"
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'item': item
            } 