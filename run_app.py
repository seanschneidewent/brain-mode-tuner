#!/usr/bin/env python3
"""
Brain Mode Tuner - Startup Script

Run this to start the application:
    python run_app.py

Then open http://localhost:8000 in your browser.
"""

import os
import sys
from pathlib import Path

# Ensure we're in the right directory
os.chdir(Path(__file__).parent)

# Check for .env file
env_file = Path(".env")
if not env_file.exists():
    print("=" * 60)
    print("WARNING: No .env file found!")
    print("=" * 60)
    print("\nCreating .env from .env.example...")
    
    example = Path(".env.example")
    if example.exists():
        env_file.write_text(example.read_text())
        print("Created .env file. Please edit it to add your GEMINI_API_KEY")
    else:
        env_file.write_text("GEMINI_API_KEY=your_key_here\n")
        print("Created .env file. Please add your GEMINI_API_KEY")
    
    print("\nEdit .env and run again.")
    sys.exit(1)

# Check for API key
from dotenv import load_dotenv
load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key or api_key == "your_gemini_api_key_here" or api_key == "your_key_here":
    print("=" * 60)
    print("WARNING: GEMINI_API_KEY not configured!")
    print("=" * 60)
    print("\nPlease edit .env and add your Gemini API key.")
    print("Get one at: https://aistudio.google.com/app/apikey")
    sys.exit(1)

# Start the server
print("=" * 60)
print("Brain Mode Tuner")
print("=" * 60)
print(f"\nData path: {os.getenv('DATA_PATH', 'D:\\MOCK DATA\\...')}")
print(f"API key: {api_key[:8]}...{api_key[-4:]}")
print("\nStarting server at http://localhost:8080")
print("Press Ctrl+C to stop\n")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8080, reload=False)
