# LLM-Pokemon-Red-Benchmark

> A comprehensive benchmark for evaluating advanced AI capabilities in a dynamic, visual environment

## Why This Benchmark Matters

This project provides a unique way to evaluate modern AI systems through gameplay - challenging LLMs to play Pokémon Red the way a human would. Unlike typical text-based benchmarks, this tests several critical dimensions of AI intelligence simultaneously:

- **Visual Understanding**: Can the AI interpret pixel-based game screens, recognize objects, and understand spatial relationships?
- **Intuitive Decision Making**: The AI must infer game rules and mechanics without explicit instructions
- **Context Memory**: Requires tracking progress, items, and goals across long time horizons
- **Strategic Planning**: Demands forward planning for team building, route planning, and battle strategies
- **Adaptability**: Tests how well AI can respond to unexpected game situations and recover from mistakes

By restricting the AI to only screenshots, memory and controller inputs, we create a standardized environment to compare different models on a complex, multi-step task that closely mirrors real-world problem-solving.

## How It Works

This project uses a combination of components to allow an AI to play Pokémon Red:

1. **Emulator with Lua Script**: The mGBA emulator runs Pokémon Red and uses a Lua script to:
   - Capture screenshots of the game
   - Send those screenshots to the Python controller
   - Receive button press commands
   - Execute those commands in the game

2. **Python Controller**: The controller acts as a bridge between the emulator and the LLM:
   - Receives screenshots from the emulator
   - Manages the notepad (game memory)
   - Sends the screenshots and notepad to the selected LLM
   - Gets decisions from the LLM (button presses and notepad updates)
   - Sends commands back to the emulator

3. **LLM Provider**: The "brain" of the system that:
   - Analyzes screenshots to understand the game state
   - Makes decisions about what to do next
   - Keeps track of its progress and goals in the notepad

## Benchmark Insights

Initial testing reveals fascinating differences between leading AI models:

 - Each model has their own strengths and weaknesses and display distinct "play styles" that reflect their underlying architecture and training.

 MORE RESULTS COMING SOON

## Supported LLM Providers

The system supports the following LLM providers:

- **Google Gemini** (gemini-2.0-flash, etc.)
- **OpenAI** (GPT-4o, etc.)
- **Anthropic Claude** (claude-3-sonnet, etc.)

## Setup and Configuration

### 1. Install Dependencies

```bash
pip install "google-generativeai>=0.3.0" pillow openai anthropic python-dotenv
```

### 2. Configure Environment Variables and LLM Provider

This project uses environment variables for sensitive information like API keys. You have two options for setup:

#### Option 1: Quick Setup (Recommended)

Run the setup script which will create all necessary files and directories:

```bash
python setup.py
```

Then edit the `.env` file to add your API keys:

```
# LLM API Keys
GEMINI_API_KEY=YOUR_GEMINI_API_KEY
OPENAI_API_KEY=YOUR_OPENAI_API_KEY
ANTHROPIC_API_KEY=YOUR_ANTHROPIC_API_KEY

# Default provider
DEFAULT_LLM_PROVIDER=gemini

# Model names
GEMINI_MODEL=gemini-2.0-flash
OPENAI_MODEL=gpt-4o
ANTHROPIC_MODEL=claude-3-sonnet-20240229
```

#### Option 2: Manual Setup

1. Create a `.env` file with your API keys (as shown above)
2. Run the config generator:
```bash
python config_loader.py
```

This will create a `config.json` file with your environment variables substituted.

### 3. Test Your LLM Provider

Before running the full system, you can test your LLM provider configuration. There are two easy ways to test:

#### Option 1: Using test_llm_provider.py

This performs a comprehensive test with detailed feedback:

```bash
python test_llm_provider.py
```

For more options:

```bash
python test_llm_provider.py --help
```

#### Option 2: Direct Provider Testing

For a quick test of a specific provider:

