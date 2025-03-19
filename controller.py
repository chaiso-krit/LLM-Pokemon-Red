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
import requests
import json
from enum import Enum
from typing import Dict, List, Any, Tuple, Deque
from collections import deque

# Import from your existing modules
from pokemon_logger import PokemonLogger
from config_loader import load_config

class Provider(str, Enum):
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    OPENAI = "openai"

class Tool:
    def __init__(self, name: str, description: str, parameters: List[Dict[str, Any]]):
        self.name = name
        self.description = description
        self.parameters = parameters
    
    def to_provider_format(self, provider: Provider) -> Dict[str, Any]:
        schema = {
            "type": "object",
            "properties": {
                p["name"]: {
                    "type": p["type"],
                    "description": p["description"]
                } for p in self.parameters
            },
            "required": [p["name"] for p in self.parameters if p.get("required", False)]
        }
        
        if provider == Provider.ANTHROPIC:
            return {
                "name": self.name,
                "description": self.description,
                "input_schema": schema
            }
        elif provider == Provider.GOOGLE:
            return {
                "name": self.name,
                "description": self.description,
                "parameters": schema
            }
        elif provider == Provider.OPENAI:
            return {
                "type": "function",
                "function": {
                    "name": self.name,
                    "description": self.description,
                    "parameters": schema
                }
            }

class ToolCall:
    def __init__(self, id: str, name: str, arguments: Dict[str, Any]):
        self.id = id
        self.name = name
        self.arguments = arguments

class PokemonGameTools:
    """
    Contains all the tools for controlling the Pokemon game
    """
    @staticmethod
    def define_tools() -> List[Tool]:
        """Define all the tools needed for the Pokemon game controller"""
        
        # Tool for pressing a button - THE PRIMARY TOOL
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
        
        # Tool for updating the notepad (AI's memory)
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
        
        # ONLY return these two tools
        return [press_button, update_notepad]

