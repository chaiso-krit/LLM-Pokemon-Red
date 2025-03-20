#!/usr/bin/env python3
import os
import time
import threading
import PIL.Image
import argparse
import json
from typing import Dict, Any, Optional

# Import from your existing modules
from pokemon_logger import PokemonLogger
from config_loader import load_config
from google_controller import GeminiPokemonController  # Your actual controller class
from twitch_chat_client import TwitchChatClient

class TwitchEnabledPokemonController(GeminiPokemonController):
    """Pokemon controller enhanced with Twitch chat integration."""
    
    def __init__(self, config_path='config.json'):
        # Initialize the parent controller
        super().__init__(config_path)
        
        # Load Twitch config
        self.twitch_config = self._load_twitch_config()
        
        # Initialize Twitch client if enabled
        self.twitch_client = None
        self.chat_update_interval = self.twitch_config.get('chat_update_interval', 30)  # seconds
        self.last_chat_update = 0
        
        # Path for storing latest chat (separate from notepad)
        self.latest_chat_path = os.path.join(
            os.path.dirname(self.config.get('notepad_path', 'data/notepad.md')),
            'latest_chat.md'
        )
        
        if self.twitch_config.get('enabled', False):
            self._setup_twitch_client()
    
    def _load_twitch_config(self) -> Dict[str, Any]:
        """Load Twitch configuration from the config file."""
        # Default configuration
        default_config = {
            'enabled': False,
            'username': 'ai_plays_pokemon',
            'oauth_token': 'oauth:your_token_here',
            'channel': 'your_channel',
            'chat_update_interval': 30,  # seconds
            'max_chat_history': 50,
            'suggestions_per_update': 3,
            'log_file': 'data/twitch_chat.log'
        }
        
        # Try to load from config file
        try:
            if not hasattr(self, 'config') or not self.config:
                self.config = load_config(self.config_path)
            
            twitch_config = self.config.get('twitch', {})
            
            # Merge with defaults
            for key, value in default_config.items():
                if key not in twitch_config:
                    twitch_config[key] = value
            
            return twitch_config
            
        except Exception as e:
            self.logger.error(f"Error loading Twitch config: {e}")
            return default_config
    
    def _setup_twitch_client(self):
        """Set up the Twitch chat client."""
        try:
            # Ensure log directory exists
            log_file = self.twitch_config.get('log_file')
            if log_file:
                os.makedirs(os.path.dirname(log_file), exist_ok=True)
            
            # Create the client
            self.twitch_client = TwitchChatClient(
                username=self.twitch_config['username'],
                oauth_token=self.twitch_config['oauth_token'],
                channel=self.twitch_config['channel'],
                max_chat_history=self.twitch_config['max_chat_history'],
                log_file=log_file
            )
            
            # Start the client
            if self.twitch_client.start():
                self.logger.success(f"Connected to Twitch chat: {self.twitch_config['channel']}")
            else:
                self.logger.error("Failed to connect to Twitch chat")
                self.twitch_client = None
                
        except Exception as e:
            self.logger.error(f"Error setting up Twitch client: {e}")
            self.twitch_client = None
    
    def cleanup(self):
        """Enhanced cleanup that also stops the Twitch client."""
        if self.twitch_client:
            try:
                self.twitch_client.stop()
                self.logger.info("Twitch chat client stopped")
            except:
                pass
            self.twitch_client = None
        
        # Call parent cleanup
        super().cleanup()
    
    def update_latest_chat(self):
        """Update the latest chat file with current messages (completely replacing contents)."""
        if not self.twitch_client:
            return
        
        current_time = time.time()
        # Only update periodically
        if current_time - self.last_chat_update < self.chat_update_interval:
            return
            
        try:
            # Reset the timer regardless of whether we have new messages
            self.last_chat_update = current_time
            
            # Get recent chat messages (not just new ones)
            recent_messages = self.twitch_client.get_recent_messages(count=10)
            
            if recent_messages:
                # Format the messages
                formatted = "# Latest Twitch Chat Messages\n\n"
                for msg in recent_messages:
                    timestamp = msg['timestamp'].strftime("%H:%M:%S")
                    formatted += f"[{timestamp}] {msg['username']}: {msg['message']}\n"
                
                # Write to the latest chat file (completely replacing contents)
                with open(self.latest_chat_path, 'w') as f:
                    f.write(formatted)
                
                self.logger.info("Updated latest chat file with current messages")
            else:
                # If no messages, still create/update the file but with a placeholder
                with open(self.latest_chat_path, 'w') as f:
                    f.write("# Latest Twitch Chat Messages\n\nNo recent messages.\n")
                
        except Exception as e:
            self.logger.error(f"Error updating latest chat file: {e}")
    
    def read_latest_chat(self):
        """Read the latest chat messages from the dedicated file."""
        try:
            if os.path.exists(self.latest_chat_path):
                with open(self.latest_chat_path, 'r') as f:
                    return f.read()
            else:
                return "No recent chat messages."
        except Exception as e:
            self.logger.error(f"Error reading latest chat: {e}")
            return "Error reading latest chat messages."
    
    def enhance_prompt(self, prompt: str) -> str:
        """Enhance the LLM prompt with Twitch-specific instructions."""
        if not self.twitch_client:
            return prompt
        
        # Add Twitch-specific instructions to help the AI understand chat messages
        twitch_instructions = """
        ## Twitch Chat Integration:
        - The "Latest Twitch Chat Messages" section contains CURRENT messages from real viewers watching your gameplay
        - These are RECENT suggestions that override any older advice in the notepad
        - Consider these messages as helpful advice about what to do RIGHT NOW
        - Pay close attention to chat when you're stuck or facing challenges
        - Viewers might suggest both immediate actions (button presses) and longer-term goals
        - Chat could provide valuable game knowledge about locations, mechanics, or objectives
        - Use your judgment but give serious consideration to these LATEST chat suggestions
        """
        
        # Insert these instructions at an appropriate point in the prompt
        if "## Navigation Rules:" in prompt:
            prompt_parts = prompt.split("## Navigation Rules:")
            prompt = prompt_parts[0] + "## Navigation Rules:" + prompt_parts[1]
            prompt = prompt.replace(
                "## Navigation Rules:", 
                "## Navigation Rules:" + twitch_instructions
            )
        else:
            # If we can't find the Navigation Rules section, just append to the end
            prompt += twitch_instructions
        
        return prompt
    
    def process_screenshot(self, screenshot_path=None):
        """Override to update latest chat before processing screenshot."""
        # Update latest chat file first
        self.update_latest_chat()
        
        # Get the current_time
        current_time = time.time()
        
        if current_time - self.last_decision_time < self.decision_cooldown:
            return None
            
        try:
            notepad_content = self.read_notepad()
            latest_chat = self.read_latest_chat()
            recent_actions = self.get_recent_actions_text()
            path_to_use = screenshot_path if screenshot_path else self.screenshot_path
            
            if not os.path.exists(path_to_use):
                self.logger.error(f"Screenshot not found at {path_to_use}")
                return None
            
            # Load the original image
            original_image = PIL.Image.open(path_to_use)
            
            # Create the base prompt
            prompt = f"""
            You are playing Pokémon Red, you are the character with the red hat. Look at this screenshot and choose ONE button to press.
            
            ## Controls:
            - A: To talk to people or interact with objects or advance text (NOT for entering/exiting buildings)
            - B: To cancel or go back
            - UP, DOWN, LEFT, RIGHT: To move your character (use these to enter/exit buildings)
            - START: To open the main menu
            - SELECT: Rarely used special function

            ## Navigation Rules:
            - If you've pressed the same button 3+ times with no change, TRY A DIFFERENT DIRECTION
            - You must be DIRECTLY ON TOP of exits (red mats, doors, stairs) to use them
            - Light gray or black space is NOT walkable - it's a wall/boundary you need to use the exits (red mats, doors, stairs)
            - The character must directly face objects to interact with them
            - When you enter a new area or discover something important, UPDATE THE NOTEPAD using the update_notepad function to record what you learned, where you are and your current goal.
            
            {recent_actions}
            
            ## Twitch Chat (Latest Messages):
            {latest_chat}
            
            ## Long-term Memory (Game State):
            {notepad_content}

            IMPORTANT: After each significant change (entering new area, talking to someone, finding items), use the update_notepad function to record what you learned or where you are.
            
            Choose the appropriate button for this situation and use the press_button function to execute it.
            When you're in a room, house, or cave you must look for the exits via the ladders, stairs, or red mats on the floor and use them by walking directly over them.
            """
            
            # Enhance the prompt with Twitch instructions
            prompt = self.enhance_prompt(prompt)
            
            images = [original_image]
            self.logger.section(f"Requesting decision from Gemini")
            
            response, tool_calls, text = self.gemini.call_with_tools(
                message=prompt,
                tools=self.tools,
                images=images
            )
            
            print(f"Gemini Text Response: {text}")
            
            button_code = None
            
            for call in tool_calls:
                if call.name == "update_notepad":
                    content = call.arguments.get("content", "")
                    if content:
                        self.update_notepad(content)
                        print(f"Updated notepad with: {content[:50]}...")
                
                elif call.name == "press_button":
                    button = call.arguments.get("button", "").upper()
                    button_map = {
                        "A": 0, "B": 1, "SELECT": 2, "START": 3,
                        "RIGHT": 4, "LEFT": 5, "UP": 6, "DOWN": 7,
                        "R": 8, "L": 9
                    }
                    
                    if button in button_map:
                        button_code = button_map[button]
                        self.logger.success(f"Tool used button: {button}")
                        
                        # Modified: Store timestamp, button, and full reasoning text
                        timestamp = time.strftime("%H:%M:%S")
                        self.recent_actions.append((timestamp, button, text))
                        
                        self.logger.ai_action(button, button_code)
                        self.last_decision_time = current_time
                        return {'button': button_code}
            
            if button_code is None:
                self.logger.warning("No press_button tool call found!")
                return None
            
        except Exception as e:
            self.logger.error(f"Error processing screenshot: {e}")
            if self.debug_mode:
                import traceback
                self.logger.debug(traceback.format_exc())
        return None

    def start(self):
        """Enhanced start method with Twitch info."""
        if self.twitch_client:
            self.logger.header(f"Starting Pokémon Game Controller with Gemini + Twitch Chat Integration")
            self.logger.info(f"Connected to Twitch channel: {self.twitch_config['channel']}")
            
            # Announce in chat that AI is now playing
            self.twitch_client.send_message("AI Pokémon player is now live! Use chat to help guide the AI when it gets stuck.")
        else:
            self.logger.header(f"Starting Pokémon Game Controller with Gemini (Twitch integration disabled)")
        
        # Call the parent start method
        super().start()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Twitch-enabled Pokémon Game AI Controller")
    parser.add_argument("--config", "-c", default="config.json", help="Path to the configuration file")
    args = parser.parse_args()
    
    controller = TwitchEnabledPokemonController(args.config)
    try:
        controller.start()
    except KeyboardInterrupt:
        pass
    finally:
        controller.cleanup()