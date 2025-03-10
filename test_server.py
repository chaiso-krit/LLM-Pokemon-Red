#!/usr/bin/env python3
"""
Simple test server that mainly sends A button presses to help
get through Pokémon Red's start menus
"""
import socket
import time
import os
import random

def main():
    # Make sure screenshots directory exists
    os.makedirs("data/screenshots", exist_ok=True)
    
    # Set up server
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    host = '127.0.0.1'
    port = 8888
    running = True  # Flag for server loop
    client = None  # Initialize client to None
    
    try:
        # First, try to kill any process using the port
        try:
            server.bind((host, port))
        except socket.error as e:
            print(f"Port {port} is already in use. Make sure no other scripts are running.")
            return
            
        server.listen(1)
        print(f"Server listening on {host}:{port}")
        
        print("Waiting for connection from mGBA...")
        client, address = server.accept()
        print(f"Connected to {address}")
        
        # Set non-blocking mode
        client.setblocking(0)
        
        counter = 0
        last_key_time = 0
        key_interval = 2  # seconds between key presses
        
        while running:
            try:
                # Check if there's incoming data
                data = client.recv(1024)
                if data:
                    message = data.decode('utf-8').strip()
                    print(f"Received: {message}")
            except socket.error as e:
                # Handle non-blocking socket error
                if e.args[0] in {10035, 35} or str(e) == 'Resource temporarily unavailable':
                    pass  # Expected for non-blocking sockets
                else:
                    print(f"Socket error: {e}")
                    break  # Exit the loop on socket error

            # Send a key press every few seconds
            current_time = time.time()
            if current_time - last_key_time > key_interval:
                # 80% chance to press A button
                if random.random() < 0.8:
                    key_to_send = 0  # A button
                else:
                    # Occasionally press other useful buttons
                    key_to_send = random.choice([0, 1, 3, 4, 5, 6, 7])  # A, B, START, direction keys
                
                print(f"Sending key press: {key_to_send}")
                try:
                    client.send(str(key_to_send).encode('utf-8') + b'\n')  # Add newline
                    last_key_time = current_time
                    counter += 1
                except:
                    print("Error sending key press")
                    break

            time.sleep(0.1)  # Prevent CPU hogging
            
    except KeyboardInterrupt:
        print("\nReceived KeyboardInterrupt. Shutting down server...")
        running = False
    except Exception as e:
        print(f"Unexpected Error: {e}")
    finally:
        if client:  # Only close if client was defined
            print("Closing client connection...")
            client.close()
        print("Closing server socket...")
        server.close()
        print("Server shut down successfully.")

if __name__ == "__main__":
    main()