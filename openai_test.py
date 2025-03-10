#!/usr/bin/env python3
"""
Simple test script to verify OpenAI connectivity
"""

import os
import sys
from dotenv import load_dotenv

def test_openai_connection():
    # Load API key from .env file
    load_dotenv()
    
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY not found in environment variables")
        return False
    
    print(f"Using API key: {api_key[:5]}...{api_key[-4:]}")
    
    try:
        # Try importing the OpenAI client
        print("Attempting to import OpenAI client...")
        
        # Check installed version
        try:
            import pkg_resources
            openai_version = pkg_resources.get_distribution("openai").version
            print(f"Installed OpenAI package version: {openai_version}")
        except Exception as e:
            print(f"Could not determine OpenAI package version: {e}")
        
        # Try different import approaches
        
        # Approach 1: Modern OpenAI client
        try:
            print("\nTrying modern import: from openai import OpenAI")
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            print("✅ Modern import successful")
            
            # Test API call
            print("Testing API call...")
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",  # Using a simpler model for testing
                messages=[
                    {"role": "user", "content": "Say 'Hello, I am connected to OpenAI!'"}
                ]
            )
            
            print(f"✅ API call successful. Response: {response.choices[0].message.content}")
            return True
            
        except Exception as e:
            print(f"❌ Error with modern import: {e}")
        
        # Approach 2: Legacy OpenAI client
        try:
            print("\nTrying legacy import: import openai")
            import openai
            
            # Set API key
            openai.api_key = api_key
            
            print("✅ Legacy import successful")
            
            # Test API call
            print("Testing API call...")
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "user", "content": "Say 'Hello, I am connected to OpenAI using legacy client!'"}
                ]
            )
            
            print(f"✅ API call successful. Response: {response.choices[0].message.content}")
            return True
            
        except Exception as e:
            print(f"❌ Error with legacy import: {e}")
        
        # If we got here, both approaches failed
        print("\n❌ Could not connect to OpenAI API.")
        return False
        
    except Exception as e:
        print(f"Unexpected error: {e}")
        return False

if __name__ == "__main__":
    print("OpenAI Connectivity Test")
    print("-----------------------")
    result = test_openai_connection()
    
    if result:
        print("\n✅ OpenAI connection test passed!")
        sys.exit(0)
    else:
        print("\n❌ OpenAI connection test failed.")
        print("\nTroubleshooting tips:")
        print("1. Check if you have the latest OpenAI package: pip install -U openai")
        print("2. Verify your API key is correct")
        print("3. Check your network connection")
        sys.exit(1)