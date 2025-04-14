#!/bin/bash

# Exit if any command fails
set -e

# Activate the virtual environment
if [ -f "env/bin/activate" ]; then
    source env/bin/activate
elif [ -f "env/Scripts/activate" ]; then
    source env/Scripts/activate
else
    echo "Virtual environment not found!"
    exit 1
fi

# Optional: Print FFmpeg version
ffmpeg -version | head -n 1 || echo "FFmpeg not found"

# Start the Flask app using gunicorn
exec gunicorn app:app --bind 0.0.0.0:5000