```bash
# Test Gemini
python llm_provider.py --provider gemini

# Test OpenAI
python llm_provider.py --provider openai

# Test Anthropic
python llm_provider.py --provider anthropic
```

You can also customize the test prompt:

```bash
python llm_provider.py --provider openai --prompt "Describe a Pikachu in one sentence"
```

These tests will confirm your API keys are working and that you can successfully connect to each LLM service.

### 4. Set Up the mGBA Emulator

1. Download and install [mGBA](https://mgba.io/downloads.html)
2. Load your Pokémon Red ROM
3. Open the Script Viewer (`Tools > Script Viewer`)
4. Load the `script.lua` file
5. Start the game

### 5. Run the Controller

```bash
python controller.py
```

## Standardized Benchmarking

One of the main features of this project is the ability to benchmark different LLMs under identical conditions:

1. Create separate config files for each provider:

   ```bash
   # For Gemini
   export DEFAULT_LLM_PROVIDER=gemini
   python config_loader.py config-gemini.json
   
   # For OpenAI
   export DEFAULT_LLM_PROVIDER=openai
   python config_loader.py config-openai.json
   
   # For Anthropic
   export DEFAULT_LLM_PROVIDER=anthropic
   python config_loader.py config-anthropic.json
   ```

   Or simply edit the `.env` file between runs to change `DEFAULT_LLM_PROVIDER`.

2. Run your benchmarks:
   ```bash
   python controller.py --config config-gemini.json
   # Play for a fixed timeframe or until reaching specific milestones
   
   python controller.py --config config-openai.json
   # Run with identical parameters
   
   python controller.py --config config-anthropic.json
   # Run with identical parameters
   ```

3. Evaluation Metrics:
   - **Progress Speed**: How quickly does the AI reach key game milestones?
   - **Exploration Efficiency**: Does the AI take optimal routes or wander aimlessly?
   - **Battle Strategy**: How effectively does the AI manage type advantages and team composition?
   - **Adaptation**: How well does the AI recover from mistakes or unexpected events?
   - **Memory Utilization**: Does the AI effectively use the notepad to track important information?

## Capabilities Evaluated

This benchmark tests a comprehensive set of AI capabilities that are relevant to real-world applications:

- **Visual Understanding**: Interpreting game screens mirrors document understanding in professional contexts
- **Sequential Decision Making**: Similar to workflow optimization and process automation
- **Long-term Memory**: Comparable to maintaining context in extended professional interactions
- **Strategic Thinking**: Reflects the planning needed in project management and resource allocation
- **Adaptability**: Tests how well AI can respond to changing conditions - critical for autonomous systems

## Tips for Optimal Performance

- Different LLMs have different strengths:
  - Gemini: Good at visual reasoning and navigation
  - GPT-4o: Strong at complex strategic planning
  - Claude: Excellent at tracking context and following instructions

- Each provider has different rate limits and costs:
  - Adjust the `decision_cooldown` parameter to match provider rate limits
  - Consider costs when benchmarking over longer periods

## Extending the System

### Adding New LLM Providers

To add a new LLM provider:

1. Update the `llm_provider.py` file with a new provider class
2. Implement the required methods (initialize, generate_content)
3. Update the factory function to return your new provider
4. Add the provider configuration to your `config.json`


## Contributing

Contributions are welcome! Here are some ways to get involved:
- Improve code base
- Run benchmarks with different models and share your results
- Add support for additional LLM providers
- Create visualization tools for benchmark results and gameplay

## Citation

If you use this benchmark in your research or evaluation, please cite:

```
@software{LLM-Pokemon-Red-Benchmark,
  author = Alejandro Martos Ayala,
  title = LLM-Pokemon-Red-Benchmark: A Dynamic Visual Reasoning Benchmark for LLMs,
  year = 2025,
  url = https://github.com/martoast/LLM-Pokemon-Red-Benchmark
}
```

## License

MIT