from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from googletrans import Translator, LANGUAGES
from pydantic import BaseModel, Field, validator
import re
from typing import List, Optional, Tuple
import time

app = FastAPI()
translator = Translator()

# Constants
VALID_LANGUAGES = set(LANGUAGES.keys())
MAX_BATCH_SIZE = 50
MAX_TEXT_LENGTH = 5000


# Pydantic Models
class TranslateRequest(BaseModel):
    text: str | List[str]
    dest: str
    src: str = "auto"

    @validator("dest")
    def validate_destination_language(cls, dest: str) -> str:
        dest = dest.lower()
        if dest not in VALID_LANGUAGES:
            raise ValueError(
                f"Unsupported ISO 639-1 language code: {dest}. Supported codes: {', '.join(sorted(VALID_LANGUAGES))}"
            )
        return dest

    @validator("src")
    def validate_source_language(cls, src: str) -> str:
        src = src.lower()
        if src != "auto" and src not in VALID_LANGUAGES:
            raise ValueError(
                f"Unsupported ISO 639-1 language code: {src}. Supported codes: {', '.join(sorted(VALID_LANGUAGES))}"
            )
        return src

    @validator("text")
    def validate_text_input(cls, text: str | List[str]) -> str | List[str]:
        if isinstance(text, str):
            if not validate_text(text)[0]:
                raise ValueError(validate_text(text)[1])
            if len(text) > MAX_TEXT_LENGTH:
                raise ValueError(f"Text exceeds {MAX_TEXT_LENGTH} characters")
            return text
        if len(text) > MAX_BATCH_SIZE:
            raise ValueError(f"Batch size exceeds maximum of {MAX_BATCH_SIZE} texts")
        for t in text:
            if not validate_text(t)[0]:
                raise ValueError(validate_text(t)[1])
        return text


class DetectRequest(BaseModel):
    text: str

    @validator("text")
    def validate_text_input(cls, text: str) -> str:
        if not validate_text(text)[0]:
            raise ValueError(validate_text(text)[1])
        return text


# Utility Functions
def sanitize_text(text: str) -> str:
    """Sanitize input text by removing excessive whitespace."""
    return re.sub(r"\s+", " ", text.strip())


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


# Custom Exception Handler for Pydantic Validation Errors
@app.exception_handler(ValueError)
async def validation_exception_handler(request: Request, exc: ValueError):
    return JSONResponse(
        status_code=400,
        content={
            "error": "Bad Request",
            "message": str(exc),
            "status": 400,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        },
    )


# API Endpoints
@app.post("/v1/translate")
async def translate_text(request: TranslateRequest):
    """Translate text to a target language."""
    texts = [request.text] if isinstance(request.text, str) else request.text
    results = []
    start_time = time.time()

    for t in texts:
        sanitized_text = sanitize_text(t)
        src_to_use = request.src
        detected = None

        if request.src == "auto":
            detected = translator.detect(sanitized_text)
            src_to_use = detected.lang if detected.confidence > 0.9 else "auto"

        translated = translator.translate(
            sanitized_text, src=src_to_use, dest=request.dest
        )
        result = {
            "input_text": sanitized_text,
            "translated_text": translated.text,
            "source_language": src_to_use,
            "source_language_name": (
                LANGUAGES.get(src_to_use, "Unknown")
                if src_to_use != "auto"
                else "Auto-detected"
            ),
            "target_language": request.dest,
            "target_language_name": LANGUAGES.get(request.dest, "Unknown"),
            "confidence": (
                round(detected.confidence, 3) if detected and request.src == "auto" else None
            ),
            "character_count": len(sanitized_text),
            "total_processing_time": None,
        }
        results.append(result)

    processing_time = time.time() - start_time
    if len(results) == 1:
        results[0]["total_processing_time"] = round(processing_time, 3)
        response = results[0]
    else:
        for result in results:
            result["total_processing_time"] = round(processing_time, 3)
        response = results

    return response


@app.post("/v1/translate/detect")
async def detect_language(request: DetectRequest):
    """Detect the language of input text."""
    sanitized_text = sanitize_text(request.text)
    start_time = time.time()
    detected = translator.detect(sanitized_text)
    processing_time = time.time() - start_time

    return {
        "input_text": sanitized_text,
        "language": detected.lang,
        "language_name": LANGUAGES.get(detected.lang, "Unknown"),
        "confidence": round(detected.confidence, 3),
        "character_count": len(sanitized_text),
        "total_processing_time": round(processing_time, 3),
    }