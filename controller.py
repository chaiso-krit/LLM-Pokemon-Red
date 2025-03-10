#!/usr/bin/env python3
import os
import socket
import time
import threading
import re
import PIL.Image
import signal
import sys
import atexit
import argparse
from pokemon_logger import PokemonLogger
from llm_provider import get_llm_provider  # Import our new provider factory
from config_loader import load_config  # Import the config loader

class PokemonGameController:
    def __init__(self, config_path='config.json'):
        # Cleanup control
        self._cleanup_done = False
        self._cleanup_lock = threading.Lock()
        
        # Load configuration with environment variable support
        self.config = load_config(config_path)
        if not self.config:
            print(f"Failed to load config from {config_path}")
            sys.exit(1)
        
        # Set up LLM provider instead of directly using Gemini
        self.llm = get_llm_provider(self.config)
        if not self.llm:
            print("Error: Failed to initialize LLM provider")
            sys.exit(1)
            
        # Store the provider name for use in prompts
        self.provider_name = self.llm.get_provider_name()
        
        # Initialize socket server
        self.server_socket = None
        
        # Game state variables
        self.notepad_path = self.config['notepad_path']
        self.screenshot_path = self.config['screenshot_path']
        self.thinking_history_path = os.path.join(os.path.dirname(self.notepad_path), 'thinking_history.txt')
        self.current_client = None
        self.running = True
        self.last_decision_time = 0
        self.decision_cooldown = self.config['decision_cooldown']
        self.client_threads = []
        self.debug_mode = self.config.get('debug_mode', False)
        
        # Create directories if they don't exist
        os.makedirs(os.path.dirname(self.notepad_path), exist_ok=True)
        os.makedirs(os.path.dirname(self.screenshot_path), exist_ok=True)
        
        # Initialize the logger
        self.logger = PokemonLogger(debug_mode=self.debug_mode)
        
        # Initialize notepad and thinking history if they don't exist
        self.initialize_notepad()
        self.initialize_thinking_history()
        
        self.logger.info("Controller initialized")
        self.logger.debug(f"LLM Provider: {self.provider_name}")
        self.logger.debug(f"Model: {self.llm.get_model_name()}")
        self.logger.debug(f"Notepad path: {self.notepad_path}")
        self.logger.debug(f"Thinking history path: {self.thinking_history_path}")
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
            # These options might not be available on all platforms
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

    # Config loading is now handled by the config_loader module

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

    def initialize_thinking_history(self):
        """Initialize the thinking history file if it doesn't exist"""
        if not os.path.exists(self.thinking_history_path):
            os.makedirs(os.path.dirname(self.thinking_history_path), exist_ok=True)
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            with open(self.thinking_history_path, 'w') as f:
                f.write(f"# Pokémon Game AI Thinking History\n\n")
                f.write(f"Started: {timestamp}\n\n")

    def read_notepad(self):
        """Read the current notepad content"""
        try:
            with open(self.notepad_path, 'r') as f:
                return f.read()
        except Exception as e:
            print(f"Error reading notepad: {e}")
            return "Error reading notepad"

    def read_thinking_history(self):
        """Read the current thinking history content"""
        try:
            with open(self.thinking_history_path, 'r') as f:
                return f.read()
        except Exception as e:
            print(f"Error reading thinking history: {e}")
            return "Error reading thinking history"

    def update_notepad(self, new_content):
        """Update the notepad with new content"""
        try:
            with open(self.notepad_path, 'w') as f:
                f.write(new_content)
            print("Notepad updated")
        except Exception as e:
            print(f"Error updating notepad: {e}")

    def update_thinking_history(self, new_thinking):
        """Update the thinking history with new content"""
        try:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            
            # Get existing history, but limit to recent entries if too large
            history_content = self.read_thinking_history()
            
            # If history gets too long, keep only the most recent entries
            max_chars = self.config['thinking_history_max_chars']
            keep_entries = self.config['thinking_history_keep_entries']
            
            if len(history_content) > max_chars:
                # Split by timestamps and keep only the most recent ones
                entries = history_content.split("## Thinking")
                # Keep header and last N entries based on config
                if len(entries) > keep_entries + 1:  # +1 for the header
                    history_content = entries[0] + "".join(entries[-(keep_entries):])
                    self.logger.debug(f"Trimmed thinking history to {keep_entries} entries")
            
            # Add new thinking with timestamp
            with open(self.thinking_history_path, 'w') as f:
                f.write(history_content)
                f.write(f"\n## Thinking {timestamp}\n{new_thinking}\n")
            
            self.logger.debug("Thinking history updated")
        except Exception as e:
            print(f"Error updating thinking history: {e}")

    def summarize_notepad_if_needed(self):
        """Summarize notepad if it gets too long, keeping the structure intact"""
        notepad_content = self.read_notepad()
        
        # If notepad is over 10KB, ask LLM to summarize it
        if len(notepad_content) > 10000:
            print("Notepad is getting too long, summarizing...")
            
            try:
                summarize_prompt = """
                Please summarize the following game notes into a more concise format.
                
                Maintain these exact sections:
                - Long-term Goals
                - Current Objectives 
                - Team Status
                - Inventory
                - Game Progress
                
                Condense repetitive information but preserve all important game state details:
                - Current location and next destination
                - All Pokémon on the team with their levels, types and moves
                - Important items in the inventory
                - Badges collected and significant events
                - Current strategy and immediate plans
                
                Format the response as a well-structured markdown document with clear headings and bullet points.
                
                Here are the notes to summarize:
                
                """
                
                # Use our provider-agnostic interface
                response_text = self.llm.generate_content(summarize_prompt + notepad_content)
                
                if response_text:
                    # Add a note about summarization
                    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                    response_text += f"\n\n## Note\nNotepad was summarized at {timestamp} to reduce size while preserving important information."
                    
                    self.update_notepad(response_text)
                    print("Notepad summarized successfully")
            except Exception as e:
                print(f"Error summarizing notepad: {e}")

    def process_screenshot(self, screenshot_path=None):
        """Process the latest screenshot with the LLM provider, also sending previous screenshot"""
        current_time = time.time()
        
        # Check if we should make a new decision based on cooldown
        if current_time - self.last_decision_time < self.decision_cooldown:
            return None  # Skip decision making during cooldown
            
        try:
            # Read the notepad and thinking history
            notepad_content = self.read_notepad()
            thinking_history = self.read_thinking_history()
            
            # Use provided path or default
            path_to_use = screenshot_path if screenshot_path else self.screenshot_path
            
            if not os.path.exists(path_to_use):
                self.logger.error(f"Screenshot not found at {path_to_use}")
                return None
            
            # Setup previous screenshot path
            comparison_folder = os.path.join(os.path.dirname(self.screenshot_path), 'comparison')
            os.makedirs(comparison_folder, exist_ok=True)
            prev_screenshot_path = os.path.join(comparison_folder, 'previous_screenshot.png')
            last_action_path = os.path.join(comparison_folder, 'last_action.txt')
            
            # Get the last action (button pressed)
            last_action = "NONE (First action)"
            if os.path.exists(last_action_path):
                try:
                    with open(last_action_path, 'r') as f:
                        last_action = f.read().strip()
                except:
                    pass
            
            # Load current screenshot
            current_image = PIL.Image.open(path_to_use)
            
            # Check if we have a previous screenshot
            has_previous = os.path.exists(prev_screenshot_path)
            previous_image = None
            
            if has_previous:
                previous_image = PIL.Image.open(prev_screenshot_path)
            
            # Craft the prompt with the dynamic provider name
            prompt = f"""
                You are {self.provider_name}, an AI playing Pokémon Fire Red. Look at the screenshots and make decisions to progress in the game.
                
                ## Game Context
                - You are playing Pokémon Fire Red for Game Boy Advance
                - You are at the beginning of the game in Pallet Town
                - The game has buildings, routes, and towns to navigate through
                
                ## Screenshots Information
                - You are receiving TWO screenshots: current and previous state
                - The first image is your CURRENT view
                - The second image is the PREVIOUS view (before your last action)
                - Your last action was: {last_action}
                - IMPORTANT: Compare these images to see if your last action had any effect
                - If the character position is the same in both images, it means you hit a WALL or OBSTACLE
                
                ## Pokémon Game Navigation Rules:
                - Indoor spaces: Rooms have walls and you CAN'T walk through them
                - In your bedroom, the STAIRS are the YELLOW LADDER in the TOP LEFT corner
                - Carpets/Rugs indicate walkable areas in rooms
                - To use stairs or doors, stand DIRECTLY IN FRONT of them and press A
                
                ## Your notepad (your memory):
                {notepad_content}
                
                ## Your recent thinking:
                {thinking_history}
                
                ## Controls Available:
                - A: Confirm/Select/Interact
                - B: Cancel/Back
                - START: Open menu
                - UP, DOWN, LEFT, RIGHT: Move/Navigate
                
                ## Your task:
                1. FIRST: Compare the current and previous screenshots to see if your last action ({last_action}) caused movement
                2. If you didn't move, conclude there's a wall in that direction and try a DIFFERENT direction
                3. If you're in the bedroom, locate the yellow ladder (stairs) in the top left corner
                4. Choose ONE button to press that will make progress
                5. Update your notepad if needed
                
                Respond in this exact format:
                THINK: [First analyze if your last action caused movement, then analyze the current situation]
                BUTTON: [single button name (A, B, START, UP, DOWN, LEFT, RIGHT). YOU MUST include the button you want to press.]
                NOTEPAD: [one of: "no change" OR specific information to add]
                
                Buttons must be EXACTLY one of: A, B, START, UP, DOWN, LEFT, RIGHT
                """
            
            self.logger.section(f"Sending Screenshots to {self.provider_name}")
            
            # Save current screenshot as previous for next time
            try:
                current_image.save(prev_screenshot_path)
            except Exception as e:
                self.logger.error(f"Error saving previous screenshot: {e}")
            
            # Generate response from LLM provider - send both current and previous screenshots if available
            images = []
            if current_image:
                images.append(current_image)
            if has_previous and previous_image:
                self.logger.info("Sending both current and previous screenshots for comparison")
                images.append(previous_image)
            else:
                self.logger.info("First screenshot - no previous for comparison")
            
            # Use our provider-agnostic interface
            response_text = self.llm.generate_content(prompt, images)
            
            if response_text:
                self.logger.success(f"Received response from {self.provider_name}")
                
                # Parse response for button press and notepad update
                button_press, notepad_update, thinking = self.parse_llm_response(response_text)
                self.last_decision_time = current_time
                
                # Log the AI's thinking and actions
                self.logger.ai_thinking(thinking)
                
                if button_press is not None:
                    # Map button index back to name for better logging
                    button_names = {0: "A", 1: "B", 2: "SELECT", 3: "START", 
                                4: "RIGHT", 5: "LEFT", 6: "UP", 7: "DOWN",
                                8: "R", 9: "L"}
                    button_name = button_names.get(button_press, "UNKNOWN")
                    
                    # Save the button name for next comparison
                    try:
                        with open(last_action_path, 'w') as f:
                            f.write(button_name)
                    except Exception as e:
                        self.logger.error(f"Error saving last action: {e}")
                    
                    self.logger.ai_action(button_name, button_press)
                
                if notepad_update:
                    new_content = notepad_update.split("## Update")[-1] if "## Update" in notepad_update else notepad_update
                    self.logger.notepad(new_content)
                
                return {
                    'button': button_press,
                    'notepad_update': notepad_update
                }
            
        except Exception as e:
            self.logger.error(f"Error processing screenshot: {e}")
            if self.debug_mode:
                import traceback
                self.logger.debug(traceback.format_exc())
        
        return None

    def parse_llm_response(self, response_text):
        """Parse the LLM response to extract button press, notepad update and thinking"""
        button_press = None
        notepad_update = None
        thinking = None
        
        # Button mapping
        button_map = {
            "A": 0, "B": 1, "SELECT": 2, "START": 3,
            "RIGHT": 4, "LEFT": 5, "UP": 6, "DOWN": 7,
            "R": 8, "L": 9
        }
        
        # Find each section
        think_match = re.search(r"THINK:\s*(.*?)(?=BUTTON:|$)", response_text, re.DOTALL)
        button_match = re.search(r"BUTTON:\s*(.*?)(?=NOTEPAD:|$)", response_text, re.DOTALL)
        notepad_match = re.search(r"NOTEPAD:\s*(.*?)$", response_text, re.DOTALL)
        
        # Extract thinking
        if think_match:
            thinking = think_match.group(1).strip()
            # Save thinking to history
            self.update_thinking_history(thinking)
            
        # Extract button press
        if button_match:
            button_value = button_match.group(1).strip().upper()
            if button_value in button_map:
                button_press = button_map[button_value]
            else:
                # Default to A if invalid button
                button_press = 0
                self.logger.warning(f"Invalid button '{button_value}', defaulting to A (0)")
        
        # Extract notepad update
        if notepad_match:
            notepad_content = notepad_match.group(1).strip()
            if notepad_content.lower() != "no change":
                # Create more meaningful updates by filtering repetitive content
                # Remove phrases that just talk about pressing buttons
                filtered_content = re.sub(r"I (will|am going to|should) press [A-Z]+ to.*?\.", "", notepad_content)
                filtered_content = re.sub(r"I (will|should|am going to|need to) (select|choose|pick).*?\.", "", filtered_content)
                filtered_content = filtered_content.strip()
                
                if filtered_content:
                    # Add timestamp to notepad entries
                    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                    
                    # Add to existing notepad with timestamp
                    current_notepad = self.read_notepad()
                    notepad_update = current_notepad + f"\n## Update {timestamp}\n{filtered_content}\n"
        
        return button_press, notepad_update, thinking

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
                            decision = self.process_screenshot(content)
                            
                            if decision:
                                # Send button press to emulator
                                if decision['button'] is not None and self.running:
                                    try:
                                        client_socket.send(str(decision['button']).encode('utf-8') + b'\n')
                                        self.logger.success("Button command sent to emulator")
                                    except:
                                        self.logger.error("Failed to send button command")
                                        break
                                
                                # Update notepad if needed
                                if decision['notepad_update']:
                                    self.update_notepad(decision['notepad_update'])
                                    self.summarize_notepad_if_needed()
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

    def log_debug(self, message):
        """Log debug messages if debug mode is enabled"""
        if self.debug_mode:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            print(f"[DEBUG {timestamp}] {message}")
    
    def extract_game_info(self, screenshot_path):
        """
        Extract useful game information from screenshots
        This could be expanded with OCR or more advanced CV techniques
        """
        try:
            # This is a placeholder for future OCR/CV improvements
            # We could use OCR to extract text from the game screen
            # For now, we'll just return the basic file info
            if os.path.exists(screenshot_path):
                file_size = os.path.getsize(screenshot_path)
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                return {
                    "timestamp": timestamp,
                    "file_size": file_size,
                    "path": screenshot_path
                }
            return None
        except Exception as e:
            print(f"Error extracting game info: {e}")
            return None

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