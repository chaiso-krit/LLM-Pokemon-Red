#!/usr/bin/env python3
"""
Setup script for Pokémon Red AI Player
This script helps set up the environment and configuration
"""

import os
import sys
import argparse
from config_loader import create_default_config
import subprocess

def check_python_version():
    """Check if Python version is adequate"""
    min_version = (3, 8)
    current_version = sys.version_info[:2]
    
    if current_version < min_version:
        print(f"Error: Python {min_version[0]}.{min_version[1]} or higher is required")
        print(f"Your version: {current_version[0]}.{current_version[1]}")
        return False
    return True

def check_env_file():
    """Check if .env file exists"""
    if not os.path.exists('.env'):
        print("Creating default .env file...")
        with open('.env', 'w') as f:
            f.write("""# LLM API Keys
GEMINI_API_KEY=YOUR_GEMINI_API_KEY
OPENAI_API_KEY=YOUR_OPENAI_API_KEY
ANTHROPIC_API_KEY=YOUR_ANTHROPIC_API_KEY

# Default provider
DEFAULT_LLM_PROVIDER=gemini

# Model names
GEMINI_MODEL=gemini-2.0-flash
OPENAI_MODEL=gpt-4o
ANTHROPIC_MODEL=claude-3-sonnet-20240229
""")
        print("Created .env file. Please edit it to add your API keys.")
        return False
    return True

def install_dependencies():
    """Install required packages"""
    print("Installing dependencies...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("Dependencies installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error installing dependencies: {e}")
        return False

def create_directories():
    """Create necessary directories"""
    dirs = [
        "data/screenshots",
        "data/screenshots/comparison"
    ]
    
    for directory in dirs:
        os.makedirs(directory, exist_ok=True)
        print(f"Created directory: {directory}")
    
    return True

def setup_configuration():
    """Set up configuration files"""
    if not os.path.exists('config.json'):
        print("Creating default configuration...")
        if create_default_config():
            print("Configuration created successfully")
        else:
            print("Failed to create configuration")
            return False
    else:
        print("Configuration already exists")
    
    return True

def main():
    """Main setup function"""
    parser = argparse.ArgumentParser(description="Setup Pokémon Red AI Player")
    parser.add_argument("--force", "-f", action="store_true", help="Force setup even if already configured")
    args = parser.parse_args()
    
    print("=== Pokémon Red AI Player Setup ===")
    
    # Check Python version
    if not check_python_version():
        return False
    
    # Check/create .env file
    env_ok = check_env_file()
    
    # Install dependencies
    if not install_dependencies():
        return False
    
    # Create directories
    if not create_directories():
        return False
    
    # Setup configuration
    if not setup_configuration():
        return False
    
    print("\n=== Setup Complete ===")
    
    if not env_ok:
        print("\nIMPORTANT: Edit the .env file to add your API keys before running the controller")
    
    print("\nTo test your setup:")
    print("  python test_llm_provider.py")
    print("\nTo start the controller:")
    print("  python controller.py")
    
    return True

if __name__ == "__main__":
    sys.exit(0 if main() else 1)