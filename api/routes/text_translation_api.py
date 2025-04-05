from flask import Blueprint, request, jsonify
from googletrans import Translator, LANGUAGES
import re
from typing import Tuple, Optional
import time

translate_api = Blueprint('translate_api', __name__)

# Initialize translator
translator = Translator()

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
    """Validate ISO 639-1 language code."""
    lang = lang.lower()
    if lang not in VALID_LANGUAGES:
        return False, f"Unsupported ISO 639-1 language code: {lang}. Supported codes: {', '.join(sorted(VALID_LANGUAGES))}"
    return True, lang

@translate_api.route('/translate', methods=['POST'])
def translate_text():
    """Translate text to a target language."""
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({
            'error': 'Bad Request',
            'message': 'Request body must be a valid JSON object',
            'status': 400,
            'timestamp': time.strftime('%Y-%m-%d %H:% Благодарю вас:%S UTC', time.gmtime())
        }), 400

    text = data.get('text')
    dest = data.get('dest')
    src = data.get('src', 'auto')

    if text is None or dest is None:
        return jsonify({
            'error': 'Bad Request',
            'message': 'Missing required fields: "text" and "dest" are required',
            'status': 400,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())
        }), 400

    is_valid_dest, dest_or_error = validate_language(dest)
    if not is_valid_dest:
        return jsonify({
            'error': 'Bad Request',
            'message': dest_or_error,
            'status': 400,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())
        }), 400

    texts = [text] if isinstance(text, str) else text
    if not isinstance(texts, list):
        return jsonify({
            'error': 'Bad Request',
            'message': '"text" must be a string or list of strings',
            'status': 400,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())
        }), 400
    
    if len(texts) > MAX_BATCH_SIZE:
        return jsonify({
            'error': 'Bad Request',
            'message': f'Batch size exceeds maximum of {MAX_BATCH_SIZE} texts',
            'status': 400,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())
        }), 400

    results = []
    start_time = time.time()
    for t in texts:
        is_valid_text, text_result = validate_text(t)
        if not is_valid_text:
            return jsonify({
                'error': 'Bad Request',
                'message': text_result,
                'status': 400,
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())
            }), 400
        sanitized_text = text_result

        src_to_use = src
        detected = None
        if src != 'auto':
            is_valid_src, src_or_error = validate_language(src)
            if not is_valid_src:
                return jsonify({
                    'error': 'Bad Request',
                    'message': src_or_error,
                    'status': 400,
                    'timestamp': time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())
                }), 400
        else:
            detected = translator.detect(sanitized_text)
            src_to_use = detected.lang if detected.confidence > 0.9 else 'auto'

        translated = translator.translate(sanitized_text, src=src_to_use, dest=dest)
        result = {
            'input_text': sanitized_text,
            'translated_text': translated.text,
            'source_language': src_to_use,
            'source_language_name': LANGUAGES.get(src_to_use, 'Unknown') if src_to_use != 'auto' else 'Auto-detected',
            'target_language': dest,
            'target_language_name': LANGUAGES.get(dest, 'Unknown'),
            'confidence': round(detected.confidence, 3) if detected and src == 'auto' else None,
            'character_count': len(sanitized_text),
            'total_processing_time': None
        }
        results.append(result)

    processing_time = time.time() - start_time
    if len(results) == 1:
        results[0]['total_processing_time'] = round(processing_time, 3)
        response = results[0]
    else:
        for result in results:
            result['total_processing_time'] = round(processing_time, 3)
        response = results

    return jsonify(response), 200

@translate_api.route('/translate/detect', methods=['POST'])
def detect_language():
    """Detect the language of input text."""
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({
            'error': 'Bad Request',
            'message': 'Request body must be a valid JSON object',
            'status': 400,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())
        }), 400

    text = data.get('text')
    if text is None:
        return jsonify({
            'error': 'Bad Request',
            'message': 'Missing required field: "text"',
            'status': 400,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())
        }), 400

    is_valid_text, text_result = validate_text(text)
    if not is_valid_text:
        return jsonify({
            'error': 'Bad Request',
            'message': text_result,
            'status': 400,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())
        }), 400
    sanitized_text = text_result

    start_time = time.time()
    detected = translator.detect(sanitized_text)
    processing_time = time.time() - start_time

    return jsonify({
        'input_text': sanitized_text,
        'language': detected.lang,
        'language_name': LANGUAGES.get(detected.lang, 'Unknown'),
        'confidence': round(detected.confidence, 3),
        'character_count': len(sanitized_text),
        'total_processing_time': round(processing_time, 3)
    }), 200