# LLM-Pokemon-Red-Benchmark

> An AI benchmark that evaluates LLMs by having them play Pokémon Red through visual understanding and decision making

## Project Vision

This project challenges AI systems to play Pokémon Red by only seeing the game screen, just like a human would. It tests the AI's ability to understand visuals, make decisions, remember context, plan strategies, and adapt to changing situations - all valuable skills that translate to real-world AI applications.

## How It Works

1. **Game Emulator (mGBA)** runs Pokémon Red with a Lua script that:
   - Takes screenshots
   - Receives button commands from the controller
   - Executes those commands in the game

2. **Python Controller** bridges the emulator and AI:
   - Manages screenshots and the AI's memory notepad
   - Sends data to the chosen LLM
   - Returns the AI's decisions to the emulator

3. **LLM Provider** (Gemini, OpenAI, or Anthropic) acts as the "brain":
   - Analyzes game screenshots
   - Decides which buttons to press
   - Updates its notepad to track progress

## Quick Setup

1. **Install dependencies**:
```bash
pip install "google-generativeai>=0.3.0" pillow openai anthropic python-dotenv
```

2. **Set up your config**:
   - Run the setup script: `python setup.py`
   - Edit the created `.env` file with your API keys:

```
# API Keys
GEMINI_API_KEY=YOUR_KEY_HERE
OPENAI_API_KEY=YOUR_KEY_HERE
ANTHROPIC_API_KEY=YOUR_KEY_HERE

# Default provider
DEFAULT_LLM_PROVIDER=gemini

# Models
GEMINI_MODEL=gemini-2.0-flash
OPENAI_MODEL=gpt-4o
ANTHROPIC_MODEL=claude-3-sonnet-20240229
```

3. **Test your setup**:
```bash
python test_llm_provider.py
```

4. **Update the Lua script path**:
   - Open `script.lua` in any text editor
   - Find and change the following line to match your system's full path:
   ```lua
   local screenshotPath = "/YOUR/FULL/PATH/TO/LLM-Pokemon-Red-Benchmark/data/screenshots/screenshot.png"
   ```
   - Example: `local screenshotPath = "/Users/yourname/Documents/LLM-Pokemon-Red-Benchmark/data/screenshots/screenshot.png"`

5. **Run in the correct order**:
   - Start mGBA and load your Pokémon Red ROM
   - Start playing the game
   - In a separate terminal, run the controller:
   ```bash
   python controller.py
   ```
   - Return to mGBA, open Tools > Script Viewer
   - Load and run the `script.lua` file
   
   This sequence is important! The controller must be running before you activate the Lua script.

## Video Tutorial

For a visual guide to setting up and running the project, watch this tutorial:

🎬 [**Watch the Video on Loom**](https://www.loom.com/share/bf5114789d4a4a9fb6fefa5488e7a15f?sid=dbbdeb60-9f4f-4f39-af26-bd68f6935c5e)

## Supported LLM Providers

- Google Gemini (gemini-2.0-flash)
- OpenAI (GPT-4o)
- Anthropic Claude (claude-3-sonnet)

## Tips for Best Results

- Adjust the `decision_cooldown` in your config to match your LLM provider's rate limits
- Consider API costs when running extended benchmarks
- Try different LLMs to see their unique "play styles"

## Contributing

Contributions welcome! You can:
- Improve the code
- Add support for more LLMs
- Share benchmark results
- Create visualization tools

## License

MIT