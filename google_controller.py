#!/usr/bin/env python3
import os
import socket
import time
import threading
import PIL.Image
import signal
import sys
import atexit
import argparse
import json
from collections import deque
from typing import Dict, List, Any, Tuple

# Import from your existing modules
from pokemon_logger import PokemonLogger

# Import ollama instead of google.generativeai
from ollama import Client

import re

class Tool:
    """Simple class to define a tool for the LLM"""
    def __init__(self, name: str, description: str, parameters: List[Dict[str, Any]]):
        self.name = name
        self.description = description
        self.parameters = parameters
    
    def to_ollama_format(self) -> Dict[str, Any]:
        """Convert to Ollama's expected format (simple function definition for prompt)"""
        # Ollama's tool calling might require a specific schema; 
        # for now, we'll represent it as a string description.
        param_str = ", ".join([f"{p['name']}: {p['type']} ({p['description']})" for p in self.parameters])
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    p["name"]: {
                        "type": p["type"],
                        "description": p["description"]
                    } for p in self.parameters
                },
                "required": [p["name"] for p in self.parameters if p.get("required", False)]
            }
        }

class ToolCall:
    """Represents a tool call from the LLM"""
    def __init__(self, id: str, name: str, arguments: Dict[str, Any]):
        self.id = id
        self.name = name
        self.arguments = arguments

