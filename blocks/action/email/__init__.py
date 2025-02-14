import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any
from blocks.base import ActionBlock
import json
import os
import logging

logger = logging.getLogger(__name__)

class Email(ActionBlock):
    """Block for sending emails based on input data"""
    
    @property
    def name(self) -> str:
        return 'Email'
    
    @property
    def version(self) -> str:
        return '1.0'
    
    @property
    def description(self) -> str:
        return 'Sends emails using input data with configurable templates and SMTP settings'
    
    @property
    def parameters(self) -> Dict[str, Dict[str, Any]]:
        return {
            'smtp_host': {
                'type': 'string',
                'required': True,
                'description': 'SMTP server hostname',
                'default': 'smtp.gmail.com'
            },
            'smtp_port': {
                'type': 'integer',
                'required': True,
                'description': 'SMTP server port',
                'default': 587
            },
            'smtp_username': {
                'type': 'string',
                'required': True,
                'description': 'SMTP username/email'
            },
            'smtp_password': {
                'type': 'string',
                'required': True,
                'description': 'SMTP password or app-specific password'
            },
            'from_email': {
                'type': 'string',
                'required': True,
                'description': 'Sender email address'
            },
            'to_email': {
                'type': 'string',
                'required': True,
                'description': 'Recipient email address(es), comma-separated'
            },
            'subject_template': {
                'type': 'string',
                'required': True,
                'description': 'Email subject template with {{field}} placeholders',
                'default': 'New Item: {{title}}'
            },
            'body_template': {
                'type': 'string',
                'required': True,
                'description': 'Email body template (HTML) with {{field}} placeholders',
                'default': '''<h2>{{title}}</h2>
<p>{{description}}</p>
<hr>
<p><small>Sent by Web Scraper</small></p>
'''
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
        """Send an email based on the input item
        
        Args:
            item: Dictionary containing the item data
            parameters: Dictionary containing SMTP and template parameters
            
        Returns:
            Dictionary containing the result of the email send operation
        """
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['From'] = parameters['from_email']
            msg['To'] = parameters['to_email']
            
            # Replace placeholders in subject and body
            subject = self._replace_placeholders(parameters['subject_template'], item)
            body = self._replace_placeholders(parameters['body_template'], item)
            
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'html'))
            
            # Only send if there are new items
            if item.get('is_new', True):
                # Connect to SMTP server
                with smtplib.SMTP(parameters['smtp_host'], parameters['smtp_port']) as server:
                    server.starttls()
                    server.login(parameters['smtp_username'], parameters['smtp_password'])
                    
                    # Send email
                    server.send_message(msg)
                    
                    logger.info(f"Email sent successfully: {subject}")
                    return {
                        'success': True,
                        'message': 'Email sent successfully',
                        'subject': subject,
                        'item': item
                    }
            else:
                logger.info(f"Skipping email for non-new item: {subject}")
                return {
                    'success': True,
                    'message': 'Skipped sending (not a new item)',
                    'subject': subject,
                    'item': item
                }
                
        except Exception as e:
            error_msg = f"Failed to send email: {str(e)}"
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'item': item
            } 