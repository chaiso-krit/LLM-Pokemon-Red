#!/usr/bin/env python3
"""
Main Launcher for Pokémon Red AI Player
Launches game and server socket with support for multiple LLM providers
"""
import os
import sys
import time
import subprocess
import argparse
from dotenv import load_dotenv
from config_loader import load_config, create_default_config

def setup_directories():
    """Set up required directories"""
    # Get the project root directory
    project_root = os.path.dirname(os.path.abspath(__file__))
    
    # Create the screenshots directory
    screenshots_dir = os.path.join(project_root, "data", "screenshots")
    comparison_dir = os.path.join(screenshots_dir, "comparison")
    os.makedirs(screenshots_dir, exist_ok=True)
    os.makedirs(comparison_dir, exist_ok=True)
    
    # Create an empty notepad.txt if it doesn't exist
    notepad_path = os.path.join(project_root, "notepad.txt")
    if not os.path.exists(notepad_path):
        with open(notepad_path, "w") as f:
            f.write("# Pokémon Red Game AI Notepad\n")
            f.write("I am playing Pokémon Red. I need to record important information here.\n\n")
    
    print(f"Created directory: {screenshots_dir}")
    print(f"Created directory: {comparison_dir}")
    print(f"Screenshot path: {os.path.join(screenshots_dir, 'screenshot.png')}")
    print(f"Notepad path: {notepad_path}")
    print("Directory setup complete!")

def check_env_file():
    """Verify .env file exists and contains required variables"""
    if not os.path.exists('.env'):
        print("Warning: .env file not found. Creating a template...")
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
    
    # Load environment variables
    load_dotenv()
    
    # Check for API keys based on selected provider
    provider = os.environ.get('DEFAULT_LLM_PROVIDER', 'gemini').lower()
    
    if provider == 'gemini' and not os.environ.get('GEMINI_API_KEY'):
        print("Warning: GEMINI_API_KEY not found in .env file")
        return False
    elif provider == 'openai' and not os.environ.get('OPENAI_API_KEY'):
        print("Warning: OPENAI_API_KEY not found in .env file")
        return False
    elif provider == 'anthropic' and not os.environ.get('ANTHROPIC_API_KEY'):
        print("Warning: ANTHROPIC_API_KEY not found in .env file")
        return False
    
    return True

def test_provider(provider_name=None):
    """Test if the provider is working correctly"""
    if not provider_name:
        provider_name = os.environ.get('DEFAULT_LLM_PROVIDER', 'gemini')
    
    print(f"Testing {provider_name} provider...")
    result = subprocess.run(
        [sys.executable, "llm_provider.py", "--provider", provider_name, 
         "--prompt", "Say 'WORKING' if you can receive this message."],
        capture_output=True,
        text=True
    )
    
    if "WORKING" in result.stdout:
        print(f"✅ {provider_name.upper()} provider test successful!")
        return True
    else:
        print(f"❌ {provider_name.upper()} provider test failed!")
        print(f"Error: {result.stderr}")
        return False

def main():
    """Main function to launch all components"""
    parser = argparse.ArgumentParser(description="Launch Pokémon Red AI Player")
    parser.add_argument("--config", default="config.json", help="Path to config file")
    parser.add_argument("--rom", default="pokemon-red.gb", help="Path to Pokémon ROM file")
    parser.add_argument("--emulator", default="/Applications/mGBA.app/Contents/MacOS/mGBA", 
                       help="Path to emulator executable")
    parser.add_argument("--provider", choices=["gemini", "openai", "anthropic"], 
                       help="Override the LLM provider to use")
    parser.add_argument("--test-only", action="store_true", 
                       help="Only test the provider without starting the game")
    args = parser.parse_args()
    
    # Setup directories
    setup_directories()
    
    # Check environment variables
    if not check_env_file():
        print("Please edit the .env file with appropriate API keys")
        if not args.test_only:
            return 1
    
    # Create default config if it doesn't exist
    if not os.path.exists(args.config):
        print(f"Config file {args.config} not found. Creating default config...")
        if not create_default_config(args.config):
            print("Failed to create config file")
            return 1
    
    # Override provider if specified
    if args.provider:
        os.environ['DEFAULT_LLM_PROVIDER'] = args.provider
        print(f"Using {args.provider} as LLM provider (overridden by command line)")
    
    # Load config
    config = load_config(args.config)
    if not config:
        print("Failed to load configuration")
        return 1
    
    provider_name = config.get('llm_provider', 'gemini')
    print(f"Using {provider_name} as LLM provider")
    
    # Test provider
    provider_working = test_provider(provider_name)
    
    if args.test_only:
        return 0 if provider_working else 1
    
    if not provider_working:
        print("Provider test failed. Would you like to continue anyway? (y/n)")
        response = input().lower()
        if response != 'y':
            return 1
    
    # Check if ROM file exists
    if not os.path.exists(args.rom):
        print(f"Error: ROM file {args.rom} not found.")
        print("Please provide a valid path to the Pokémon Red ROM file.")
        return 1
    
    # Start the controller in background
    print(f"Starting Python controller with {provider_name}...")
    controller_process = subprocess.Popen(
        [sys.executable, "controller.py", "--config", args.config],
        stdout=subprocess.PIPE, 
        stderr=subprocess.PIPE
    )
    
    # Give the controller a moment to start
    time.sleep(2)
    
    # Start the emulator with the ROM
    print("Starting emulator...")
    print("IMPORTANT: Once mGBA opens, go to Tools > Scripting... and load the script from 'script.lua'")
    emulator_command = [
        args.emulator,
        args.rom
    ]
    
    try:
        emulator_process = subprocess.Popen(emulator_command)
        
        # Print controller output in real-time
        def print_output(stream, prefix):
            for line in iter(stream.readline, b''):
                print(f"{prefix}: {line.decode().strip()}")
                
        from threading import Thread
        Thread(target=print_output, args=(controller_process.stdout, "Controller")).daemon = True
        Thread(target=print_output, args=(controller_process.stderr, "Controller Error")).daemon = True
        
        # Wait for the emulator to finish
        emulator_process.wait()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        # Clean up processes
        print("Terminating controller...")
        controller_process.terminate()
        
        try:
            controller_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            controller_process.kill()
        
        print("All processes terminated.")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())