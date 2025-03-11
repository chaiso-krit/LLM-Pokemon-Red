import logging
import colorama
from colorama import Fore, Back, Style

class PokemonLogger:
    """Custom logger for the Pokémon Game AI"""
    
    def __init__(self, debug_mode=False):
        """Initialize the logger with colorama for colored terminal output"""
        # Initialize colorama
        colorama.init(autoreset=True)
        
        # Set up logging format
        self.debug_mode = debug_mode
        
        # Create a basic logger
        logging.basicConfig(
            level=logging.INFO,
            format='%(message)s',
            handlers=[
                logging.StreamHandler(),  # Console handler
                logging.FileHandler("pokemon_ai.log")  # File handler
            ]
        )
        
        self.logger = logging.getLogger("Pokemon_AI")
        
        # Print header
        self.header("Pokémon Game AI Logger Initialized")
    
    def header(self, message):
        """Print a header message"""
        line = "=" * 80
        self.logger.info(f"\n{Fore.CYAN}{line}")
        self.logger.info(f"{Fore.CYAN}{Style.BRIGHT}{message.center(80)}")
        self.logger.info(f"{Fore.CYAN}{line}\n")
    
    def section(self, message):
        """Print a section header"""
        # Only print section headers if they're not "Waiting for emulator connection..."
        # to reduce noise in the logs
        if "Waiting for emulator connection" not in message:
            self.logger.info(f"\n{Fore.MAGENTA}{Style.BRIGHT}{message}")
            self.logger.info(f"{Fore.MAGENTA}{'-' * len(message)}")
    
    def info(self, message):
        """Log a normal info message"""
        self.logger.info(f"{Fore.WHITE}{message}")
    
    def game_state(self, message):
        """Log game state information"""
        # Only log game state if it's not a generic waiting message
        if "Waiting for game data" not in message:
            self.logger.info(f"{Fore.GREEN}🎮 {message}")
    
    def ai_thinking(self, thinking):
        """Log AI thinking process - always show full thinking"""
        if thinking:
            self.logger.info(f"{Fore.YELLOW}🤔 AI THINKING: {thinking}")
    
    def ai_action(self, button, button_index):
        """Log AI action (button press)"""
        button_colors = {
            "A": Fore.GREEN, 
            "B": Fore.RED,
            "START": Fore.BLUE,
            "SELECT": Fore.BLUE,
            "UP": Fore.CYAN,
            "DOWN": Fore.CYAN,
            "LEFT": Fore.CYAN,
            "RIGHT": Fore.CYAN
        }
        
        button_name = button.upper()
        color = button_colors.get(button_name, Fore.WHITE)
        
        self.logger.info(f"{color}👆 AI ACTION: Pressing {Style.BRIGHT}{button_name}{Style.NORMAL} (index: {button_index})")
    
    def notepad(self, content, truncate=150):
        """Log notepad updates"""
        if content and content.lower() != "no change":
            self.logger.info(f"{Fore.BLUE}📝 NOTEPAD UPDATE: {content}")
    
    def warning(self, message):
        """Log a warning message"""
        self.logger.info(f"{Fore.YELLOW}⚠️ {message}")
    
    def error(self, message):
        """Log an error message"""
        self.logger.info(f"{Fore.RED}❌ {message}")
    
    def success(self, message):
        """Log a success message"""
        self.logger.info(f"{Fore.GREEN}✅ {message}")
    
    def debug(self, message):
        """Log a debug message (only if debug_mode is True)"""
        if self.debug_mode:
            # Only log debug messages that aren't about screenshots
            if "Screenshot path" not in message:
                self.logger.info(f"{Fore.LIGHTBLACK_EX}🔍 DEBUG: {message}")
    
    def screenshot(self, path, filesize):
        """Log a screenshot capture - minimizing this output"""
        # Don't log every screenshot capture to reduce noise
        pass