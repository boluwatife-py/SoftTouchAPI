from flask import Blueprint, request, jsonify
from googletrans import Translator, LANGUAGES
import re
from typing import Tuple, Optional
import time

translate_api = Blueprint('translate_api', __name__)

# Initialize translator with error handling
try:
    translator = Translator()
except Exception as e:
    raise RuntimeError(f"Failed to initialize Translator: {str(e)}")  # Caught by global handler if app startup fails

# Constants
VALID_LANGUAGES = set(LANGUAGES.keys())
MAX_BATCH_SIZE = 50
MAX_TEXT_LENGTH = 5000

def sanitize_text(text: str) -> str:
    """Sanitize input text by removing excessive whitespace."""
    return re.sub(r'\s+', ' ', text.strip())

def validate_text(text: Optional[str]) -> Tuple[bool, str]:
    """Validate input text."""
    if not isinstance(text, str):
        return False, "Text must be a string"
    sanitized = sanitize_text(text)
    if not sanitized:
        return False, "Text cannot be empty"
    if len(sanitized) > MAX_TEXT_LENGTH:
        return False, f"Text exceeds {MAX_TEXT_LENGTH} characters"
    return True, sanitized

def validate_language(lang: str) -> Tuple[bool, str]:
    """Validate language code."""
    lang = lang.lower()
    if lang not in VALID_LANGUAGES:
        return False, f"Unsupported language code: {lang}. Use ISO 639-1 codes (e.g., 'en', 'es')"
    return True, lang

@translate_api.route('/translate', methods=['POST'])
def translate_text():
    """
    Translate text to a target language.
    Request body (JSON):
    - text: string or list of strings (required)
    - dest: target language code (required, e.g., 'es')
    - src: source language code (optional, default='auto')
    Returns:
    - Single text: {translated_text, src, dest, total_processing_time}
    - Multiple texts: [{translated_text, src, dest, total_processing_time}, ...]
    """
    data = request.get_json(silent=True)
    if not data:
        raw_data = request.data.decode('utf-8')
        if not raw_data:
            return jsonify({'error': 'Request body is empty'}), 400
        try:
            import json
            data = json.loads(raw_data)
        except json.JSONDecodeError:
            return jsonify({'error': 'Invalid JSON format in request body'}), 400

    if not isinstance(data, dict):
        return jsonify({'error': 'Request body must be a JSON object'}), 400

    text = data.get('text')
    dest = data.get('dest')
    src = data.get('src', 'auto')

    # Validate required fields
    if text is None:
        return jsonify({'error': 'Missing "text" field'}), 400
    if dest is None:
        return jsonify({'error': 'Missing "dest" field'}), 400

    is_valid_dest, dest_or_error = validate_language(dest)
    if not is_valid_dest:
        return jsonify({'error': dest_or_error}), 400

    # Handle single string or list of strings
    texts = [text] if isinstance(text, str) else text
    if not isinstance(texts, list):
        return jsonify({'error': '"text" must be a string or list of strings'}), 400
    
    if len(texts) > MAX_BATCH_SIZE:
        return jsonify({'error': f'Batch size exceeds maximum of {MAX_BATCH_SIZE} texts'}), 400

    results = []
    start_time = time.time()
    for t in texts:
        is_valid_text, text_result = validate_text(t)
        if not is_valid_text:
            return jsonify({'error': text_result}), 400
        sanitized_text = text_result

        # Validate source language if provided
        src_to_use = src
        if src != 'auto':
            is_valid_src, src_or_error = validate_language(src)
            if not is_valid_src:
                return jsonify({'error': src_or_error}), 400
        else:
            detected = translator.detect(sanitized_text)  # Global handler catches failures
            src_to_use = detected.lang if detected.confidence > 0.9 else 'auto'

        # Perform translation
        translated = translator.translate(sanitized_text, src=src_to_use, dest=dest)  # Global handler catches failures
        results.append({
            'translated_text': translated.text,
            'src': src_to_use,
            'dest': dest,
        })

    processing_time = time.time() - start_time
    response = results[0] if isinstance(text, str) else results
    if isinstance(response, list):
        for item in response:
            item['total_processing_time'] = round(processing_time, 3)
    else:
        response['total_processing_time'] = round(processing_time, 3)

    return jsonify({
        'success': True,
        'results': response
    }), 200

@translate_api.route('/translate/detect', methods=['POST'])
def detect_language():
    """
    Detect the language of input text.
    Request body (JSON):
    - text: string (required)
    Returns:
    - {language, confidence, total_processing_time}
    """
    data = request.get_json(silent=True)
    if not data:
        raw_data = request.data.decode('utf-8')
        if not raw_data:
            return jsonify({'error': 'Request body is empty'}), 400
        try:
            import json
            data = json.loads(raw_data)
        except json.JSONDecodeError:
            return jsonify({'error': 'Invalid JSON format in request body'}), 400

    if not isinstance(data, dict):
        return jsonify({'error': 'Request body must be a JSON object'}), 400

    text = data.get('text')
    if text is None:
        return jsonify({'error': 'Missing "text" field'}), 400

    is_valid_text, text_result = validate_text(text)
    if not is_valid_text:
        return jsonify({'error': text_result}), 400
    sanitized_text = text_result

    start_time = time.time()
    detected = translator.detect(sanitized_text)  # Global handler catches failures
    processing_time = time.time() - start_time

    return jsonify({
        'success': True,
        'language': detected.lang,
        'confidence': round(detected.confidence, 3),
        'total_processing_time': round(processing_time, 3)  # Added processing time here
    }), 200

@translate_api.route('/translate/info', methods=['GET'])
def translate_info():
    """Return /translate endpoint info."""
    start_time = time.time()
    response = {
        'endpoint': '/api/translate/translate',
        'method': 'POST',
        'description': 'Translate text to a target language',
        'parameters': {
            'text': 'string or list of strings (required)',
            'dest': 'target language code (required, ISO 639-1, e.g., "es")',
            'src': 'source language code (optional, default="auto", ISO 639-1, e.g., "en")'
        },
        'returns': {
            'success': 'boolean',
            'results': 'object or array with {translated_text, src, dest, total_processing_time}'
        },
        'limits': {
            'max_batch_size': MAX_BATCH_SIZE,
            'max_text_length': MAX_TEXT_LENGTH
        }
    }
    processing_time = time.time() - start_time
    response['total_processing_time'] = round(processing_time, 3)  # Optional: added for consistency
    return jsonify(response), 200

@translate_api.route('/translate/detect/info', methods=['GET'])
def detect_info():
    """Return /translate/detect endpoint info."""
    start_time = time.time()
    response = {
        'endpoint': '/api/translate/translate/detect',
        'method': 'POST',
        'description': 'Detect the language of input text',
        'parameters': {
            'text': 'string (required)'
        },
        'returns': {
            'success': 'boolean',
            'language': 'detected language code (ISO 639-1)',
            'confidence': 'float (0 to 1)',
            'total_processing_time': 'float (seconds)'
        },
        'limits': {
            'max_text_length': MAX_TEXT_LENGTH
        },
        'available_languages': list(LANGUAGES.keys())  # Converted to list for JSON serialization
    }
    processing_time = time.time() - start_time
    response['total_processing_time'] = round(processing_time, 3)  # Optional: added for consistency
    return jsonify(response), 200