class GeminiClient: # Renamed to OllamaClient for clarity if this were a full refactor
    """Client specifically for communicating with Ollama"""
    def __init__(self, provider_config):
        self.api_key = provider_config.get("api_key", "") # Not directly used by ollama, but kept for compatibility
        self.model_name = provider_config.get("model_name")
        self.model_image_name = provider_config.get("model_image_name")
        self.max_tokens = provider_config.get("max_tokens", 1024) # Max tokens for Ollama output
        self.client_host = provider_config.get("host")
        self._setup_client()
    
    def _setup_client(self):
        """Set up the Ollama client (no explicit setup needed for ollama library)"""
        # No explicit setup like API key configuration needed for ollama client library
        # The model needs to be pulled and running via 'ollama run <model_name>'
        self.client = Client(
            host=self.client_host,
        )        
    
    def call_with_tools(self, message: str, tools: List[Tool], images: List[PIL.Image.Image] = None) -> Tuple[Any, List[ToolCall], str]:
        """
        Call Ollama with the given message and tools, optionally including images
        """
        provider_tools = [tool.to_ollama_format() for tool in tools]
        
        system_message = """
        You are playing Pokémon Yellow. Your job is to press buttons to control the game.
        
        IMPORTANT: After analyzing the screenshot, you MUST use the press_button function.
        You are REQUIRED to use the press_button function with every response.
        
        NEVER just say what button to press - ALWAYS use the press_button function to actually press it.
        """
        
        messages = [
            {"role": "system", "content": system_message},
            #{"role": "assistant", "content": "I understand. For every screenshot, I will use the press_button function to specify which button to press (A, B, UP, DOWN, etc.)."},
        ]
        
        # Prepare the user message with image(s) if present
        user_message_content = {"role": "user", "content":  f"{message}", "images": []}
    
        if images:
            for img in images:
                user_message_content["images"].append(img)
        
        messages.append(user_message_content)
        
        try:
            response = self.client.chat(
                model=self.model_name,
                messages=messages,
                # options={
                #     "num_predict": self.max_tokens,
                #     "temperature": 0.2,
                #     "top_p": 0.95,
                #     "top_k": 0
                # },
                #tools=provider_tools, # Pass tools directly here
            )
        except Exception as e:
            print(f"Error calling Ollama: {e}")
            import traceback
            print(traceback.format_exc())
            return None, [], ""
        
        return response, self._parse_tool_calls(response), self._extract_text(response)
    
    def call_with_images(self, message: str, images_path: List[str] = None) -> Tuple[Any, str]:
        """
        Call Ollama with the given message and images
        """
        
        system_message = """
        You are playing Pokémon Yellow.
        
        IMPORTANT: After analyzing the screenshot, you must describe important information that relevant to game.
        Only text about screenshot, not opinion or question.
        """
        
        messages = [
            {"role": "system", "content": system_message},
        ]
        
        # Prepare the user message with image(s) if present
        user_message_content = {"role": "user", "content":  f"Describe screenshot in detail", "images": []}
    
        if images_path:
            user_message_content["images"] = images_path
        
        messages.append(user_message_content)
        
        try:
            response = self.client.chat(
                model=self.model_image_name,
                messages=messages,
            )
        except Exception as e:
            print(f"Error calling Ollama: {e}")
            import traceback
            print(traceback.format_exc())
            return None, [], ""
        
        return response, self._extract_text(response)
    
    def _parse_tool_calls(self, response: Any) -> List[ToolCall]:
        """Parse tool calls from Ollama's response"""
        tool_calls = []

        #print(response)
        
        try:
            # Ollama's chat response for tool calls typically comes as content in JSON format
            # within the message, or sometimes as part of 'tool_calls' if the model supports it directly.
            # Assuming the tool call comes as a JSON object in the 'content' field for simplicity.
            
            if response and 'message' in response and 'tool_calls' in response['message']:
                for call_data in response['message']['tool_calls']:
                    if 'function' in call_data:
                        tool_calls.append(ToolCall(
                            id=call_data.get('id', f"call_{len(tool_calls)}"),
                            name=call_data['function'].get('name', ''),
                            arguments=call_data['function'].get('arguments', {})
                        ))
            elif response and 'message' in response and 'content' in response['message']:
                content_str = response['message']['content']
                # Try to parse content as JSON, expecting tool calls
                try:
                    parsed_content = json.loads(content_str)
                    if isinstance(parsed_content, dict) and 'tool_call' in parsed_content:
                        # Simple case: direct tool_call object
                        call_data = parsed_content['tool_call']
                        if 'name' in call_data and 'arguments' in call_data:
                            tool_calls.append(ToolCall(
                                id=f"call_{len(tool_calls)}",
                                name=call_data['name'],
                                arguments=call_data['arguments']
                            ))
                    elif isinstance(parsed_content, dict) and 'function_call' in parsed_content:
                        # Another common format for function calls
                        call_data = parsed_content['function_call']
                        if 'name' in call_data and 'arguments' in call_data:
                            tool_calls.append(ToolCall(
                                id=f"call_{len(tool_calls)}",
                                name=call_data['name'],
                                arguments=call_data['arguments']
                            ))
                except json.JSONDecodeError:
                    # Not a JSON tool call in content, proceed to extract text
                    pattern = r"press_button\((.*?)\)"
                    matches = re.findall(pattern, content_str)
                    if len(matches) == 1:
                        tool_calls.append(ToolCall(
                                id=f"call_{len(tool_calls)}",
                                name='press_button',
                                arguments={'button': matches[0]}
                            ))
                    else:
                        print("Error Parsing")
        except Exception as e:
            print(f"Error parsing Ollama tool calls: {e}")
            import traceback
            print(traceback.format_exc())
        
        for call in tool_calls:
            print(f"Tool call: {call.name}, args: {call.arguments}")
        
        return tool_calls
    
    def _extract_text(self, response: Any) -> str:
        """Extract text from the Ollama response"""
        try:
            if response and 'message' in response and 'content' in response['message']:
                return response['message']['content']
        except Exception as e:
            print(f"Error extracting text from Ollama response: {e}")
        return ""

