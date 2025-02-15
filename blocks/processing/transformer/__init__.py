import json
from typing import Dict, Any, List
from blocks.base import ProcessingBlock
import re

class JsonTransformer(ProcessingBlock):
    """Block for transforming JSON objects using templates"""
    
    @property
    def name(self) -> str:
        return 'JSON Transformer'
    
    @property
    def version(self) -> str:
        return '1.1'
    
    @property
    def description(self) -> str:
        return 'Transform JSON objects by mapping fields and using templates with {{field}} syntax'
    
    @property
    def parameters(self) -> Dict[str, Dict[str, Any]]:
        return {
            'template': {
                'type': 'string',
                'required': True,
                'description': 'JSON template with {{field}} placeholders. Example: {"message":"{{title}} posted on {{date}}"}'
            }
        }

    def _replace_placeholders(self, template: str, input_data: Dict[str, Any]) -> str:
        """Replace {{field}} placeholders with actual values
        
        Args:
            template: String containing placeholders
            input_data: Dictionary containing the input data
            
        Returns:
            String with placeholders replaced by values
        """
        def replace_match(match):
            field = match.group(1)  # Extract field name from {{field}}
            try:
                # Handle nested fields with dot notation
                value = input_data
                for key in field.split('.'):
                    value = value[key]
                return str(value)
            except (KeyError, TypeError):
                print(f"Warning: Field {field} not found in input data")
                return f"{{missing:{field}}}"
        
        # Replace all {{field}} occurrences
        pattern = r'\{\{([^}]+)\}\}'
        return re.sub(pattern, replace_match, template)

    async def process(self, data: List[Dict[str, Any]], parameters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Transform each item according to the template
        
        Args:
            data: List of dictionaries containing items to transform
            parameters: Dictionary containing the template
            
        Returns:
            List of transformed dictionaries
        """
        try:
            # Parse the template JSON
            template = json.loads(parameters['template'])
            template_str = json.dumps(template)
            
            # Transform each item
            transformed_items = []
            for item in data:
                # Replace placeholders in the template string
                result_str = self._replace_placeholders(template_str, item)
                
                try:
                    # Parse the result back into a dictionary
                    transformed = json.loads(result_str)
                    transformed_items.append(transformed)
                except json.JSONDecodeError as e:
                    print(f"Error parsing transformed JSON: {e}")
                    # If parsing fails, return the raw string in a simple object
                    transformed_items.append({"error": "Invalid JSON", "raw": result_str})
            
            return transformed_items
            
        except json.JSONDecodeError as e:
            print(f"Error parsing template JSON: {e}")
            return [{"error": "Invalid template"} for _ in data]
        except Exception as e:
            print(f"Unexpected error: {e}")
            return [{"error": str(e)} for _ in data] 