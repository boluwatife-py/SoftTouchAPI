from flask import Blueprint, request, jsonify
from collections import Counter
import re, json, time, traceback, spacy
from typing import List, Dict, Optional

text_api = Blueprint('text_api', __name__)

# Load spaCy model with error handling
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    return_error = {
        "error": "Failed to load spaCy model. Please ensure 'en_core_web_sm' is installed.",
        "solution": "Run: python -m spacy download en_core_web_sm"
    }
    raise RuntimeError(jsonify(return_error))

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

def handle_exception(e):
    """Generate JSON error response from exception."""
    return jsonify({
        'error': str(e),
        'traceback': traceback.format_exc() if isinstance(e, Exception) else None
    }), 500

@text_api.route('/analyze', methods=['POST'])
def analyze_text():
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
    try:
        data = request.get_json(silent=True)
        if not data:
            raw_data = request.data.decode('utf-8')
            if not raw_data:
                return jsonify({'error': 'Request body is empty'}), 400
            try:
                data = json.loads(raw_data)
            except json.JSONDecodeError:
                return jsonify({'error': 'Invalid JSON format in request body'}), 400

        if not isinstance(data, dict):
            return jsonify({'error': 'Request body must be a JSON object'}), 400

        text = data.get('text')
        num_keywords = data.get('num_keywords', 5)

        # Validate input
        is_valid, error_msg = validate_input(text)
        if not is_valid:
            return jsonify({'error': error_msg}), 400
        
        if not isinstance(num_keywords, int) or num_keywords < 1 or num_keywords > 20:
            return jsonify({'error': 'num_keywords must be an integer between 1 and 20'}), 400

        start_time = time.time()
        text = preprocess_text(text)
        doc = nlp(text)

        # Extract entities
        entities = [{'text': ent.text, 'label': ent.label_} for ent in doc.ents][:5]
        
        # Extract keywords
        keywords = extract_keywords(text, num_keywords)
        
        # Word count and POS tags
        word_count = len([token for token in doc if not token.is_space])
        pos_tags = [{'text': token.text, 'pos': token.pos_} for token in doc][:10]

        processing_time = time.time() - start_time

        return jsonify({
            'success': True,
            'entities': entities,
            'keywords': keywords,
            'word_count': word_count,
            'pos_tags': pos_tags,
            'processing_time': round(processing_time, 3)
        }), 200

    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        return handle_exception(e)

@text_api.route('/sentiment', methods=['POST'])
def sentiment_analysis():
    """
    Analyze text sentiment (polarity only; subjectivity is placeholder).
    Request body (JSON):
    - text: string (required)
    Returns:
    - sentiment: polarity and subjectivity scores
    - interpretation: human-readable sentiment labels
    - processing_time: float (seconds)
    """
    try:
        data = request.get_json(silent=True)
        if not data:
            raw_data = request.data.decode('utf-8')
            if not raw_data:
                return jsonify({'error': 'Request body is empty'}), 400
            try:
                data = json.loads(raw_data)
            except json.JSONDecodeError:
                return jsonify({'error': 'Invalid JSON format in request body'}), 400

        if not isinstance(data, dict):
            return jsonify({'error': 'Request body must be a JSON object'}), 400

        text = data.get('text')

        # Validate input
        is_valid, error_msg = validate_input(text)
        if not is_valid:
            return jsonify({'error': error_msg}), 400

        start_time = time.time()
        text = preprocess_text(text)
        doc = nlp(text)

        # Note: spaCy doesn't natively provide sentiment; this is a placeholder
        # For real sentiment, integrate a library like TextBlob or VADER
        polarity = sum([token.sentiment for token in doc if token.sentiment]) / (len(doc) or 1)
        subjectivity = 0.5  # Placeholder; spaCy doesn’t provide this

        processing_time = time.time() - start_time

        return jsonify({
            'success': True,
            'sentiment': {
                'polarity': round(polarity, 3),
                'subjectivity': subjectivity
            },
            'interpretation': {
                'polarity': 'positive' if polarity > 0.1 else 'negative' if polarity < -0.1 else 'neutral',
                'subjectivity': 'subjective' if subjectivity > 0.5 else 'objective'
            },
            'processing_time': round(processing_time, 3),
            'note': 'Sentiment analysis is limited; consider integrating TextBlob or VADER for better results'
        }), 200

    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        return handle_exception(e)

@text_api.route('/analyze', methods=['GET'])
def analyze_info():
    """Return /analyze endpoint info."""
    try:
        return jsonify({
            'endpoint': '/api/text/analyze',
            'method': 'POST',
            'description': 'Analyze text for entities, keywords, word count, and POS tags',
            'parameters': {
                'text': 'string (required)',
                'num_keywords': 'integer (optional, default: 5, max: 20)'
            },
            'returns': {
                'success': 'boolean',
                'entities': 'list of {text, label} objects (max 5)',
                'keywords': 'list of top keywords',
                'word_count': 'integer',
                'pos_tags': 'list of {text, pos} objects (max 10)',
                'processing_time': 'float (seconds)'
            }
        }), 200
    except Exception as e:
        return handle_exception(e)

@text_api.route('/sentiment', methods=['GET'])
def sentiment_info():
    """Return /sentiment endpoint info."""
    try:
        return jsonify({
            'endpoint': '/api/text/sentiment',
            'method': 'POST',
            'description': 'Analyze text sentiment (polarity and subjectivity)',
            'parameters': {
                'text': 'string (required)'
            },
            'returns': {
                'success': 'boolean',
                'sentiment': {
                    'polarity': 'float (-1 to 1)',
                    'subjectivity': 'float (0 to 1, placeholder)'
                },
                'interpretation': {
                    'polarity': 'string (positive/neutral/negative)',
                    'subjectivity': 'string (subjective/objective)'
                },
                'processing_time': 'float (seconds)',
                'note': 'string (limitations info)'
            }
        }), 200
    except Exception as e:
        return handle_exception(e)