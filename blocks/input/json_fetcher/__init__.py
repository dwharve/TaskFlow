import requests
from typing import Dict, Any, List, Optional
import json
import logging
from blocks.base import InputBlock

# Set up logging
logger = logging.getLogger(__name__)

class JsonFetcher(InputBlock):
    """Block for fetching JSON data from a URL"""
    
    @property
    def name(self) -> str:
        return 'JSON Fetcher'
    
    @property
    def version(self) -> str:
        return '1.0'
    
    @property
    def description(self) -> str:
        return 'Fetches JSON data from a URL with configurable headers and request method'
    
    @property
    def parameters(self) -> Dict[str, Dict[str, Any]]:
        return {
            'method': {
                'type': 'string',
                'required': False,
                'description': 'HTTP method to use (GET or POST)',
                'default': 'GET'
            },
            'headers': {
                'type': 'string',
                'required': False,
                'description': 'JSON string of headers to include in the request (e.g., {"Authorization": "Bearer token"})',
                'default': '{}'
            },
            'post_data': {
                'type': 'string',
                'required': False,
                'description': 'JSON string of data to send in POST request body',
                'default': '{}'
            },
            'json_path': {
                'type': 'string',
                'required': False,
                'description': 'Dot-notation path to extract specific data from JSON response (e.g., "data.items" or leave empty for entire response)',
                'default': ''
            }
        }

    async def collect(self, url: str, parameters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Collect JSON data from the given URL
        
        Args:
            url: The URL to fetch JSON data from
            parameters: Dictionary containing request parameters
            
        Returns:
            List of dictionaries containing the JSON data
        """
        try:
            # Log input parameters
            logger.debug(f"Fetching JSON from URL: {url}")
            logger.debug(f"Parameters: {parameters}")
            
            # Parse parameters
            method = parameters.get('method', 'GET').upper()
            
            try:
                # Convert single quotes to double quotes for JSON parsing
                headers_str = parameters.get('headers', '{}').replace("'", '"')
                headers = json.loads(headers_str)
                logger.debug(f"Parsed headers: {headers}")
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing headers JSON: {str(e)}")
                logger.error(f"Headers string: {parameters.get('headers', '{}')}")
                headers = {}
            
            try:
                post_data = json.loads(parameters.get('post_data', '{}'))
                logger.debug(f"Parsed post data: {post_data}")
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing post data JSON: {str(e)}")
                logger.error(f"Post data string: {parameters.get('post_data', '{}')}")
                post_data = {}
            
            json_path = parameters.get('json_path', '')
            
            # Add default headers for JSON
            if 'Content-Type' not in headers:
                headers['Content-Type'] = 'application/json'
            if 'Accept' not in headers:
                headers['Accept'] = 'application/json'
            
            logger.debug(f"Making {method} request to {url}")
            logger.debug(f"Headers: {headers}")
            if method == 'POST':
                logger.debug(f"Post data: {post_data}")
            
            # Make the request
            if method == 'POST':
                response = requests.post(url, headers=headers, json=post_data)
            else:
                response = requests.get(url, headers=headers)
            
            response.raise_for_status()
            
            # Log response details
            logger.debug(f"Response status: {response.status_code}")
            logger.debug(f"Response content type: {response.headers.get('content-type', 'unknown')}")
            logger.debug(f"Response text: {response.text[:1000]}...")  # Log first 1000 chars
            
            try:
                data = response.json()
                logger.debug(f"Successfully parsed response JSON")
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing response JSON: {str(e)}")
                logger.error(f"Response content: {response.text}")
                raise
            
            # Extract data using json_path if specified
            if json_path:
                logger.debug(f"Extracting data using path: {json_path}")
                for key in json_path.split('.'):
                    if key:
                        data = data.get(key, {})
                        logger.debug(f"After extracting '{key}': {type(data)}")
            
            # Ensure we return a list of dictionaries
            if isinstance(data, dict):
                data = [data]
            elif not isinstance(data, list):
                data = []
            
            logger.debug(f"Returning {len(data)} items")
            return data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching JSON data: {str(e)}")
            return []
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing JSON: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}", exc_info=True)
            return [] 