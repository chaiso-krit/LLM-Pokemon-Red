#!/usr/bin/env python3
"""
Configuration loader for Pokémon AI Player
Handles loading config from JSON and environment variables
"""

import os
import json
import re
from dotenv import load_dotenv

def load_config(config_path='config.json'):
    """
    Load configuration from JSON file and substitute environment variables
    
    Args:
        config_path (str): Path to the configuration JSON file
        
    Returns:
        dict: Configuration dictionary with environment variables substituted
    """
    # Load environment variables from .env file
    load_dotenv()
    
    # Read the config file
    try:
        with open(config_path, 'r') as f:
            config_str = f.read()
    except Exception as e:
        print(f"Error reading config file {config_path}: {e}")
        return None
    
    # Replace environment variables in the config string
    def replace_env_vars(match):
        env_var = match.group(1)
        value = os.environ.get(env_var, '')
        if not value:
            print(f"Warning: Environment variable {env_var} not found")
        return value
    
    # Replace ${VAR_NAME} with the value from environment variables
    config_str = re.sub(r'\${([A-Za-z0-9_]+)}', replace_env_vars, config_str)
    
    # Parse the JSON
    try:
        config = json.loads(config_str)
    except json.JSONDecodeError as e:
        print(f"Error parsing config JSON: {e}")
        return None
    
    # Validate API keys exist for the selected provider
    provider = config.get('llm_provider', '')
    provider_config = config.get('providers', {}).get(provider, {})
    
    if provider and provider_config:
        api_key = provider_config.get('api_key', '')
        if not api_key:
            print(f"Warning: No API key found for provider '{provider}'")
    
    # Make paths absolute
    if 'notepad_path' in config and not os.path.isabs(config['notepad_path']):
        config['notepad_path'] = os.path.abspath(config['notepad_path'])
        
    if 'screenshot_path' in config and not os.path.isabs(config['screenshot_path']):
        config['screenshot_path'] = os.path.abspath(config['screenshot_path'])
    
    return config

def create_default_config(output_path='config.json'):
    """
    Create a default configuration file from the template
    
    Args:
        output_path (str): Path to save the configuration file
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        template_path = 'config.template.json'
        if not os.path.exists(template_path):
            print("Template file config.template.json not found")
            return False
        
        # Load and process the template
        config = load_config(template_path)
        if not config:
            print("Failed to process the template")
            return False
        
        # Write the processed config
        with open(output_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        print(f"Created config file: {output_path}")
        return True
    except Exception as e:
        print(f"Error creating config file: {e}")
        return False

if __name__ == "__main__":
    # If run directly, create a default config
    create_default_config()