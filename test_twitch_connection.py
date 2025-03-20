#!/usr/bin/env python3
import time
import json
import os
from twitch_chat_client import TwitchChatClient

def test_twitch_connection():
    """Test the Twitch chat connection with credentials from config file."""
    print("=" * 80)
    print(" Testing Twitch Chat Connection")
    print("=" * 80)
    
    # Load config
    config_file = "twitch_config.json"
    if not os.path.exists(config_file):
        config_file = "config.json"
        if not os.path.exists(config_file):
            print(f"Error: Neither twitch_config.json nor config.json found!")
            return False
    
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
            
        twitch_config = config.get('twitch', {})
        if not twitch_config:
            print(f"Error: No Twitch configuration found in {config_file}")
            return False
            
        # Extract credentials
        username = twitch_config.get('username')
        oauth_token = twitch_config.get('oauth_token')
        channel = twitch_config.get('channel')
        
        if not all([username, oauth_token, channel]):
            print("Error: Missing required Twitch credentials!")
            return False
            
        print(f"Connecting to Twitch as: {username}")
        print(f"Channel: {channel}")
        
        # Create and start client
        client = TwitchChatClient(
            username=username,
            oauth_token=oauth_token,
            channel=channel,
            log_file=None  # Log to console for testing
        )
        
        if not client.connect():
            print("Failed to connect to Twitch chat! Check your credentials.")
            return False
            
        print("\n✅ Successfully connected to Twitch chat!")
        print("Listening for messages for 60 seconds...")
        
        # Start message reception
        client.start()
        
        # Send a test message
        client.send_message("Hello! This is a test message from the AI Pokemon player.")
        
        # Listen for messages
        try:
            for i in range(60):
                time.sleep(1)
                if i % 10 == 0:
                    print(f"{60-i} seconds remaining...")
                
                # Print any new suggestions
                suggestions = client.get_suggestions()
                if suggestions:
                    print("\nNew suggestions:")
                    for s in suggestions:
                        print(f"  {s['username']}: {s['message']}")
                        
                # Print all new messages every 5 seconds
                if i % 5 == 0:
                    recent = client.get_recent_messages(5)
                    if recent:
                        print("\nRecent messages:")
                        for msg in recent:
                            print(f"  {msg['username']}: {msg['message']}")
        
        except KeyboardInterrupt:
            print("\nTest interrupted by user.")
        finally:
            client.stop()
            print("\nTest completed. Connection closed.")
        
        return True
        
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    test_twitch_connection()