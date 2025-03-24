#!/usr/bin/env python3
import socket
import threading
import time
import json
import os
import sys
import signal

class MemoryTestController:
    def __init__(self, host='127.0.0.1', port=8889):
        self.host = host
        self.port = port
        self.server_socket = None
        self.running = True
        self.current_client = None
        
        # Set up signal handlers for proper shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        # Setup the socket
        self.setup_socket()
        
    def setup_socket(self):
        """Set up the socket server"""
        try:
            # Initialize socket server
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # Try to bind to the port
            try:
                self.server_socket.bind((self.host, self.port))
            except socket.error:
                print(f"Port {self.port} is already in use. Trying to release it...")
                os.system(f"lsof -ti:{self.port} | xargs kill -9")
                time.sleep(1)  # Wait for port to be released
                self.server_socket.bind((self.host, self.port))
            
            self.server_socket.listen(1)
            self.server_socket.settimeout(1)  # Non-blocking socket with timeout
            print(f"Socket server set up on {self.host}:{self.port}")
            
        except socket.error as e:
            print(f"Socket setup error: {e}")
            sys.exit(1)
            
    def signal_handler(self, sig, frame):
        """Handle termination signals"""
        print(f"\nReceived signal {sig}. Shutting down server...")
        self.running = False
        self.cleanup()
        sys.exit(0)
        
    def cleanup(self):
        """Clean up resources properly"""
        print("Cleaning up resources...")
        
        # Close client connections
        if self.current_client:
            try:
                self.current_client.close()
            except:
                pass
            self.current_client = None
        
        # Close server socket
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
            self.server_socket = None
            
        print("Cleanup complete")
    
    def handle_client(self, client_socket, client_address):
        """Handle communication with the emulator client"""
        print(f"Connected to emulator at {client_address}")
        self.current_client = client_socket
        
        print("Waiting for game memory data...")
        
        map_names = {
            0: "Pallet Town",
            1: "Viridian City",
            2: "Pewter City",
            # Add more as we discover them
        }
        
        # Keep track of the last values to only show changes
        last_values = {
            "direction": None,
            "position": None,
            "mapId": None
        }
        
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
                    if message_type == "memory_data":
                        try:
                            # Parse JSON data
                            memory_data = json.loads(content)
                            
                            # Check for changes to avoid duplicate output
                            changed = False
                            changes = []
                            
                            # Check direction change
                            if last_values["direction"] != memory_data["direction"]["text"]:
                                last_values["direction"] = memory_data["direction"]["text"]
                                changed = True
                                changes.append(f"Direction: {memory_data['direction']['text']}")
                            
                            # Check position change
                            position_str = f"X={memory_data['position']['x']}, Y={memory_data['position']['y']}"
                            if last_values["position"] != position_str:
                                last_values["position"] = position_str
                                changed = True
                                changes.append(f"Position: {position_str}")
                            
                            # Check map change
                            if last_values["mapId"] != memory_data["mapId"]:
                                last_values["mapId"] = memory_data["mapId"]
                                changed = True
                                map_name = map_names.get(memory_data["mapId"], f"Unknown Map ({memory_data['mapId']})")
                                changes.append(f"Map: {map_name} (ID: {memory_data['mapId']})")
                            
                            # Only print if something changed
                            if changed:
                                print("\n--- Memory Data Update ---")
                                for change in changes:
                                    print(change)
                            
                        except json.JSONDecodeError as e:
                            print(f"Error parsing JSON data: {e}")
                            print(f"Raw content: {content}")
                
            except socket.timeout:
                # Just a timeout, continue the loop
                continue
            except socket.error as e:
                if e.args[0] != socket.EWOULDBLOCK and str(e) != 'Resource temporarily unavailable':
                    print(f"Socket error: {e}")
                    break
            except Exception as e:
                print(f"Error handling client: {e}")
                if not self.running:
                    break
                continue
        
        print(f"Disconnected from emulator at {client_address}")
        self.current_client = None
        try:
            client_socket.close()
        except:
            pass
    
    def start(self):
        """Start the controller server"""
        print("Starting Pokemon Memory Test Controller")
        
        try:
            while self.running:
                try:
                    print("Waiting for emulator connection...")
                    client_socket, client_address = self.server_socket.accept()
                    
                    # Start client handler in the main thread for simplicity
                    self.handle_client(client_socket, client_address)
                    
                except socket.timeout:
                    # Just a timeout, continue the loop
                    continue
                except KeyboardInterrupt:
                    print("Keyboard interrupt detected. Shutting down...")
                    break
                except Exception as e:
                    if self.running:  # Only log if we're still supposed to be running
                        print(f"Error in main loop: {e}")
                        # Short delay to prevent tight error loops
                        time.sleep(1)
        finally:
            # Ensure we clean up properly
            self.running = False
            self.cleanup()
            print("Server shut down cleanly")

if __name__ == "__main__":
    controller = MemoryTestController()
    try:
        controller.start()
    except KeyboardInterrupt:
        pass  # Already handled in signal_handler
    finally:
        controller.cleanup()