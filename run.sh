#!/bin/bash

# Exit on any error
set -e

# Navigate to the script's directory (optional but good if you run from elsewhere)
cd "$(dirname "$0")"

# Activate the virtual environment
if [ -f "env/bin/activate" ]; then
    source env/bin/activate
elif [ -f "env/Scripts/activate" ]; then
    source env/Scripts/activate
else
    echo "❌ Virtual environment not found!"
    exit 1
fi

# Run FastAPI with Uvicorn
exec uvicorn app:app --host 0.0.0.0 --port 5000
