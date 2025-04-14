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

python admin/create_admin.py
exec gunicorn app:app --bind 0.0.0.0:5000