class LLMControlClient:
    """
    Client for communicating with LLMs using the tool-based approach
    """
    def __init__(self, provider: Provider, api_key: str, model_name: str, max_tokens: int = 1024):
        self.provider = provider
        self.api_key = api_key
        self.model_name = model_name
        self.max_tokens = max_tokens
        self._setup_client()
    
    def _setup_client(self):
        """Set up the appropriate client based on the provider"""
        if self.provider == Provider.ANTHROPIC:
            self.api_url = "https://api.anthropic.com/v1/messages"
            self.headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }
        elif self.provider == Provider.OPENAI:
            from openai import OpenAI
            self.client = OpenAI(api_key=self.api_key)
        elif self.provider == Provider.GOOGLE:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self.client = genai
    
    def call_with_tools(self, message: str, tools: List[Tool], images: List[PIL.Image.Image] = None) -> Tuple[Any, List[ToolCall], str]:
        """
        Call the LLM with the given message and tools, optionally including images
        """
        provider_tools = [tool.to_provider_format(self.provider) for tool in tools]
        
        if self.provider == Provider.ANTHROPIC:
            # Handle images for Claude
            content = [{"type": "text", "text": message}]
            
            if images:
                for image in images:
                    import base64
                    from io import BytesIO
                    
                    buffer = BytesIO()
                    image.save(buffer, format="PNG")
                    base64_image = base64.b64encode(buffer.getvalue()).decode("utf-8")
                    
                    content.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": base64_image
                        }
                    })
            
            system = """
            You are an AI playing Pokémon Red. Your ONLY job is to press buttons to control the game.
            
            IMPORTANT: You MUST use the press_button function to specify which button to press.
            
            Always select the appropriate button based on the context: 
            - A: To confirm, advance text, or select
            - B: To cancel or go back
            - Directional buttons: To navigate
            - START: To open the menu
            
            If you need to add important information to the long-term memory, use update_notepad.
            """
            
            response = requests.post(
                self.api_url,
                headers=self.headers,
                json={
                    "model": self.model_name,
                    "max_tokens": self.max_tokens,
                    "messages": [{"role": "user", "content": content}],
                    "system": system,
                    "tools": provider_tools
                }
            ).json()
            
        elif self.provider == Provider.OPENAI:
            import base64
            from io import BytesIO
            
            system = """
            You are an AI playing Pokémon Red. Your ONLY job is to press buttons to control the game.
            
            IMPORTANT: You MUST use the press_button function to specify which button to press.
            
            Always select the appropriate button based on the context: 
            - A: To confirm, advance text, or select
            - B: To cancel or go back
            - Directional buttons: To navigate
            - START: To open the menu
            
            If you need to add important information to the long-term memory, use update_notepad.
            """
            
            messages = [
                {"role": "system", "content": system},
            ]
            
            if images:
                # Add images to content
                content = []
                content.append({"type": "text", "text": message})
                
                for image in images:
                    buffer = BytesIO()
                    image.save(buffer, format="PNG")
                    base64_image = base64.b64encode(buffer.getvalue()).decode("utf-8")
                    content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{base64_image}"
                        }
                    })
                
                messages.append({"role": "user", "content": content})
            else:
                messages.append({"role": "user", "content": message})
            
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                tools=provider_tools,
                tool_choice="auto",
                max_tokens=self.max_tokens
            )
            
        elif self.provider == Provider.GOOGLE:
            import google.generativeai as genai
            
            model = self.client.GenerativeModel(model_name=self.model_name)
            
            # Tell Gemini EXPLICITLY that it must use the press_button function
            system_message = """
            You are playing Pokémon Red. You MUST press buttons to control the game.
            
            VERY IMPORTANT: After analyzing the screenshot, use the press_button function to execute a button press.
            You are REQUIRED to use the press_button function with every response.
            
            DO NOT just describe what button to press - you MUST execute the press_button function.
            
            If you need to record important information for long-term memory, use the update_notepad function.
            """
            
            # Create conversation with extremely direct instructions
            chat = model.start_chat(
                history=[
                    {"role": "user", "parts": [system_message]},
                    {"role": "model", "parts": ["I understand. For every screenshot, I will use the press_button function to specify which button to press (A, B, UP, DOWN, etc.)."]}
                ]
            )
            
            # Simple, direct message focusing on button selection
            enhanced_message = f"{message}\n\nYou MUST use the press_button function. Select which button to press (A, B, UP, DOWN, LEFT, RIGHT, START or SELECT)."
            content_parts = [enhanced_message]
            
            if images:
                for image in images:
                    content_parts.append(image)
            
            # Send the message with the image
            response = chat.send_message(
                content=content_parts,
                tools={"function_declarations": provider_tools}
            )
        
        return response, self._parse_tool_calls(response), self._extract_text(response)
    
    def _parse_tool_calls(self, response: Any) -> List[ToolCall]:
        """Parse tool calls from the LLM response"""
        tool_calls = []
        
        if self.provider == Provider.ANTHROPIC:
            try:
                for content_item in response.get("content", []):
                    if content_item.get("type") == "tool_use":
                        tool_calls.append(ToolCall(
                            id=content_item.get("id", f"tool_{len(tool_calls)}"),
                            name=content_item.get("name", "unknown"),
                            arguments=content_item.get("input", {})
                        ))
            except Exception as e:
                print(f"Error parsing Anthropic tool calls: {e}")
                
        elif self.provider == Provider.OPENAI:
            try:
                for choice in response.choices:
                    if hasattr(choice.message, "tool_calls") and choice.message.tool_calls:
                        for call in choice.message.tool_calls:
                            import json
                            tool_calls.append(ToolCall(
                                id=call.id,
                                name=call.function.name,
                                arguments=json.loads(call.function.arguments)
                            ))
            except Exception as e:
                print(f"Error parsing OpenAI tool calls: {e}")
                        
        elif self.provider == Provider.GOOGLE:
            try:
                # For Gemini, check for function calls in the response
                if hasattr(response, "candidates"):
                    for candidate in response.candidates:
                        if hasattr(candidate, "content") and candidate.content:
                            for part in candidate.content.parts:
                                if hasattr(part, "function_call") and part.function_call:
                                    # Only process if function_call exists and has a name
                                    if hasattr(part.function_call, "name") and part.function_call.name:
                                        args = {}
                                        if hasattr(part.function_call, "args") and part.function_call.args is not None:
                                            # Convert args to a dictionary
                                            try:
                                                # Handle either direct args or items method
                                                if hasattr(part.function_call.args, "items"):
                                                    for key, value in part.function_call.args.items():
                                                        args[key] = str(value)
                                                else:
                                                    # Try to handle as a single value
                                                    args = {"argument": str(part.function_call.args)}
                                            except:
                                                pass
                                        
                                        # Create a tool call object
                                        tool_calls.append(ToolCall(
                                            id=f"call_{len(tool_calls)}",
                                            name=part.function_call.name,
                                            arguments=args
                                        ))
                                    
            except Exception as e:
                print(f"Error parsing Google tool calls: {e}")
                import traceback
                print(traceback.format_exc())
        
        # Debug output
        print(f"Found {len(tool_calls)} tool calls")
        for call in tool_calls:
            print(f"Tool call: {call.name}, args: {call.arguments}")
        
        return tool_calls
    
    def _extract_text(self, response: Any) -> str:
        """Extract text from the LLM response"""
        if self.provider == Provider.ANTHROPIC:
            text_parts = []
            for item in response.get("content", []):
                if item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
            return "\n".join(text_parts)
            
        elif self.provider == Provider.OPENAI:
            return response.choices[0].message.content or ""
            
        elif self.provider == Provider.GOOGLE:
            try:
                # Try directly accessing text property
                if hasattr(response, "text"):
                    return response.text
                
                # Try extracting from candidates
                if hasattr(response, "candidates") and response.candidates:
                    text_parts = []
                    for candidate in response.candidates:
                        if hasattr(candidate, "content") and candidate.content:
                            for part in candidate.content.parts:
                                if hasattr(part, "text") and part.text:
                                    text_parts.append(part.text)
                    if text_parts:
                        return "\n".join(text_parts)
            except:
                pass
            
            return ""

