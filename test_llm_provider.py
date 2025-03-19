#!/usr/bin/env python3
"""
Utility to test LLM providers.
"""

import os
import sys
import json
import argparse
from PIL import Image
from llm_provider import get_llm_provider


def load_config(config_path):
    """Load and parse the JSON configuration file."""
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        # Expand environment variables in the config
        for provider in config.get("providers", {}):
            for key, value in config["providers"][provider].items():
                if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                    env_var = value[2:-1]  # Extract env variable name
                    config["providers"][provider][key] = os.getenv(env_var, "")

        return config
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"Error loading config file: {e}")
        sys.exit(1)


def test_llm_provider(config, test_image_path=None, prompt=None):
    """Test a configured LLM provider."""
    llm_provider = get_llm_provider(config)
    if not llm_provider:
        print(f"Error: Could not initialize LLM provider '{config.get('llm_provider', 'unknown')}'")
        sys.exit(1)

    provider_name = llm_provider.get_provider_name()
    model_name = llm_provider.get_model_name()
    print(f"Testing LLM Provider: {provider_name}")
    print(f"Model: {model_name}")

    # Use default prompt if none provided
    if not prompt:
        prompt = (f"""
You are {provider_name}, an AI assistant. Please analyze this test request.

1. Confirm that you can understand this message
2. Introduce yourself in exactly one sentence
3. List 3 things you could help with in a Pokémon game

Respond in this exact format:
RESULT: [Your confirmation message]
INTRO: [Your one-sentence introduction]
SKILLS: [List of 3 Pokémon-related skills]
        """)

    images = []
    if test_image_path and os.path.exists(test_image_path):
        try:
            images.append(Image.open(test_image_path))
            print(f"Testing with image: {test_image_path}")
        except Exception as e:
            print(f"Error loading image: {e}")
            sys.exit(1)

    print("\nSending request to LLM...")
    try:
        response = llm_provider.generate_content(prompt, images)
        print("\n----- RESPONSE -----")
        print(response)
        print("----- END RESPONSE -----\n")
        print(f"Successfully received response from {provider_name}!")
        return True
    except Exception as e:
        print(f"Error: Failed to get response from {provider_name}: {e}")
        return False


def main():
    """Main function to parse arguments and run the test."""
    parser = argparse.ArgumentParser(description="Test LLM providers for the Pokémon AI project")
    parser.add_argument("--config", "-c", default="config.json", help="Path to the configuration file")
    parser.add_argument("--image", "-i", help="Path to a test image file (optional)")
    parser.add_argument("--prompt", "-p", help="Custom test prompt (optional)")
    
    args = parser.parse_args()
    config = load_config(args.config)
    success = test_llm_provider(config, args.image, args.prompt)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
