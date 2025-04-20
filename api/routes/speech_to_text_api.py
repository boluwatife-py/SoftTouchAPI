from fastapi import APIRouter, UploadFile, Form, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, constr
from typing import Optional
import whisper
import os
import time
import shutil
from tempfile import NamedTemporaryFile

transcribe_api = APIRouter()

MODEL_NAME = "small"
MODEL_CACHE_DIR = "whisper_model"

# Load Whisper model
try:
    os.makedirs(MODEL_CACHE_DIR, exist_ok=True)
    model = whisper.load_model(MODEL_NAME, download_root=MODEL_CACHE_DIR)
except Exception as e:
    raise RuntimeError(f"Failed to load Whisper model: {str(e)}")

ALLOWED_EXTENSIONS = {'.mp3', '.wav', '.m4a'}

def validate_file(filename: str, language: Optional[str] = None) -> tuple[bool, str]:
    if not filename or not any(filename.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS):
        return False, f"Invalid or missing file. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
    if language and len(language) != 2:
        return False, "Language must be a 2-character ISO code (e.g., 'en')"
    return True, ""

@transcribe_api.post("/v1/transcribe", response_class=PlainTextResponse)
async def transcribe_audio(
    audio: UploadFile,
    language: Optional[str] = Form(default=None)
):
    """
    Transcribe audio file using Whisper.
    - **audio**: File upload (required)
    - **language**: Optional 2-char ISO code (e.g., 'en')
    Returns:
    - Plain text transcription
    """
    is_valid, error_msg = validate_file(audio.filename, language)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

    start_time = time.time()

    try:
        # Save file temporarily
        with NamedTemporaryFile(delete=False, suffix=os.path.splitext(audio.filename)[-1]) as tmp:
            shutil.copyfileobj(audio.file, tmp)
            temp_path = tmp.name

        # Run Whisper transcription
        options = {"language": language} if language else {}
        result = model.transcribe(temp_path, **options)
        transcription = result['text']

        os.remove(temp_path)
        return transcription

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")
