#!/bin/bash

# Exit on any error
set -e

python -m venv env
echo "Virtual environment created."

# Activate virtual environment (adjust if needed for Windows or your environment)
if [ -f "env/bin/activate" ]; then
    source env/bin/activate
elif [ -f "env/Scripts/activate" ]; then
    source env/Scripts/activate
else
    echo "Virtual environment not found! Please create one first."
    exit 1
fi

# === Install Tesseract OCR (for image text extraction) ===
# if command -v sudo >/dev/null 2>&1 && command -v apt >/dev/null 2>&1; then
#     echo "Installing Tesseract OCR system-wide with apt..."
#     sudo apt install -y tesseract-ocr
# else
#     echo "Please install Tesseract manually. Auto-install not supported for this system."
# fi

# Purge pip cache to ensure fresh installs
python -m pip cache purge

# Update pip to the latest version
python -m pip install --upgrade pip

# Install Python dependencies
python -m pip install git+https://github.com/openai/whisper.git werkzeug flask

# Install additional requirements from requirements.txt (if it exists)
if [ -f "requirements.txt" ]; then
    python -m pip install -r requirements.txt
fi

# Install spaCy English model
python -m spacy download en_core_web_sm

# === Install FFmpeg (for Whisper) ===
if command -v sudo >/dev/null 2>&1 && command -v apt >/dev/null 2>&1; then
    echo "Installing FFmpeg system-wide with apt..."
    sudo apt update
    sudo apt install -y ffmpeg
else
    echo "Installing FFmpeg locally..."
    FFmpeg_DIR="$HOME/ffmpeg"
    if ! command -v ffmpeg >/dev/null 2>&1; then
        wget -q https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz
        tar -xf ffmpeg-release-amd64-static.tar.xz
        mkdir -p "$FFmpeg_DIR"
        mv ffmpeg-*-static/ffmpeg "$FFmpeg_DIR/"
        mv ffmpeg-*-static/ffprobe "$FFmpeg_DIR/" || true
        rm -rf ffmpeg-*-static ffmpeg-release-amd64-static.tar.xz
        echo "export PATH=\"$FFmpeg_DIR:\$PATH\"" >> ~/.bashrc
        export PATH="$FFmpeg_DIR:$PATH"
    fi
fi

# Verify installations
echo "Verifying installations..."
ffmpeg -version | head -n 1 || echo "FFmpeg not in PATH"
tesseract --version | head -n 1 || echo "Tesseract not in PATH"

echo "Setup complete! Activate your environment and run the app."