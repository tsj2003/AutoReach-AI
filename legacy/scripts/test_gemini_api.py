#!/usr/bin/env python3
import os
import sys
import json
import urllib.request
import urllib.parse
from pathlib import Path

def verify_api_key(api_key: str, model: str = "gemini-2.0-flash") -> bool:
    print(f"Testing API key with model '{model}'...")
    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{urllib.parse.quote(model)}:generateContent"
        f"?key={urllib.parse.quote(api_key)}"
    )
    payload = {
        "contents": [{"parts": [{"text": "Hello, write a single word reply saying SUCCESS."}]}],
    }
    
    try:
        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            text = res_data["candidates"][0]["content"]["parts"][0]["text"].strip()
            print(f"\n✅ SUCCESS! Gemini responded: '{text}'")
            return True
    except urllib.error.HTTPError as e:
        print(f"\n❌ API request failed with HTTP Error {e.code}: {e.reason}")
        try:
            error_body = json.loads(e.read().decode("utf-8"))
            print("Error Details:", json.dumps(error_body, indent=2))
        except:
            pass
        return False
    except Exception as e:
        print(f"\n❌ Request failed: {e}")
        return False

def main():
    state_file = Path(".campaign_state.json")
    api_key = None
    model = "gemini-2.0-flash"
    
    if state_file.exists():
        try:
            with open(state_file) as f:
                state = json.load(f)
                api_key = state.get("gemini_api_key")
                model = state.get("personalization_model", model)
        except Exception as e:
            print(f"Warning: Could not read .campaign_state.json: {e}")
            
    if not api_key:
        api_key = os.getenv("GEMINI_API_KEY")
        
    if not api_key:
        print("No API key found in saved campaign state or GEMINI_API_KEY environment variable.")
        if len(sys.argv) > 1:
            api_key = sys.argv[1]
        else:
            api_key = input("Please enter your Gemini API key to test: ").strip()
            
    if not api_key:
        print("No key provided. Exiting.")
        sys.exit(1)
        
    success = verify_api_key(api_key, model)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
