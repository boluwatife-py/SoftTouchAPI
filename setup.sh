#!/bin/bash
pip3 install git+https://github.com/openai/whisper.git werkzeug
pip install -r requirements.txt
python -m spacy download en_core_web_sm
