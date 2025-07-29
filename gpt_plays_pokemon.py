import base64
import json
import time
import sys
import os

import pyjson5
import textwrap

#import pymongo
from pyboy import PyBoy
from pyboy.utils import WindowEvent
import requests

config_path = "config.json"
# Load config directly from JSON file
try:
    with open("config.json", 'r') as f:
        CONFIG = json.load(f)
except Exception as e:
    print(f"Failed to load config from {config_path}: {e}")
    sys.exit(1)

import PIL
import google.generativeai as genai

genai.configure(api_key=CONFIG["providers"]["google"]["api_key"])
client = genai
model = client.GenerativeModel(model_name=CONFIG["providers"]["google"]["model_name"])

# from openai import OpenAI

# client = OpenAI(api_key="XXXXXXX")

#from ollama import Client
#import pickle

#client = Client(host=CONFIG["providers"]["ollama"]["host"])
#client = Client()

load_savestate = False
# execute button presses
pyboy = PyBoy(CONFIG["gameboy_rom"])
pyboy.set_emulation_speed(3)

def read_notepad():
    """Read the current notepad content"""
    try:
        with open(CONFIG["tips_path"], 'r') as f:
            return f.read()
    except Exception as e:
        print(f"Error reading notepad: {e}")
        return "Error reading notepad"

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def loose_parse_json(json_string: str):


    json_substring = json_string[json_string.find("{") : json_string.rfind("}") + 1]

    return pyjson5.loads(json_substring)


def get_gpt_response(current_memory, turns, screenshot_path):
    #print("Promp",prompt)

    chat = model.start_chat(
            history=[
        {
            "role": "user", 
            "parts": [textwrap.dedent(
                """\
        You are currently playing Pokémon Yellow. You should output a JSON object containing the following keys:
        {
          thoughts: string;
          memory: any;
          buttons: ("A" | "B" | "UP" | "DOWN" | "LEFT" | "RIGHT" | "START")[];
        }
        
        "thoughts": A short string in which you should analyze the current situation and think step-by-step about what to do next. This will also serve as live commentary, read out to the YouTube audience.
        "memory": Arbitrary JSON containing notes to your future self. This should include both short and long term goals and important information you learn. This is the only information that will be passed to your future self, so you should include anything from the previous session that you still want to remember including any important lessons that you've learned while removing anything no longer relevant to save on token cost. For example, if something you've tried to achieve a goal has not worked many times in a row, you might want to record it in your memory for future reference.
        "buttons": A sequence of button presses you want to input into the game. These will be entered one second apart so you can safely navigate entire tiles or select menu options. To be efficient, try to plan ahead and input as many button presses in sequence as you can.
        
        Only output JSON. Do not include a Markdown block around it.
					"""
            )]},
        {
            "role": "user",
            "parts": [f"""Here is your current working memory in JSON: {json.dumps(current_memory)}"""],
        },
        {
            "role": "user",
            "parts": [f"""Here is information from expert: {read_notepad()}"""],
        },
        {
            "role": "user",
            "parts": [f"Next is the summary of your most recent turns. Study them closely. What did you intend to do? Did you succeed? What went wrong? What did you learn, and what should you do next?"],
        },
        {
            "role": "user",
            "parts": [f"Turn {turn['turn']}. Internal thoughts: {turn['thoughts']}; Button presses: {json.dumps(turn['buttons'])}." for turn in turns],   
        }
            
        ],
        )
          
    content_parts = [f"The screenshot is the current in-game situation. Respond accordingly."]

    original_image = PIL.Image.open(screenshot_path)
            
    # Scale the image to 3x its original size for better detail recognition
    scale_factor = 3
    scaled_width = original_image.width * scale_factor
    scaled_height = original_image.height * scale_factor
    scaled_image = original_image.resize((scaled_width, scaled_height), PIL.Image.LANCZOS)
    
    content_parts.append(scaled_image)
        
    response = chat.send_message(
            content=content_parts,
            generation_config={
                "max_output_tokens": 1024
            },
        )

    # completion = client.chat(
    #             model="gemma3",
    #             messages=prompt,
    #         )
    
    # completion = client.chat.completions.create(
    #     model="gpt-4-vision-preview",
    #     messages=prompt,
    #     max_tokens=1024,
    #     # response_format={"type": "json_object"},
    # )

    #print(response)

    try:
        if hasattr(response, "text"):
            return response.text
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

    # for now, return dummy json
    # return json.dumps(
    #     {
    #         "thoughts": "No thoughts so far, just placeholders.",
    #         "memory": {"head": "empty"},
    #         "buttons": ["A", "A"],
    #     }
    # )


def get_commentary(thoughts, turn_number):
    commentary_path = f"commentary/thoughts{turn_number:09}.mp3"

    response = client.audio.speech.create(model="tts-1", voice="echo", input=thoughts)

    response.stream_to_file(commentary_path)

    # for now, just copy dummy mp3 to commentary folder
    # with open(commentary_path, "wb") as f:
    #     f.write(open("speech.mp3", "rb").read())

    return commentary_path


