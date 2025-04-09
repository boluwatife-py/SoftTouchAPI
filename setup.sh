#!/bin/bash

# Exit on any error
set -e

# Activate virtual environment (adjust if needed for Windows or your environment)
if [ -f "env/bin/activate" ]; then
    source env/bin/activate
elif [ -f "env/Scripts/activate" ]; then
    source env/Scripts/activate
else
    echo "Virtual environment not found! Please create one first."
    exit 1
fi

# Purge pip cache to ensure fresh installs
python -m pip cache purge

# Update pip to the latest version
python -m pip install --upgrade pip

# Install Python dependencies
# - OpenAI Whisper from GitHub (includes torch by default)
# - Werkzeug for secure_filename
# - Flask for the API
python -m pip install git+https://github.com/openai/whisper.git werkzeug flask

# Install additional requirements from requirements.txt (if it exists)
if [ -f "requirements.txt" ]; then
    python -m pip install -r requirements.txt
fi

# Install spaCy English model
python -m spacy download en_core_web_sm

# Install FFmpeg (required by Whisper for audio processing)
# Option 1: System-wide install (requires sudo)
if command -v sudo >/dev/null 2>&1 && command -v apt >/dev/null 2>&1; then
    echo "Installing FFmpeg system-wide with apt..."
    sudo apt update
    sudo apt install -y ffmpeg
else
    # Option 2: Install FFmpeg locally (no sudo required)
    echo "Sudo or apt not available, installing FFmpeg locally..."
    FFmpeg_DIR="$HOME/ffmpeg"
    if ! command -v ffmpeg >/dev/null 2>&1; then
        wget -q https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz
        tar -xf ffmpeg-release-amd64-static.tar.xz
        mkdir -p "$FFmpeg_DIR"
        mv ffmpeg-*-static/ffmpeg "$FFmpeg_DIR/"
        mv ffmpeg-*-static/ffprobe "$FFmpeg_DIR/" || true  # ffprobe is optional
        rm -rf ffmpeg-*-static ffmpeg-release-amd64-static.tar.xz
        # Add FFmpeg to PATH
        echo "export PATH=\"$FFmpeg_DIR:\$PATH\"" >> ~/.bashrc
        export PATH="$FFmpeg_DIR:$PATH"
    fi
fi

# Verify installations
echo "Verifying installations..."
python -c "import whisper; print('Whisper installed:', whisper.__version__)"
python -c "import flask; print('Flask installed:', flask.__version__)"
python -c "import werkzeug; print('Werkzeug installed:', werkzeug.__version__)"
ffmpeg -version | head -n 1 || echo "FFmpeg not in PATH, check installation"

echo "Setup complete! Activate your environment and run the app."