class PokemonGameController:
    def __init__(self, config_path='config.json'):
        # Cleanup control
        self._cleanup_done = False
        self._cleanup_lock = threading.Lock()
        
        # Load configuration
        self.config = load_config(config_path)
        if not self.config:
            print(f"Failed to load config from {config_path}")
            sys.exit(1)
        
        # Get the LLM provider details
        provider_name = self.config.get("llm_provider", "anthropic").lower()
        provider = Provider(provider_name)
        provider_config = self.config["providers"][provider_name]
        
        # Create LLM client
        self.llm = LLMControlClient(
            provider=provider,
            api_key=provider_config["api_key"],
            model_name=provider_config["model_name"],
            max_tokens=provider_config.get("max_tokens", 1024)
        )
        
        # Store the provider name for use in prompts
        self.provider_name = provider_name
        
        # Initialize socket server
        self.server_socket = None
        
        # Define tools
        self.tools = PokemonGameTools.define_tools()
        
        # Game state variables
        self.notepad_path = self.config['notepad_path']
        self.screenshot_path = self.config['screenshot_path']
        self.current_client = None
        self.running = True
        self.last_decision_time = 0
        self.decision_cooldown = self.config['decision_cooldown']
        self.client_threads = []
        self.debug_mode = self.config.get('debug_mode', False)
        
        # Short-term memory for recent actions (last 10 actions)
        self.recent_actions = deque(maxlen=10)
        
        # Create directories if they don't exist
        os.makedirs(os.path.dirname(self.notepad_path), exist_ok=True)
        os.makedirs(os.path.dirname(self.screenshot_path), exist_ok=True)
        
        # Initialize the logger
        self.logger = PokemonLogger(debug_mode=self.debug_mode)
        
        # Initialize notepad if it doesn't exist
        self.initialize_notepad()
        
        self.logger.info("Controller initialized")
        self.logger.debug(f"LLM Provider: {self.provider_name}")
        self.logger.debug(f"Notepad path: {self.notepad_path}")
        self.logger.debug(f"Screenshot path: {self.screenshot_path}")
        
        # Set up the socket after logger is initialized
        self.setup_socket()
        
        # Set up signal handlers for proper shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        # Register cleanup function
        atexit.register(self.cleanup)

    def setup_socket(self):
        """Set up the socket server with improved error handling and stability"""
        try:
            # Initialize socket server
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # Add keep-alive options to prevent disconnections
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            
            # Try to set TCP keepalive options if available
            try:
                # TCP Keepalive options: time, interval, retries
                self.server_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 60)
                self.server_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)
                self.server_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 6)
            except (AttributeError, OSError):
                self.logger.debug("TCP keepalive options not fully supported on this platform")
            
            # Try to bind to the port
            try:
                self.server_socket.bind((self.config['host'], self.config['port']))
            except socket.error:
                self.logger.warning(f"Port {self.config['port']} is already in use. Trying to release it...")
                os.system(f"lsof -ti:{self.config['port']} | xargs kill -9")
                time.sleep(1)  # Wait for port to be released
                self.server_socket.bind((self.config['host'], self.config['port']))
            
            self.server_socket.listen(1)
            self.server_socket.settimeout(1)  # Non-blocking socket with timeout
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
        """Clean up resources properly - runs only once"""
        with self._cleanup_lock:
            if self._cleanup_done:
                return
            self._cleanup_done = True
            
            self.logger.section("Cleaning up resources...")
            
            # Close client connections
            if self.current_client:
                try:
                    self.current_client.close()
                    self.current_client = None
                except:
                    pass
            
            # Close server socket
            if self.server_socket:
                try:
                    self.server_socket.close()
                    self.server_socket = None
                except:
                    pass
                
            self.logger.success("Cleanup complete")
            
            # Give time to shut down (fixes the timeout warning)
            time.sleep(0.5)

    def initialize_notepad(self):
        """Initialize the notepad file with a clearer structure"""
        if not os.path.exists(self.notepad_path):
            os.makedirs(os.path.dirname(self.notepad_path), exist_ok=True)
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            with open(self.notepad_path, 'w') as f:
                f.write("# Pokémon Game AI Notepad\n\n")
                f.write(f"Game started: {timestamp}\n\n")
                f.write("## Current Status\n")
                f.write("- Game just started\n\n")
                f.write("## Game Progress\n")
                f.write("- Beginning journey\n\n")

    def read_notepad(self):
        """Read the current notepad content"""
        try:
            with open(self.notepad_path, 'r') as f:
                return f.read()
        except Exception as e:
            print(f"Error reading notepad: {e}")
            return "Error reading notepad"

    def update_notepad(self, new_content):
        """Update the notepad with new content or append to it"""
        try:
            # Get current content
            current_content = self.read_notepad()
            
            # Add timestamp and append the new content
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            updated_content = current_content + f"\n## Update {timestamp}\n{new_content}\n"
            
            # Write the updated content
            with open(self.notepad_path, 'w') as f:
                f.write(updated_content)
            
            self.logger.debug("Notepad updated")
            
            # Check if notepad is getting too large
            if len(updated_content) > 10000:
                self.summarize_notepad()
                
        except Exception as e:
            self.logger.error(f"Error updating notepad: {e}")

    def summarize_notepad(self):
        """Summarize the notepad when it gets too long"""
        try:
            self.logger.info("Notepad is getting large, summarizing...")
            
            # Get the current notepad content
            notepad_content = self.read_notepad()
            
            # Create a summarization prompt
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
            
            # No tools needed for summarization
            empty_tools = []
            
            # Call the LLM to summarize
            response, _, text = self.llm.call_with_tools(
                message=summarize_prompt + notepad_content,
                tools=empty_tools
            )
            
            if text:
                # Add a timestamp to the summarized content
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                summary = f"# Pokémon Game AI Notepad (Summarized)\n\n"
                summary += f"Last summarized: {timestamp}\n\n"
                summary += text
                
                # Write the summarized content back to the notepad
                with open(self.notepad_path, 'w') as f:
                    f.write(summary)
                
                self.logger.success("Notepad summarized successfully")
            
        except Exception as e:
            self.logger.error(f"Error summarizing notepad: {e}")

    def get_recent_actions_text(self):
        """Get formatted text of recent actions for short-term memory"""
        if not self.recent_actions:
            return "No recent actions."
            
        # Format recent actions chronologically, newest last
        recent_actions_text = "Your recent actions:\n"
        for i, action in enumerate(self.recent_actions, 1):
            recent_actions_text += f"{i}. {action}\n"
            
        return recent_actions_text

    def process_screenshot(self, screenshot_path=None):
        """Process a screenshot - with short-term memory of actions"""
        current_time = time.time()
        
        # Check cooldown
        if current_time - self.last_decision_time < self.decision_cooldown:
            return None
            
        try:
            # Read game state data (long-term memory)
            notepad_content = self.read_notepad()
            
            # Get recent actions (short-term memory)
            recent_actions = self.get_recent_actions_text()
            
            # Use provided path or default
            path_to_use = screenshot_path if screenshot_path else self.screenshot_path
            
            if not os.path.exists(path_to_use):
                self.logger.error(f"Screenshot not found at {path_to_use}")
                return None
            
            # Load current screenshot
            try:
                current_image = PIL.Image.open(path_to_use)
            except Exception as e:
                self.logger.error(f"Error opening screenshot: {e}")
                return None
            
            # Prompt with both short-term and long-term memory
            prompt = f"""
            You are playing Pokémon Red. Look at this screenshot and choose ONE button to press.
            
            ## Controls:
            - A: To confirm, select, talk, or advance text
            - B: To cancel or go back
            - UP, DOWN, LEFT, RIGHT: To move or navigate menus
            - START: To open the main menu
            - SELECT: Rarely used special function
            
            ## Short-term Memory (Recent Actions):
            {recent_actions}
            
            ## Long-term Memory (Game State):
            {notepad_content}
            
            Choose the appropriate button for this situation and use the press_button function to execute it.
            """
            
            # Send the image with the prompt
            images = [current_image]
            
            # Log that we're requesting a decision
            self.logger.section(f"Requesting decision from {self.provider_name}")
            
            # Get response from AI with tools
            response, tool_calls, text = self.llm.call_with_tools(
                message=prompt,
                tools=self.tools,
                images=images
            )
            
            # Display the raw text response for debugging
            print(f"LLM Text Response: {text}")
            
            # Look for button press tool calls
            button_code = None
            
            for call in tool_calls:
                # Handle notepad updates (long-term memory)
                if call.name == "update_notepad":
                    content = call.arguments.get("content", "")
                    if content:
                        self.update_notepad(content)
                        print(f"Updated notepad with: {content[:50]}...")
                
                # Look for button presses
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
                        
                        # Add to short-term memory
                        timestamp = time.strftime("%H:%M:%S")
                        memory_entry = f"[{timestamp}] Pressed {button}"
                        self.recent_actions.append(memory_entry)
                        
                        # Log the action
                        self.logger.ai_action(button, button_code)
                        
                        # Update decision time
                        self.last_decision_time = current_time
                        
                        # Return the decision - no fallback if not found
                        return {'button': button_code}
            
            # If no button press tool was used, just log and return None
            if button_code is None:
                self.logger.warning("No press_button tool call found!")
                return None
            
        except Exception as e:
            self.logger.error(f"Error processing screenshot: {e}")
            if self.debug_mode:
                import traceback
                self.logger.debug(traceback.format_exc())
        
        return None

    def handle_client(self, client_socket, client_address):
        """Handle communication with the emulator client"""
        self.logger.section(f"Connected to emulator at {client_address}")
        self.current_client = client_socket
        
        self.logger.game_state("Waiting for game data...")
        
        while self.running:
            try:
                data = client_socket.recv(1024)
                if not data:
                    break
                
                # Parse the message from the emulator
                message = data.decode('utf-8').strip()
                
                parts = message.split("||")
                
                if len(parts) >= 2:
                    message_type = parts[0]
                    content = parts[1]
                    
                    # Handle different message types
                    if message_type == "screenshot":
                        self.logger.game_state("Received new screenshot from emulator")
                        
                        # Verify the file exists
                        if os.path.exists(content):
                            # Process the screenshot - no fallbacks
                            decision = self.process_screenshot(content)
                            
                            if decision and decision.get('button') is not None:
                                # Only send button press if one was specified by a tool
                                try:
                                    button_code = str(decision['button'])
                                    self.logger.debug(f"Sending button code to emulator: {button_code}")
                                    client_socket.send(button_code.encode('utf-8') + b'\n')
                                    self.logger.success("Button command sent to emulator")
                                except Exception as e:
                                    self.logger.error(f"Failed to send button command: {e}")
                                    break
                            else:
                                self.logger.warning("No button press in decision - waiting for next screenshot")
                        else:
                            self.logger.error(f"Screenshot file not found at {content}")
                
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
        
        self.logger.section(f"Disconnected from emulator at {client_address}")
        self.current_client = None
        try:
            client_socket.close()
        except:
            pass

    def handle_client_connection(self, client_socket, client_address):
        """Wrapper around handle_client to properly handle connection errors"""
        try:
            self.handle_client(client_socket, client_address)
        except Exception as e:
            self.logger.error(f"Client connection error: {e}")
        finally:
            # Ensure we close the connection properly
            if client_socket:
                try:
                    client_socket.close()
                except:
                    pass
            
            # Remove client from our tracking
            if self.current_client == client_socket:
                self.current_client = None

    def start(self):
        """Start the controller server with improved connection handling"""
        self.logger.header(f"Starting Pokémon Game Controller with {self.provider_name}")
        
        try:
            while self.running:
                try:
                    self.logger.section("Waiting for emulator connection...")
                    client_socket, client_address = self.server_socket.accept()
                    
                    # Set SO_KEEPALIVE on the client socket
                    client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                    
                    # Try to set TCP keepalive options if available
                    try:
                        client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 60)
                        client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)
                        client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 6)
                    except (AttributeError, OSError):
                        pass
                    
                    client_socket.setblocking(0)
                    
                    # Start client handler in a separate thread
                    client_thread = threading.Thread(
                        target=self.handle_client_connection,
                        args=(client_socket, client_address)
                    )
                    client_thread.daemon = True
                    client_thread.start()
                    self.client_threads.append(client_thread)
                
                except socket.timeout:
                    # Just a timeout, continue the loop
                    continue
                except KeyboardInterrupt:
                    self.logger.section("Keyboard interrupt detected. Shutting down...")
                    break
                except Exception as e:
                    if self.running:  # Only log if we're still supposed to be running
                        self.logger.error(f"Error in main loop: {e}")
                        if self.debug_mode:
                            import traceback
                            self.logger.debug(traceback.format_exc())
                        # Short delay to prevent tight error loops
                        time.sleep(1)
        finally:
            # Ensure we clean up properly
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
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Pokémon Game AI Controller")
    parser.add_argument(
        "--config", 
        "-c", 
        default="config.json", 
        help="Path to the configuration file"
    )
    
    args = parser.parse_args()
    
    # Create controller with specified config
    controller = PokemonGameController(args.config)
    try:
        controller.start()
    except KeyboardInterrupt:
        pass  # Already handled in signal_handler
    finally:
        controller.cleanup()