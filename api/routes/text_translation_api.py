from fastapi import APIRouter
from googletrans import Translator, LANGUAGES
from pydantic import BaseModel, Field, field_validator
import re
from typing import List, Optional, Tuple, Union
import time

translate_api = APIRouter()
translator = Translator()


VALID_LANGUAGES = set(LANGUAGES.keys())
MAX_BATCH_SIZE = 50
MAX_TEXT_LENGTH = 5000

class TranslateRequest(BaseModel):
    text: Union[str, List[str]] = Field(..., description="Text to be translated (string or list of strings)")
    dest: str = Field(..., description="Target language code (ISO 639-1)")
    src: str = Field("auto", description="Source language code (ISO 639-1), defaults to 'auto'")

    @field_validator('text', mode='before')
    @classmethod
    def validate_text(cls, v):
        if isinstance(v, str):
            return [v]
        elif isinstance(v, list) and all(isinstance(i, str) for i in v):
            return v
        raise ValueError("Text must be a string or a list of strings")


class DetectRequest(BaseModel):
    text: str = Field(..., description="Text to detect the language of")

    @field_validator('text')
    @classmethod
    def validate_text(cls, v):
        if not isinstance(v, str):
            raise ValueError("Text must be a string")
        return v


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


def error_response(message: str):
    return {
        'error': 'Bad Request',
        'message': message,
        'status': 400,
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())
    }


@translate_api.post('/v1/translate')
async def translate_text(data: TranslateRequest):
    """Translate text to a target language."""
    texts = data.text  # Already a list due to validator
    dest = data.dest
    src = data.src or 'auto'

    # Validate destination language
    is_valid_dest, dest_or_error = validate_language(dest)
    if not is_valid_dest:
        return error_response(dest_or_error)

    # Validate batch size
    if len(texts) > MAX_BATCH_SIZE:
        return error_response(f'Batch size exceeds maximum of {MAX_BATCH_SIZE} texts')

    results = []
    start_time = time.time()

    for t in texts:
        # Validate and sanitize text
        is_valid_text, text_result = validate_text(t)
        if not is_valid_text:
            return error_response(text_result)
        sanitized_text = text_result

        detected = None
        src_to_use = src

        # Handle language detection if needed
        if src == 'auto':
            detected = await translator.detect(sanitized_text)
            src_to_use = detected.lang if detected.confidence > 0.9 else 'auto'
        else:
            is_valid_src, src_or_error = validate_language(src)
            if not is_valid_src:
                return error_response(src_or_error)

        # Perform translation
        translated = await translator.translate(sanitized_text, src=src_to_use, dest=dest)

        results.append({
            'input_text': sanitized_text,
            'translated_text': translated.text,
            'source_language': src_to_use,
            'source_language_name': LANGUAGES.get(src_to_use, 'Unknown') if src_to_use != 'auto' else 'Auto-detected',
            'target_language': dest,
            'target_language_name': LANGUAGES.get(dest, 'Unknown'),
            'confidence': round(detected.confidence, 3) if detected else None,
            'character_count': len(sanitized_text),
            'total_processing_time': None
        })

    processing_time = round(time.time() - start_time, 3)

    if len(results) == 1:
        results[0]['total_processing_time'] = processing_time
        return results[0]
    else:
        for r in results:
            r['total_processing_time'] = processing_time
        return results


@translate_api.post('/v1/translate/detect')
async def detect_language(data: DetectRequest):
    """Detect the language of input text."""
    
    text = data.text
    if text is None:
        return {
            'error': 'Bad Request',
            'message': 'Missing required field: "text"',
            'status': 400,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())
        }

    is_valid_text, text_result = validate_text(text)
    if not is_valid_text:
        return {
            'error': 'Bad Request',
            'message': text_result,
            'status': 400,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())
        }
    sanitized_text = text_result

    start_time = time.time()
    detected = await translator.detect(sanitized_text)
    processing_time = time.time() - start_time

    return {
        'input_text': sanitized_text,
        'language': detected.lang,
        'language_name': LANGUAGES.get(detected.lang, 'Unknown'),
        'confidence': round(detected.confidence, 3),
        'character_count': len(sanitized_text),
        'total_processing_time': round(processing_time, 3)
    }