def main():
    global load_savestate
    # connect to local mongo
    #client = pymongo.MongoClient("localhost", 27017)
    #turns = client["pokemon"].turns.find().sort("turn", pymongo.DESCENDING).limit(5)
    # grab 10 most recent turns from the database
    turns_list = []
    try:
        turn_file_load = open('data/turns.pkl', 'rb')
        turns_list = pickle.load(turn_file_load)
        turn_file_load.close()
        turns = turns_list[-5:]
    except:
        turns = [{
            "turn": 0,
            "thoughts": "",
            "memory": "",
            "buttons": "",
            "screenshot_index": 0,
            "screenshots": ["data/screenshots/screenshot_0000000.png"],
            "savestate": "data/savestates/state_0000000.save",
        }]

    most_recent_turn = turns[-1]
    current_memory = most_recent_turn["memory"]

    gpt_response = loose_parse_json(get_gpt_response(current_memory, turns, most_recent_turn["screenshots"][-1]))

    #print(gpt_response)

    new_thoughts = gpt_response["thoughts"]
    new_memory = gpt_response["memory"]
    new_buttons: list[str] = gpt_response["buttons"]

    print("Thought:", new_thoughts)
    print("Memory:", new_memory)
    print("Buttons:", new_buttons)

    current_screenshot_index = most_recent_turn["screenshot_index"]

    current_screenshot_index += 1

    next_turn = {
        "turn": most_recent_turn["turn"] + 1,
        "thoughts": new_thoughts,
        "memory": new_memory,
        "buttons": new_buttons,
        "screenshot_index": current_screenshot_index + len(new_buttons),
        "screenshots": [],
        "savestate": "",
    }

    if not load_savestate and "savestate" in most_recent_turn:
        pyboy.load_state(open(most_recent_turn["savestate"], "rb"))
        load_savestate = True

    for button in new_buttons:
        if button.upper().startswith("A"):
            pyboy.send_input(WindowEvent.PRESS_BUTTON_A)
            pyboy.tick()
            pyboy.tick()
            pyboy.tick()
            pyboy.send_input(WindowEvent.RELEASE_BUTTON_A)
            pyboy.tick()
        elif button.upper().startswith("B"):
            pyboy.send_input(WindowEvent.PRESS_BUTTON_B)
            pyboy.tick()
            pyboy.tick()
            pyboy.tick()
            pyboy.send_input(WindowEvent.RELEASE_BUTTON_B)
            pyboy.tick()
        elif button.upper().startswith("UP"):
            pyboy.send_input(WindowEvent.PRESS_ARROW_UP)
            pyboy.tick()
            pyboy.tick()
            pyboy.tick()
            if next_turn["turn"] >= 29:
                for _ in range(5):
                    pyboy.tick()
            pyboy.send_input(WindowEvent.RELEASE_ARROW_UP)
            pyboy.tick()
        elif button.upper().startswith("DOWN"):
            pyboy.send_input(WindowEvent.PRESS_ARROW_DOWN)
            pyboy.tick()
            pyboy.tick()
            pyboy.tick()
            if next_turn["turn"] >= 29:
                for _ in range(8):
                    pyboy.tick()
            pyboy.send_input(WindowEvent.RELEASE_ARROW_DOWN)
            pyboy.tick()
        elif button.upper().startswith("LEFT"):
            pyboy.send_input(WindowEvent.PRESS_ARROW_LEFT)
            pyboy.tick()
            pyboy.tick()
            pyboy.tick()
            if next_turn["turn"] >= 29:
                for _ in range(8):
                    pyboy.tick()
            pyboy.send_input(WindowEvent.RELEASE_ARROW_LEFT)
            pyboy.tick()
        elif button.upper().startswith("RIGHT"):
            pyboy.send_input(WindowEvent.PRESS_ARROW_RIGHT)
            pyboy.tick()
            pyboy.tick()
            pyboy.tick()
            if next_turn["turn"] >= 29:
                for _ in range(8):
                    pyboy.tick()
            pyboy.send_input(WindowEvent.RELEASE_ARROW_RIGHT)
            pyboy.tick()
        elif button.upper().startswith("START"):
            pyboy.send_input(WindowEvent.PRESS_BUTTON_START)
            pyboy.tick()
            pyboy.tick()
            pyboy.tick()
            pyboy.send_input(WindowEvent.RELEASE_BUTTON_START)
            pyboy.tick()
        else:
            print("Invalid button input")
        for i in range(1_000):
            pyboy.tick()

        pil_image = pyboy.screen.image.copy()
        screenshot_path = f"data/screenshots/screenshot_mini.png"
        pil_image.save(screenshot_path)
        current_screenshot_index += 1

        next_turn["screenshots"].append(screenshot_path)

    savestate_path = f"data/savestates/state_{most_recent_turn['turn'] + 1:07}.save"
    pyboy.save_state(open(savestate_path, "wb"))
    next_turn["savestate"] = savestate_path

    turns_list.append(next_turn)

    turn_file_save = open('data/turns.pkl', 'wb')
    pickle.dump(turns_list, turn_file_save)
    turn_file_save.close()
    #client["pokemon"].turns.insert_one(next_turn)

    #commentary_file = get_commentary(next_turn["thoughts"], next_turn["turn"])

    # Discord webhook
    webhook_url = "https://discord.com/api/webhooks/XXXXXXX"

    data = {
        "content": f"""Turn {next_turn['turn']}: {next_turn['thoughts']}
Buttons: {",".join("`" + button + "`" for button in next_turn['buttons'])}
Memory: 
```json
{json.dumps(next_turn['memory'], indent=2)}
```
        """
    }

    #print(data)

    # requests.post(
    #     webhook_url,
    #     files={
    #         "payload_json": (None, json.dumps(data), "application/json"),
    #         **{
    #             f"file{i}": (f"file{i}.png", open(screenshot_path, "rb"), "image/png")
    #             for i, screenshot_path in enumerate(next_turn["screenshots"][-8:])
    #         },
    #         "commentary": (
    #             commentary_file.split("/")[-1],
    #             open(commentary_file, "rb"),
    #             "audio/mpeg",
    #         ),
    #     },
    # )


if __name__ == "__main__":
    for i in range(10):
        try:
            main()
        except Exception as e:
            print(f"Exception occurred on turn {i}: {e}")

        print(f"Turn {i} complete. Waiting 5 seconds...")
        time.sleep(5)
