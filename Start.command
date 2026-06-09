#!/bin/bash

# YouTube Auto-Clipper — Launcher
# Double-click this file to start the app

cd "$(dirname "$0")"

echo "=============================="
echo "  YouTube Auto-Clipper"
echo "=============================="
echo ""

# Check Python is installed
if ! command -v python3 &>/dev/null; then
  echo "ERROR: Python 3 is not installed."
  echo "Download it from https://www.python.org/downloads/"
  read -p "Press Enter to close..."
  exit 1
fi

# Check FFmpeg is installed
if ! command -v ffmpeg &>/dev/null; then
  echo "FFmpeg not found. Installing via Homebrew..."
  if ! command -v brew &>/dev/null; then
    echo "Installing Homebrew first..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  fi
  brew install ffmpeg
fi

# Install Python packages if needed
echo "Checking dependencies..."
pip3 install -q -r requirements.txt

# Set OpenAI API key if provided in .env file
if [ -f ".env" ]; then
  export $(grep -v '^#' .env | xargs)
fi

echo ""
echo "Starting app... browser will open automatically."
echo "Press Ctrl+C to stop."
echo ""

python3 app.py
