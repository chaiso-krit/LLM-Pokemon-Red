#!/usr/bin/env python3
import socket
import threading
import time
import re
import logging
from queue import Queue
from collections import deque
from datetime import datetime
from typing import Optional, List, Dict, Any

class TwitchChatClient:
    """Client for connecting to Twitch chat and collecting messages."""
    
    def __init__(self, 
                 username: str, 
                 oauth_token: str, 
                 channel: str, 
                 max_chat_history: int = 50,
                 log_file: Optional[str] = None):
        """
        Initialize the Twitch chat client.
        
        Args:
            username: Twitch username for the bot
            oauth_token: OAuth token for authentication (format: oauth:xyz...)
            channel: Channel to join (format: #channelname)
            max_chat_history: Maximum number of messages to store in history
            log_file: Optional file path to log chat messages
        """
        self.server = 'irc.chat.twitch.tv'
        self.port = 6667
        self.username = username
        self.oauth_token = oauth_token
        self.channel = channel if channel.startswith('#') else f'#{channel}'
        
        # Message storage
        self.chat_history = deque(maxlen=max_chat_history)
        self.suggestion_queue = Queue()
        
        # Timestamp of last processed message
        self.last_message_timestamp = datetime.now()
        
        # Connection status
        self.socket = None
        self.is_running = False
        self.receive_thread = None
        
        # Set up logging
        self.setup_logging(log_file)
        
    def setup_logging(self, log_file: Optional[str] = None):
        """Set up logging configuration."""
        log_format = '%(asctime)s — %(message)s'
        date_format = '%Y-%m-%d_%H:%M:%S'
        
        if log_file:
            logging.basicConfig(
                level=logging.INFO,
                format=log_format,
                datefmt=date_format,
                handlers=[logging.FileHandler(log_file, encoding='utf-8')]
            )
        else:
            # Log to console if no file specified
            logging.basicConfig(
                level=logging.INFO,
                format=log_format,
                datefmt=date_format
            )
    
    def connect(self) -> bool:
        """Connect to Twitch IRC."""
        try:
            self.socket = socket.socket()
            self.socket.connect((self.server, self.port))
            
            # Ensure token has oauth: prefix
            token = self.oauth_token
            if not token.startswith('oauth:'):
                token = f'oauth:{token}'
                
            # Send authentication info
            self.socket.send(f"PASS {token}\n".encode('utf-8'))
            self.socket.send(f"NICK {self.username}\n".encode('utf-8'))
            self.socket.send(f"JOIN {self.channel}\n".encode('utf-8'))
                
            # Check if connection was successful
            resp = self.socket.recv(2048).decode('utf-8')
            logging.info(f"Connected to Twitch IRC: {self.channel}")
                
            if "Welcome" in resp or "successfully logged in" in resp or "JOIN" in resp:
                return True
            else:
                logging.error(f"Failed to connect: {resp}")
                return False
                
        except Exception as e:
            logging.error(f"Connection error: {e}")
            return False
    
    def start(self) -> bool:
        """Start receiving messages in a background thread."""
        if not self.socket:
            if not self.connect():
                return False
        
        self.is_running = True
        self.receive_thread = threading.Thread(target=self._receive_messages)
        self.receive_thread.daemon = True
        self.receive_thread.start()
        return True
    
    def stop(self):
        """Stop the client and close the connection."""
        self.is_running = False
        if self.receive_thread:
            self.receive_thread.join(timeout=1)
        
        if self.socket:
            self.socket.close()
            self.socket = None
            logging.info(f"Disconnected from Twitch IRC: {self.channel}")
    
    def _receive_messages(self):
        """Background thread to receive and process messages."""
        while self.is_running:
            try:
                data = self.socket.recv(2048).decode('utf-8')
                if not data:
                    logging.warning("No data received, reconnecting...")
                    self.connect()
                    continue
                
                # Handle PING messages to keep the connection alive
                if data.startswith('PING'):
                    self.socket.send("PONG\n".encode('utf-8'))
                    continue
                
                # Process each message (there might be multiple in one data packet)
                for line in data.split('\r\n'):
                    if not line:
                        continue
                    
                    self._process_message(line)
            
            except Exception as e:
                logging.error(f"Error receiving messages: {e}")
                time.sleep(1)  # Avoid tight loop on errors
                
                # Try to reconnect if socket is closed
                if self.is_running:
                    try:
                        self.connect()
                    except:
                        pass
    
    def _process_message(self, message: str):
        """Process a single IRC message."""
        try:
            # Check if this is a PRIVMSG (chat message)
            if "PRIVMSG" in message:
                # Parse username and message text
                match = re.search(r':(\w+)!.*@.*\.tmi\.twitch\.tv PRIVMSG #\w+ :(.*)', message)
                if match:
                    username, msg_text = match.groups()
                    timestamp = datetime.now()
                    
                    # Store in chat history
                    chat_entry = {
                        'timestamp': timestamp,
                        'username': username,
                        'message': msg_text
                    }
                    self.chat_history.append(chat_entry)
                    logging.info(f"[{self.channel}] {username}: {msg_text}")
                    
                    # All messages go into the suggestion queue for the AI to consider
                    self.suggestion_queue.put(chat_entry)
        except Exception as e:
            logging.error(f"Error processing message: {e}")
    
    def get_recent_messages(self, count: int = 10) -> List[Dict[str, Any]]:
        """Get the most recent chat messages."""
        messages = list(self.chat_history)
        return messages[-count:] if messages else []
    
    def get_suggestions(self, max_count: int = 5) -> List[Dict[str, Any]]:
        """Get pending suggestions from the queue (up to max_count)."""
        suggestions = []
        for _ in range(min(max_count, self.suggestion_queue.qsize())):
            if not self.suggestion_queue.empty():
                suggestions.append(self.suggestion_queue.get())
        return suggestions
    
    def send_message(self, message: str) -> bool:
        """Send a message to the Twitch chat channel."""
        try:
            if self.socket:
                self.socket.send(f"PRIVMSG {self.channel} :{message}\r\n".encode('utf-8'))
                return True
            return False
        except Exception as e:
            logging.error(f"Error sending message: {e}")
            return False
    
    def format_chat_summary(self, count: int = 10) -> str:
        """Format recent chat as a string for inclusion in the notepad."""
        recent_messages = self.get_recent_messages(count)
        if not recent_messages:
            return "No recent chat messages."
        
        formatted = "## Recent Twitch Chat:\n"
        for msg in recent_messages:
            timestamp = msg['timestamp'].strftime("%H:%M:%S")
            formatted += f"[{timestamp}] {msg['username']}: {msg['message']}\n"
        
        return formatted
    
    def format_all_chat(self, count: int = 10) -> str:
        """Format only new chat messages since the last call."""
        # Get messages newer than last_message_timestamp
        new_messages = []
        for msg in self.get_recent_messages(count=50):  # Check more messages to find new ones
            if msg['timestamp'] > self.last_message_timestamp:
                new_messages.append(msg)
        
        # Update the timestamp for next time
        if new_messages:
            self.last_message_timestamp = datetime.now()
        
        if not new_messages:
            return ""  # Return empty string if no new messages
        
        formatted = "## New Twitch Chat Messages:\n"
        for msg in new_messages:
            timestamp = msg['timestamp'].strftime("%H:%M:%S")
            formatted += f"[{timestamp}] {msg['username']}: {msg['message']}\n"
        
        return formatted


if __name__ == "__main__":
    # Example usage
    import os
    from dotenv import load_dotenv
    
    # Load environment variables
    load_dotenv()
    
    # Get credentials from environment variables
    username = os.getenv("TWITCH_USERNAME")
    oauth_token = os.getenv("TWITCH_OAUTH_TOKEN")
    channel = os.getenv("TWITCH_CHANNEL", "your_channel")
    
    # Create and start the client
    client = TwitchChatClient(
        username=username,
        oauth_token=oauth_token,
        channel=channel,
        log_file="twitch_chat.log"
    )
    
    if client.start():
        print(f"Started listening to {channel}")
        try:
            # Run for a while to test
            for _ in range(30):
                time.sleep(1)
                # Print any new suggestions
                suggestions = client.get_suggestions()
                if suggestions:
                    print("\nNew suggestions:")
                    for s in suggestions:
                        print(f"  {s['username']}: {s['message']}")
            
            print("\nChat summary:")
            print(client.format_chat_summary())
            
        finally:
            client.stop()
    else:
        print("Failed to connect to Twitch chat")