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
import base64
from io import BytesIO
from collections import deque
from typing import Dict, List, Any, Tuple
# Import from your existing modules
from pokemon_logger import PokemonLogger
from config_loader import load_config
from openai import OpenAI

class Tool:
    """Simple class to define a tool for OpenAI"""
    def __init__(self, name: str, description: str, parameters: List[Dict[str, Any]]):
        self.name = name
        self.description = description
        self.parameters = parameters
    
    def to_openai_format(self) -> Dict[str, Any]:
        """Convert to OpenAI's expected format"""
        return {
            "type": "function",
            "function": {
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
        }

class ToolCall:
    """Represents a tool call from OpenAI"""
    def __init__(self, id: str, name: str, arguments: Dict[str, Any]):
        self.id = id
        self.name = name
        self.arguments = arguments

class OpenAIClient:
    """Client specifically for communicating with OpenAI"""
    def __init__(self, api_key: str, model_name: str, max_tokens: int = 1024):
        self.api_key = api_key
        self.model_name = model_name
        self.max_tokens = max_tokens
        self._setup_client()
    
    def _setup_client(self):
        """Set up the OpenAI client"""
        self.client = OpenAI(api_key=self.api_key)
    
    def call_with_tools(self, message: str, tools: List[Tool], images: List[PIL.Image.Image] = None) -> Tuple[Any, List[ToolCall], str]:
        """
        Call OpenAI with the given message and tools, optionally including images
        """
        provider_tools = [tool.to_openai_format() for tool in tools]
        
        system_message = """
        You are playing Pokémon Red. Your job is to press buttons to control the game.
        
        IMPORTANT: After analyzing the screenshot, you MUST use the press_button function.
        You are REQUIRED to use the press_button function with every response.
        
        NEVER just say what button to press - ALWAYS use the press_button function to actually press it.
        """
        
        messages = [
            {"role": "system", "content": system_message},
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
        
        return response, self._parse_tool_calls(response), self._extract_text(response)
    
    def _parse_tool_calls(self, response: Any) -> List[ToolCall]:
        """Parse tool calls from OpenAI's response"""
        tool_calls = []
        
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
            import traceback
            print(traceback.format_exc())
        
        for call in tool_calls:
            print(f"Tool call: {call.name}, args: {call.arguments}")
        
        return tool_calls
    
    def _extract_text(self, response: Any) -> str:
        """Extract text from the OpenAI response"""
        try:
            if response.choices and hasattr(response.choices[0], "message"):
                return response.choices[0].message.content or ""
        except:
            pass
        
        return ""

class OpenAIPokemonController:
    def __init__(self, config_path='config.json'):
        self._cleanup_done = False
        self._cleanup_lock = threading.Lock()
        
        self.config = load_config(config_path)
        if not self.config:
            print(f"Failed to load config from {config_path}")
            sys.exit(1)
        
        provider_config = self.config["providers"]["openai"]
        
        self.openai = OpenAIClient(
            api_key=provider_config["api_key"],
            model_name=provider_config["model_name"],
            max_tokens=provider_config.get("max_tokens", 1024)
        )
        
        self.server_socket = None
        self.tools = self._define_tools()
        
        self.notepad_path = self.config['notepad_path']
        self.screenshot_path = self.config['screenshot_path']
        self.current_client = None
        self.running = True
        self.last_decision_time = 0
        self.decision_cooldown = self.config['decision_cooldown']
        self.client_threads = []
        self.debug_mode = self.config.get('debug_mode', False)
        
        # Store timestamp, button, and full reasoning text
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
            response, _, text = self.openai.call_with_tools(
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
        """Get formatted text of recent actions with reasoning"""
        if not self.recent_actions:
            return "No recent actions."
        
        recent_actions_text = "## Short-term Memory (Recent Actions and Reasoning):\n"
        for i, (timestamp, button, reasoning) in enumerate(self.recent_actions, 1):
            recent_actions_text += f"{i}. [{timestamp}] Pressed {button}\n"
            recent_actions_text += f"   Reasoning: {reasoning.strip()}\n\n"
        return recent_actions_text

    def process_screenshot(self, screenshot_path=None):
        """Process a screenshot with enhanced short-term memory"""
        current_time = time.time()
        
        if current_time - self.last_decision_time < self.decision_cooldown:
            return None
            
        try:
            notepad_content = self.read_notepad()
            recent_actions = self.get_recent_actions_text()
            path_to_use = screenshot_path if screenshot_path else self.screenshot_path
            
            if not os.path.exists(path_to_use):
                self.logger.error(f"Screenshot not found at {path_to_use}")
                return None
            
            # Load the original image
            original_image = PIL.Image.open(path_to_use)
            self.logger.debug(f"Original screenshot dimensions: {original_image.size[0]}x{original_image.size[1]}")
            
            # Resize the image to 3x larger for better visibility
            scale_factor = 3
            current_image = original_image.resize(
                (original_image.size[0] * scale_factor, original_image.size[1] * scale_factor), 
                PIL.Image.NEAREST
            )
            self.logger.debug(f"Resized screenshot dimensions: {current_image.size[0]}x{current_image.size[1]}")
            
            prompt = f"""
            You are playing Pokémon Red. You control the character with the red hat. Look at this screenshot and choose ONE button to press.

            ## POKÉMON GAME MECHANICS:
            - You CANNOT enter buildings by pressing A - you must WALK to the door
            - In Pokémon Red, you enter buildings by walking into doorways, not by pressing A
            - To ENTER a door: Walk UP into the doorway
            - To EXIT a building: Walk onto the red mat and press DOWN
            - Professor Oak is NOT in your house - he's in his LAB elsewhere in town
            - DO NOT go back into places you just came from

            ## PALLET TOWN GEOGRAPHY:
            - You are now in Pallet Town (outside)
            - Professor Oak's lab is a larger building in town
            - There are only a few buildings in Pallet Town
            - EXPLORE by walking around town to find Oak's lab
            
            ## Controls:
            - A: To talk to people or interact with objects (NOT for entering buildings)
            - B: To cancel or go back
            - UP, DOWN, LEFT, RIGHT: To move your character (use these to enter buildings)
            - START: To open the main menu
            - SELECT: Rarely used
            
            {recent_actions}
            
            ## Long-term Memory (Game State):
            {notepad_content}
            
            IMPORTANT: Use update_notepad when you discover new areas or information.
            
            Choose the appropriate button and use the press_button function.
            """
            
            images = [current_image]
            self.logger.section(f"Requesting decision from OpenAI")
            
            response, tool_calls, text = self.openai.call_with_tools(
                message=prompt,
                tools=self.tools,
                images=images
            )
            
            print(f"OpenAI Text Response: {text}")
            
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
                        
                        # Store timestamp, button, and full reasoning text
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
                
                message = data.decode('utf-8').strip()
                parts = message.split("||")
                
                if len(parts) >= 2:
                    message_type = parts[0]
                    content = parts[1]
                    
                    if message_type == "screenshot":
                        self.logger.game_state("Received new screenshot from emulator")
                        if os.path.exists(content):
                            decision = self.process_screenshot(content)
                            if decision and decision.get('button') is not None:
                                try:
                                    button_code = str(decision['button'])
                                    self.logger.debug(f"Sending button code to emulator: {button_code}")
                                    client_socket.send(button_code.encode('utf-8') + b'\n')
                                    self.logger.success("Button command sent to emulator")
                                except Exception as e:
                                    self.logger.error(f"Failed to send button command: {e}")
                                    break
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
        self.logger.header(f"Starting Pokémon Game Controller with OpenAI")
        
        try:
            while self.running:
                try:
                    self.logger.section("Waiting for emulator connection...")
                    client_socket, client_address = self.server_socket.accept()
                    client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
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
    parser = argparse.ArgumentParser(description="OpenAI Pokémon Game AI Controller")
    parser.add_argument("--config", "-c", default="config.json", help="Path to the configuration file")
    args = parser.parse_args()
    
    controller = OpenAIPokemonController(args.config)
    try:
        controller.start()
    except KeyboardInterrupt:
        pass
    finally:
        controller.cleanup()