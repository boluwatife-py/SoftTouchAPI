from flask import Blueprint, request, jsonify
import whisper
import os
import traceback
import time
from werkzeug.utils import secure_filename
from typing import Optional

transcribe_api = Blueprint('transcribe_api', __name__)


MODEL_NAME = "small"
MODEL_CACHE_DIR = "whisper_model"


try:
    os.makedirs(MODEL_CACHE_DIR, exist_ok=True)
    model = whisper.load_model(MODEL_NAME, download_root=MODEL_CACHE_DIR)
except Exception as e:
    raise RuntimeError(f"Failed to load Whisper model: {str(e)}")

# Allowed file extensions
ALLOWED_EXTENSIONS = {'.mp3', '.wav', '.m4a'}

def validate_input(file: Optional[object], language: Optional[str] = None) -> tuple[bool, str]:
    """Validate input parameters."""
    try:
        if not file or 'audio' not in request.files:
            return False, "No audio file provided"
        if file.filename == '':
            return False, "No file selected"
        if not any(file.filename.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS):
            return False, f"Invalid file type. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
        if language is not None and (not isinstance(language, str) or len(language) != 2):
            return False, "Language must be a 2-character ISO code (e.g., 'en')"
        return True, ""
    except Exception as e:
        return False, f"Input validation error: {str(e)}"

@transcribe_api.route('/v1/transcribe', methods=['POST'])
def api_transcribe():
    """
    API endpoint to transcribe audio to text using Whisper.
    Request body (multipart/form-data):
    - audio: file (required)
    - language: string (optional, e.g., 'en')
    Returns:
    - Plain text string containing the transcription
    """
    try:
        audio_file = request.files.get('audio')
        language = request.form.get('language', None)
        
        # Validate input
        is_valid, error_msg = validate_input(audio_file, language)
        if not is_valid:
            return jsonify({'success': False, 'error': error_msg}), 400
        
        start_time = time.time()
        
        # Save the uploaded file temporarily
        temp_path = f"temp_{secure_filename(audio_file.filename)}"
        audio_file.save(temp_path)
        
        # Transcribe the audio
        options = {"language": language} if language else {}
        result = model.transcribe(temp_path, **options)
        transcription = result['text']
        
        # Clean up temporary file
        os.remove(temp_path)
        
        # Return transcription as plain text
        return transcription, 200, {'Content-Type': 'text/plain'}
    
    except ValueError as ve:
        return jsonify({'success': False, 'error': str(ve)}), 400