class PokemonController:
    def __init__(self, config_path='config.json'):
        self._cleanup_done = False
        self._cleanup_lock = threading.Lock()
        
        # Load config directly from JSON file
        try:
            with open(config_path, 'r') as f:
                self.config = json.load(f)
        except Exception as e:
            print(f"Failed to load config from {config_path}: {e}")
            sys.exit(1)
        
        # Ensure paths are absolute
        if 'notepad_path' in self.config and not os.path.isabs(self.config['notepad_path']):
            self.config['notepad_path'] = os.path.abspath(self.config['notepad_path'])
            
        if 'screenshot_path' in self.config and not os.path.isabs(self.config['screenshot_path']):
            self.config['screenshot_path'] = os.path.abspath(self.config['screenshot_path'])
        
        provider_config = self.config["providers"]["ollama"] # Changed to ollama
        
        self.llm_client = GeminiClient( # This would ideally be OllamaClient
            provider_config=provider_config
        )
        
        self.server_socket = None
        self.tools = self._define_tools()
        
        self.notepad_path = self.config['notepad_path']
        self.screenshot_path = self.config['screenshot_path']
        self.current_client = None
        self.running = True
        self.decision_cooldown = self.config['decision_cooldown']
        self.client_threads = []
        self.debug_mode = self.config.get('debug_mode', False)
        
        # Game state tracking
        self.player_direction = "UNKNOWN"
        self.player_x = 0
        self.player_y = 0
        self.map_id = 0
        
        # Processing state flags
        self.is_processing = False
        self.emulator_ready = False
        
        # Modified: Store timestamp, button, full reasoning text, and position/direction
        self.recent_actions = deque(maxlen=10)
        
        os.makedirs(os.path.dirname(self.notepad_path), exist_ok=True)
        os.makedirs(os.path.dirname(self.screenshot_path), exist_ok=True)
        
        self.logger = PokemonLogger(debug_mode=self.debug_mode)
        self.initialize_notepad()
        
        self.logger.info("Controller initialized")
        self.logger.debug(f"Notepad path: {self.notepad_path}")
        self.logger.debug(f"Screenshot path: {self.screenshot_path}")
        
        self.setup_socket()
        
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        atexit.register(self.cleanup)

    def _define_tools(self) -> List[Tool]:
        """Define the tools needed for the Pokémon game controller"""
        press_button = Tool(
            name="press_button",
            description="Press a button on the Game Boy emulator to control the game",
            parameters=[{
                "name": "button",
                "type": "string",
                "description": "Button to press (A, B, START, SELECT, UP, DOWN, LEFT, RIGHT, R, L)",
                "required": True,
                "enum": ["A", "B", "SELECT", "START", "RIGHT", "LEFT", "UP", "DOWN", "R", "L"]
            }]
        )
        
        update_notepad = Tool(
            name="update_notepad",
            description="Update the AI's long-term memory with new information about the game state",
            parameters=[{
                "name": "content",
                "type": "string",
                "description": "Content to add to the notepad. Only include important information about game progress, objectives, or status.",
                "required": True
            }]
        )
        
        return [press_button, update_notepad]

    def setup_socket(self):
        """Set up the socket server"""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            try:
                self.server_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 60)
                self.server_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)
                self.server_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 6)
            except (AttributeError, OSError):
                self.logger.debug("TCP keepalive options not fully supported")
            
            try:
                self.server_socket.bind((self.config['host'], self.config['port']))
            except socket.error:
                self.logger.warning(f"Port {self.config['port']} in use. Attempting to free it...")
                os.system(f"lsof -ti:{self.config['port']} | xargs kill -9")
                time.sleep(1)
                self.server_socket.bind((self.config['host'], self.config['port']))
            
            self.server_socket.listen(1)
            self.server_socket.settimeout(1)
            self.logger.success(f"Socket server set up on {self.config['host']}:{self.config['port']}")
        except socket.error as e:
            self.logger.error(f"Socket setup error: {e}")
            sys.exit(1)

    def signal_handler(self, sig, frame):
        """Handle termination signals"""
        print(f"\nReceived signal {sig}. Shutting down server...")
        self.running = False
        self.cleanup()
        sys.exit(0)
        
    def cleanup(self):
        """Clean up resources"""
        with self._cleanup_lock:
            if self._cleanup_done:
                return
            self._cleanup_done = True
            
            self.logger.section("Cleaning up resources...")
            if self.current_client:
                try:
                    self.current_client.close()
                    self.current_client = None
                except:
                    pass
            if self.server_socket:
                try:
                    self.server_socket.close()
                    self.server_socket = None
                except:
                    pass
            self.logger.success("Cleanup complete")
            time.sleep(0.5)

    def initialize_notepad(self):
        """Initialize the notepad file with clear game objectives"""
        if not os.path.exists(self.notepad_path):
            os.makedirs(os.path.dirname(self.notepad_path), exist_ok=True)
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            with open(self.notepad_path, 'w') as f:
                f.write("# Pokémon Red Game Progress\n\n")
                f.write(f"Game started: {timestamp}\n\n")
                #f.write("## Current Objectives\n- Enter my name 'Gemini' and give my rival a name.\n\n")
                f.write("## Exit my house\n\n")
                f.write("## Current Objectives\n- Find Professor Oak to get first Pokémon\n- Start Pokémon journey\n\n")
                f.write("## Current Location\n- Starting in player's house in Pallet Town\n\n")
                f.write("## Game Progress\n- Just beginning the adventure\n\n")
                f.write("## Items\n- None yet\n\n")
                f.write("## Pokémon Team\n- None yet\n\n")

    def read_notepad(self):
        """Read the current notepad content"""
        try:
            with open(self.notepad_path, 'r') as f:
                return f.read()
        except Exception as e:
            print(f"Error reading notepad: {e}")
            return "Error reading notepad"

    def update_notepad(self, new_content):
        """Update the notepad"""
        try:
            current_content = self.read_notepad()
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            updated_content = current_content + f"\n## Update {timestamp}\n{new_content}\n"
            with open(self.notepad_path, 'w') as f:
                f.write(updated_content)
            self.logger.debug("Notepad updated")
            if len(updated_content) > 10000:
                self.summarize_notepad()
        except Exception as e:
            self.logger.error(f"Error updating notepad: {e}")

    def summarize_notepad(self):
        """Summarize the notepad when it gets too long"""
        try:
            self.logger.info("Notepad is getting large, summarizing...")
            notepad_content = self.read_notepad()
            summarize_prompt = """
            Please summarize the following game notes into a more concise format.
            Maintain these key sections:
            - Current Status
            - Game Progress
            - Important Items
            - Pokemon Team
            Remove redundant information while preserving all important game state details.
            Format the response as a well-structured markdown document.
            Here are the notes to summarize:
            """
            # For Ollama, we'll call without tools and expect a text response.
            response, _, text = self.llm_client.call_with_tools(
                message=summarize_prompt + notepad_content,
                tools=[]
            )
            if text:
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                summary = f"# Pokémon Game AI Notepad (Summarized)\n\n"
                summary += f"Last summarized: {timestamp}\n\n"
                summary += text
                with open(self.notepad_path, 'w') as f:
                    f.write(summary)
                self.logger.success("Notepad summarized successfully")
        except Exception as e:
            self.logger.error(f"Error summarizing notepad: {e}")

    def get_recent_actions_text(self):
        """Get formatted text of recent actions with reasoning and position/direction"""
        if not self.recent_actions:
            return "No recent actions."
        
        recent_actions_text = "## Short-term Memory (Recent Actions and Reasoning):\n"
        for i, (timestamp, button, reasoning, direction, x, y, map_id) in enumerate(self.recent_actions, 1):
            recent_actions_text += f"{i}. [{timestamp}] Pressed {button} while facing {direction} at position ({x}, {y}) on map {map_id}\n"
            recent_actions_text += f"   Reasoning: {reasoning.strip()}\n\n"
        return recent_actions_text

    def get_direction_guidance_text(self):
        """Generate guidance text about player orientation and interactions"""
        directions = {
            "UP": "north",
            "DOWN": "south", 
            "LEFT": "west",
            "RIGHT": "east"
        }
        
        facing_direction = directions.get(self.player_direction, self.player_direction)
        
        guidance = f"""
        ## Navigation Tips:
        - To INTERACT with objects or NPCs, you MUST be FACING them and then press A
        - Your current direction is {self.player_direction} (facing {facing_direction})
        - Your current position is (X={self.player_x}, Y={self.player_y}) on map {self.map_id}
        - If you need to face a different direction, press the appropriate directional button first
        - In buildings, look for exits via stairs, doors, or red mats and walk directly over them
        """
        
        return guidance

    def get_map_name(self, map_id):
        """Get map name from ID, with fallback for unknown maps"""
        # Pokémon Red/Blue map IDs (incomplete, add more as needed)
        map_names = {
            0: "Pallet Town",
            1: "Viridian City",
            2: "Pewter City",
            3: "Cerulean City",
            12: "Route 1",
            13: "Route 2",
            14: "Route 3",
            15: "Route 4",
            37: "Yellow's House 1F",
            38: "Yellow's House 2F",
            39: "Blue's House",
            40: "Oak's Lab",
            # Add more map IDs as you explore the game
        }
        
        return map_names.get(map_id, f"Unknown Area (Map ID: {map_id})")

    def process_screenshot(self, screenshot_path=None):
        """Process a screenshot with enhanced game state information"""
        if self.is_processing:
            self.logger.debug("Already processing a decision, skipping")
            return None
            
        self.is_processing = True
        try:
            notepad_content = self.read_notepad()
            recent_actions = self.get_recent_actions_text()
            #print(recent_actions)
            direction_guidance = self.get_direction_guidance_text()
            current_map = self.get_map_name(self.map_id)
            
            path_to_use = screenshot_path if screenshot_path else self.screenshot_path
            
            if not os.path.exists(path_to_use):
                self.logger.error(f"Screenshot not found at {path_to_use}")
                self.is_processing = False
                return None
            
            # Load and enhance the image
            original_image = PIL.Image.open(path_to_use)
            
            # Scale the image to 3x its original size for better detail recognition
            scale_factor = 3
            scaled_width = original_image.width * scale_factor
            scaled_height = original_image.height * scale_factor
            scaled_image = original_image.resize((scaled_width, scaled_height), PIL.Image.LANCZOS)
            
            # Enhance contrast for better visibility
            from PIL import ImageEnhance
            contrast_enhancer = ImageEnhance.Contrast(scaled_image)
            contrast_image = contrast_enhancer.enhance(1.5)  # Increase contrast by 50%
            
            # Enhance color saturation for better color visibility
            saturation_enhancer = ImageEnhance.Color(contrast_image)
            enhanced_image = saturation_enhancer.enhance(1.8)  # Increase saturation by 80%
            
            # Optionally enhance brightness slightly
            brightness_enhancer = ImageEnhance.Brightness(enhanced_image)
            final_image = brightness_enhancer.enhance(1.1)  # Increase brightness by 10%

            final_image.save(self.config["screenshot_process_path"])

            response, image_text = self.llm_client.call_with_images(
                message="Describe image in detail, without any function call. Do not give any location name, only describe the scene",
                images_path=[self.config["screenshot_process_path"]]
            )

            print(f"Screenshot Detail: {image_text}")
            
            prompt = f"""
            You are an AI playing Pokémon Yellow, you are the character with the red hat. Look at this screenshot and choose ONE button to press.
            
            ## Current Location
            You are in {current_map}
            Position: X={self.player_x}, Y={self.player_y}
            
            ## Current Direction
            You are facing: {self.player_direction}
            
            ## Controls:
            - A: To talk to people or interact with objects or advance text (NOT for entering/exiting buildings)
            - B: To cancel or go back
            - UP, DOWN, LEFT, RIGHT: To move your character (use these to enter/exit buildings)
            - START: To open the main menu
            - SELECT: Rarely used special function
            
            
            ## Name Entry Screen Guide:
            - The cursor is a BLACK TRIANGLE/POINTER (▶) on the left side of the currently selected letter
            - The letter that will be selected is the one the BLACK TRIANGLE is pointing to
            - To navigate to a different letter, use UP, DOWN, LEFT, RIGHT buttons
            - To enter a letter, press A when the cursor is pointing to that letter
            - The keyboard layout is as follows:
            ROW 1: A B C D E F G H I
            ROW 2: J K L M N O P Q R
            ROW 3: S T U V W X Y Z
            ROW 4: Special characters
            ROW 5: END (bottom right)

            ## URGENT WARNING: DO NOT PRESS A UNLESS YOU ARE ON THE CORRECT LETTER!
            
            ## Navigation Rules:
            - If you've pressed the same button 3+ times with no change also include A,B or the position no change , TRY A DIFFERENT DIRECTION OR ACTIONS
            - You must be DIRECTLY ON TOP of exits (red mats, doors, stairs) to use them
            - Light gray or black space is NOT walkable - it's a wall/boundary you need to use the exits (red mats, doors, stairs)
            - To INTERACT with objects or NPCs, you MUST be FACING them and then press A.
            - If the text box is shown, your character cannot move, you must press A.
            - When you enter a new area or discover something important, UPDATE THE NOTEPAD using the update_notepad function
            
            {recent_actions}
            
            {direction_guidance}
            
            ## Long-term Memory (Game State):
            {notepad_content}

            ## Screenshot Information
            {image_text}
            
            IMPORTANT: After each significant change (entering new area, talking to someone, finding items), use the update_notepad function to record what you learned or where you are.
            
            ## IMPORTANT INSTRUCTIONS:
            1. FIRST, give information about current situation and objectives.
            2. THEN, provide a BRIEF explanation of what you plan to do and why.
            3. FINALLY, use the press_button() function to execute your decision.

            IMPORTANT: You MUST use the press_button() function. Select which button to press (A, B, UP, DOWN, LEFT, RIGHT, START or SELECT).
            """
            
            self.logger.section(f"Requesting decision from LLM")
            
            response, tool_calls, text = self.llm_client.call_with_tools(
                message=prompt,
                tools=self.tools
            )
            
            print(f"LLM Text Response: {text}")
            
            button_code = None
            
            if tool_calls:
                for call in tool_calls:
                    if call.name == "update_notepad":
                        content = call.arguments.get("content", "")
                        if content:
                            self.update_notepad(content)
                            print(f"Updated notepad with: {content[:50]}...")
                    
                    elif call.name == "press_button":
                        button = call.arguments.get("button", "").upper()
                        button = button.strip().strip("'\"")
                        button_map = {
                            "A": 0, "B": 1, "SELECT": 2, "START": 3,
                            "RIGHT": 4, "LEFT": 5, "UP": 6, "DOWN": 7,
                            "R": 8, "L": 9
                        }
                        
                        if button in button_map:
                            button_code = button_map[button]
                            self.logger.success(f"Tool used button: {button}")
                            
                            # Store timestamp, button, reasoning, and position/direction
                            timestamp = time.strftime("%H:%M:%S")
                            #print(len(self.recent_actions))
                            self.recent_actions.append(
                                (timestamp, button, "", self.player_direction, 
                                self.player_x, self.player_y, self.map_id)
                            )
                            
                            self.logger.ai_action(button, button_code)
                            return {'button': button_code}
            
            if button_code is None:
                self.logger.warning("No press_button tool call found!")
                return None
            
        except Exception as e:
            self.logger.error(f"Error processing screenshot: {e}")
            if self.debug_mode:
                import traceback
                self.logger.debug(traceback.format_exc())
        finally:
            self.is_processing = False
        return None

    def handle_client(self, client_socket, client_address):
        """Handle communication with the emulator client"""
        self.logger.section(f"Connected to emulator at {client_address}")
        self.current_client = client_socket
        self.last_decision_time = 0  # Track the time of last decision
        
        self.logger.game_state("Waiting for game data...")
        
        while self.running:
            try:
                data = client_socket.recv(1024)
                if not data:
                    break
                
                message = data.decode('utf-8').strip()
                parts = message.split("||")
                
                if len(parts) >= 2:
                    message_type = parts[0]
                    content = parts[1:]  # Get all remaining parts
                    
                    # Handle the "ready" message from the emulator
                    if message_type == "ready":
                        self.logger.game_state("Emulator is ready for next command")
                        self.emulator_ready = True
                        
                        # Check if cooldown period has passed
                        current_time = time.time()
                        time_since_last_decision = current_time - self.last_decision_time
                        
                        if time_since_last_decision < self.decision_cooldown:
                            wait_time = self.decision_cooldown - time_since_last_decision
                            self.logger.debug(f"Waiting {wait_time:.2f}s for cooldown before next request")
                            time.sleep(wait_time)
                        
                        # Request a screenshot if we're not currently processing one
                        if not self.is_processing:
                            try:
                                self.logger.debug("Requesting screenshot from emulator")
                                client_socket.send(b'request_screenshot\n')
                            except Exception as e:
                                self.logger.error(f"Failed to request screenshot: {e}")
                    
                    # Handle the screenshot_with_state message type
                    elif message_type == "screenshot_with_state":
                        self.logger.game_state("Received new screenshot with game state from emulator")
                        
                        # Parse the content which now includes game state
                        if len(content) >= 5:  # Path, direction, x, y, mapId
                            screenshot_path = content[0]
                            self.player_direction = content[1]
                            self.player_x = int(content[2])
                            self.player_y = int(content[3])
                            self.map_id = int(content[4])
                            
                            self.logger.debug(f"Game State: Direction={self.player_direction}, " +
                                             f"Position=({self.player_x}, {self.player_y}), " +
                                             f"Map ID={self.map_id}")
                        
                            # Verify the file exists
                            if os.path.exists(screenshot_path):
                                # Process the screenshot with game state info
                                decision = self.process_screenshot(screenshot_path)
                                
                                if decision and decision.get('button') is not None:
                                    try:
                                        button_code = str(decision['button'])
                                        self.logger.debug(f"Sending button code to emulator: {button_code}")
                                        client_socket.send(button_code.encode('utf-8') + b'\n')
                                        self.logger.success("Button command sent to emulator")
                                        self.emulator_ready = False
                                        
                                        # Update the last decision time
                                        self.last_decision_time = time.time()
                                    except Exception as e:
                                        self.logger.error(f"Failed to send button command: {e}")
                                        break
                                else:
                                    # If no decision was made, we still need to respect the cooldown
                                    self.last_decision_time = time.time()
                                    
                                    # Request another screenshot after a small delay
                                    try:
                                        time.sleep(0.5)  # Small delay to avoid flooding
                                        client_socket.send(b'request_screenshot\n')
                                    except Exception as e:
                                        self.logger.error(f"Failed to request another screenshot: {e}")
                            else:
                                self.logger.error(f"Screenshot file not found at {screenshot_path}")
                
            except socket.error as e:
                if e.args[0] != socket.EWOULDBLOCK and str(e) != 'Resource temporarily unavailable':
                    self.logger.error(f"Socket error: {e}")
                    break
            except Exception as e:
                self.logger.error(f"Error handling client: {e}")
                if self.debug_mode:
                    import traceback
                    self.logger.debug(traceback.format_exc())
                if not self.running:
                    break
                continue
            
            # Add a small delay to avoid CPU spinning
            time.sleep(0.01)
        
        self.logger.section(f"Disconnected from emulator at {client_address}")
        self.current_client = None
        try:
            client_socket.close()
        except:
            pass

    def handle_client_connection(self, client_socket, client_address):
        """Wrapper around handle_client"""
        try:
            self.handle_client(client_socket, client_address)
        except Exception as e:
            self.logger.error(f"Client connection error: {e}")
        finally:
            if client_socket:
                try:
                    client_socket.close()
                except:
                    pass
            if self.current_client == client_socket:
                self.current_client = None

    def start(self):
        """Start the controller server"""
        self.logger.header(f"Starting Pokémon Game Controller")
        
        try:
            while self.running:
                try:
                    self.logger.section("Waiting for emulator connection...")
                    client_socket, client_address = self.server_socket.accept()
                    client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    try:
                        client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 60)
                        client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)
                        client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 6)
                    except (AttributeError, OSError):
                        pass
                    
                    client_socket.setblocking(0)
                    client_thread = threading.Thread(
                        target=self.handle_client_connection,
                        args=(client_socket, client_address)
                    )
                    client_thread.daemon = True
                    client_thread.start()
                    self.client_threads.append(client_thread)
                except socket.timeout:
                    continue
                except KeyboardInterrupt:
                    self.logger.section("Keyboard interrupt detected. Shutting down...")
                    break
                except Exception as e:
                    if self.running:
                        self.logger.error(f"Error in main loop: {e}")
                        if self.debug_mode:
                            import traceback
                            self.logger.debug(traceback.format_exc())
                        time.sleep(1)
        finally:
            self.running = False
            self.logger.section("Closing all client connections...")
            for t in self.client_threads:
                try:
                    t.join(timeout=1)
                except:
                    pass
            self.cleanup()
            self.logger.success("Server shut down cleanly")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pokémon Game AI Controller")
    parser.add_argument("--config", "-c", default="config.json", help="Path to the configuration file")
    args = parser.parse_args()
    
    controller = PokemonController(args.config)
    try:
        controller.start()
    except KeyboardInterrupt:
        pass
    finally:
        controller.cleanup()