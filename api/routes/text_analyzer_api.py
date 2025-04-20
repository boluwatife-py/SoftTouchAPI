from fastapi import APIRouter, HTTPException
from collections import Counter
import re, json, time, spacy
from typing import List, Optional
from pydantic import BaseModel, Field


text_api = APIRouter()

# Configure logging
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class AnalyzeRequest(BaseModel):
    text: str = Field(..., description="Text to analyze")
    num_keywords: int = Field(5, ge=1, le=20, description="Number of top keywords to extract (default is 5)")

class Entity(BaseModel):
    text: str
    label: str

class POSTag(BaseModel):
    text: str
    pos: str

class AnalyzeResponse(BaseModel):
    success: bool
    entities: List[Entity]
    keywords: List[str]
    word_count: int
    pos_tags: List[POSTag]
    processing_time: float

class SentimentRequest(BaseModel):
    text: str = Field(..., description="Text to analyze for sentiment")


class SentimentScores(BaseModel):
    polarity: float
    subjectivity: float

class SentimentLabels(BaseModel):
    polarity: str
    subjectivity: str

class SentimentResponse(BaseModel):
    success: bool
    sentiment: SentimentScores
    interpretation: SentimentLabels
    processing_time: float
    note: str


# Load spaCy model with error handling
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    return_error = {
        "error": "Failed to load spaCy model. Please ensure 'en_core_web_sm' is installed.",
        "solution": "Run: python -m spacy download en_core_web_sm"
    }
    
    raise RuntimeError(json.dumps(return_error))


def preprocess_text(text: str) -> str:
    """Clean and normalize text."""
    try:
        return re.sub(r'\s+', ' ', text.strip())
    except Exception as e:
        raise ValueError(f"Text preprocessing failed: {str(e)}")


def extract_keywords(text: str, num_keywords: int = 5) -> List[str]:
    """Extract top keywords based on frequency."""
    try:
        doc = nlp(preprocess_text(text.lower()))
        words = [token.text for token in doc if token.is_alpha and not token.is_stop and len(token.text) > 3]
        if not words:
            return []
        return [word for word, _ in Counter(words).most_common(min(num_keywords, len(set(words))))]
    except Exception as e:
        raise RuntimeError(f"Keyword extraction failed: {str(e)}")


def validate_input(text: Optional[str], max_length: int = 10000) -> tuple[bool, str]:
    """Validate input text."""
    try:
        if not isinstance(text, str):
            return False, "Text must be a string"
        if not text.strip():
            return False, "Text cannot be empty"
        if len(text) > max_length:
            return False, f"Text exceeds {max_length} characters"
        return True, ""
    except Exception as e:
        return False, f"Input validation error: {str(e)}"


@text_api.post('/v1/analyze')
def analyze_text(payload: AnalyzeRequest):
    """
    Analyze text for entities, keywords, word count, and POS tags.
    Request body (JSON):
    - text: string (required)
    - num_keywords: integer (optional, default=5)
    Returns:
    - entities: list of named entities
    - keywords: list of top keywords
    - word_count: total words
    - pos_tags: list of part-of-speech tags
    - processing_time: float (seconds)
    """
    text = payload.text
    num_keywords = payload.num_keywords

    is_valid, error_msg = validate_input(text)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

    start_time = time.time()
    text = preprocess_text(text)
    doc = nlp(text)

    entities = [{'text': ent.text, 'label': ent.label_} for ent in doc.ents][:5]
    keywords = extract_keywords(text, num_keywords)
    word_count = len([token for token in doc if not token.is_space])
    pos_tags = [{'text': token.text, 'pos': token.pos_} for token in doc][:10]
    processing_time = round(time.time() - start_time, 3)

    return AnalyzeResponse(
        success=True,
        entities=entities,
        keywords=keywords,
        word_count=word_count,
        pos_tags=pos_tags,
        processing_time=processing_time
    )

    

@text_api.post('/v1/sentiment')
def sentiment_analysis(payload: SentimentRequest):
    text = payload.text

    is_valid, error_msg = validate_input(text)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

    start_time = time.time()
    text = preprocess_text(text)
    doc = nlp(text)

    polarity = sum([token.sentiment for token in doc if token.sentiment]) / (len(doc) or 1)
    subjectivity = 0.5  # placeholder

    interpretation = {
        'polarity': 'positive' if polarity > 0.1 else 'negative' if polarity < -0.1 else 'neutral',
        'subjectivity': 'subjective' if subjectivity > 0.5 else 'objective'
    }

    return SentimentResponse(
        success=True,
        sentiment=SentimentScores(polarity=round(polarity, 3), subjectivity=subjectivity),
        interpretation=SentimentLabels(**interpretation),
        processing_time=round(time.time() - start_time, 3),
        note="Sentiment analysis is limited; consider integrating TextBlob or VADER for better results"
    )