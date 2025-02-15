import requests
from typing import Dict, Any, List
import json
import logging
from jinja2 import Template
from blocks.base import ProcessingBlock

# Set up logging
logger = logging.getLogger(__name__)

class JsonEnricher(ProcessingBlock):
    """Block for enriching data by fetching JSON from templated URLs"""
    
    @property
    def name(self) -> str:
        return 'JSON Enricher'
    
    @property
    def version(self) -> str:
        return '1.0'
    
    @property
    def description(self) -> str:
        return 'Enriches data by fetching JSON from templated URLs using input data'
    
    @property
    def parameters(self) -> Dict[str, Dict[str, Any]]:
        return {
            'url_template': {
                'type': 'string',
                'required': True,
                'description': 'URL template with Jinja2 variables (e.g., "https://api.example.com/{{ id }}")'
            },
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
            'body_template': {
                'type': 'string',
                'required': False,
                'description': 'JSON template string for POST request body with Jinja2 variables',
                'default': '{}'
            },
            'json_path': {
                'type': 'string',
                'required': False,
                'description': 'Dot-notation path to extract specific data from JSON response',
                'default': ''
            },
            'merge_strategy': {
                'type': 'string',
                'required': False,
                'description': 'How to merge enriched data: "merge" (update existing), "append" (add new field)',
                'default': 'merge'
            },
            'target_field': {
                'type': 'string',
                'required': False,
                'description': 'Field name to store enriched data when using append strategy',
                'default': 'enriched_data'
            }
        }

    async def process(self, data: List[Dict[str, Any]], parameters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Process the input data by enriching it with JSON from templated URLs
        
        Args:
            data: List of dictionaries containing the input data
            parameters: Dictionary of parameter values
            
        Returns:
            List of dictionaries containing the enriched data
        """
        try:
            # Parse parameters
            url_template = Template(parameters['url_template'])
            method = parameters.get('method', 'GET').upper()
            merge_strategy = parameters.get('merge_strategy', 'merge')
            target_field = parameters.get('target_field', 'enriched_data')
            
            try:
                headers_str = parameters.get('headers', '{}').replace("'", '"')
                headers = json.loads(headers_str)
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing headers JSON: {str(e)}")
                headers = {}
            
            body_template_str = parameters.get('body_template', '{}')
            body_template = Template(body_template_str)
            
            json_path = parameters.get('json_path', '')
            
            # Add default headers for JSON
            if 'Content-Type' not in headers:
                headers['Content-Type'] = 'application/json'
            if 'Accept' not in headers:
                headers['Accept'] = 'application/json'
            
            enriched_data = []
            
            for item in data:
                try:
                    # Render URL template with item data
                    url = url_template.render(**item)
                    logger.debug(f"Rendered URL: {url}")
                    
                    # Render body template if needed
                    if method == 'POST':
                        try:
                            body_str = body_template.render(**item)
                            body = json.loads(body_str)
                        except (json.JSONDecodeError, Exception) as e:
                            logger.error(f"Error rendering/parsing body template: {str(e)}")
                            body = {}
                    
                    # Make the request
                    if method == 'POST':
                        response = requests.post(url, headers=headers, json=body)
                    else:
                        response = requests.get(url, headers=headers)
                    
                    response.raise_for_status()
                    
                    # Parse response
                    enrichment_data = response.json()
                    
                    # Extract data using json_path if specified
                    if json_path:
                        for key in json_path.split('.'):
                            if key:
                                enrichment_data = enrichment_data.get(key, {})
                    
                    # Merge or append enriched data
                    if merge_strategy == 'merge':
                        if isinstance(enrichment_data, dict):
                            enriched_item = {**item, **enrichment_data}
                        else:
                            logger.warning(f"Enrichment data is not a dictionary, using original item")
                            enriched_item = item
                    else:  # append strategy
                        enriched_item = item.copy()
                        enriched_item[target_field] = enrichment_data
                    
                    enriched_data.append(enriched_item)
                    
                except requests.exceptions.RequestException as e:
                    logger.error(f"Error fetching enrichment data: {str(e)}")
                    enriched_data.append(item)  # Keep original item on error
                except Exception as e:
                    logger.error(f"Error processing item: {str(e)}", exc_info=True)
                    enriched_data.append(item)  # Keep original item on error
            
            return enriched_data
            
        except Exception as e:
            logger.error(f"Unexpected error in process method: {str(e)}", exc_info=True)
            return data  # Return original data on error 