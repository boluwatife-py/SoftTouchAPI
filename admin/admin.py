from flask import Blueprint, request, jsonify
from collections import Counter
from typing import List, Tuple, Optional
import traceback, json, re, spacy

summarize_api = Blueprint('summarize_api', __name__)


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
        # Remove extra whitespace, control characters, and normalize
        text = re.sub(r'\s+', ' ', text.strip())
        return text
    except Exception as e:
        raise ValueError(f"Text preprocessing failed: {str(e)}")

def score_sentences(text: str) -> List[Tuple[str, float]]:
    """Score sentences based on word frequency."""
    try:
        doc = nlp(preprocess_text(text))
        sentences = [sent.text.strip() for sent in doc.sents if sent.text.strip()]
        if not sentences:
            raise ValueError("No valid sentences detected in text")

        # Calculate word frequencies (excluding stop words and punctuation)
        words = [token.text.lower() for token in doc if token.is_alpha and not token.is_stop]
        if not words:
            raise ValueError("No significant words found for scoring")
        
        word_freq = Counter(words)
        max_freq = max(word_freq.values(), default=1)
        
        # Score sentences based on frequency of important words
        sentence_scores = []
        for sent in sentences:
            sent_doc = nlp(sent)
            score = sum(word_freq[token.text.lower()] for token in sent_doc 
                       if token.is_alpha and not token.is_stop) / max_freq
            normalized_score = score / (len(sent_doc) or 1)  # Avoid division by zero
            sentence_scores.append((sent, normalized_score))
        
        return sentence_scores
    except Exception as e:
        raise RuntimeError(f"Sentence scoring failed: {str(e)}")

def validate_input(text: Optional[str], num_sentences: Optional[int]) -> Tuple[bool, str]:
    """Validate input parameters."""
    try:
        if not isinstance(text, str):
            return False, "Text must be a string"
        if not text.strip():
            return False, "Text cannot be empty"
        if len(text) > 10000:
            return False, "Text exceeds 10000 characters"
        if not isinstance(num_sentences, int):
            return False, "Number of sentences must be an integer"
        if num_sentences < 1 or num_sentences > 50:
            return False, "Number of sentences must be between 1 and 50"
        return True, ""
    except Exception as e:
        return False, f"Input validation error: {str(e)}"

def handle_exception(e):
    """Generate JSON error response from exception."""
    return jsonify({
        'error': str(e),
        'traceback': traceback.format_exc() if isinstance(e, Exception) else None
    }), 500

@summarize_api.route('/summarize', methods=['POST'])
def summarize_text():
    """
    Summarize input text by extracting key sentences.
    Request body (JSON):
    - text: string (required)
    - num_sentences: integer (optional, default=3)
    Returns:
    - summary: string
    - sentence_count: integer
    - original_length: integer (characters)
    - processing_time: float (seconds)
    """
    try:
        # Parse JSON request
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
        num_sentences = data.get('num_sentences', 3)

        # Validate input
        is_valid, error_msg = validate_input(text, num_sentences)
        if not is_valid:
            return jsonify({'error': error_msg}), 400

        import time
        start_time = time.time()

        # Score and sort sentences
        sentence_scores = score_sentences(text)
        if not sentence_scores:
            return jsonify({'error': 'No valid sentences found in text'}), 400

        # Select top sentences
        sorted_sentences = sorted(sentence_scores, key=lambda x: x[1], reverse=True)
        summary_sentences = [sent for sent, _ in sorted_sentences[:min(num_sentences, len(sorted_sentences))]]
        
        # Join sentences with proper punctuation
        summary = ' '.join(sent.rstrip('.!?,') + '.' for sent in summary_sentences if sent.strip())

        processing_time = time.time() - start_time

        # Return successful response
        return jsonify({
            'success': True,
            'summary': summary,
            'sentence_count': len(summary_sentences),
            'original_length': len(text),
            'processing_time': round(processing_time, 3)
        }), 200

    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        return handle_exception(e)

@summarize_api.route('/info', methods=['GET'])
def summarize_info():
    """Return API info as JSON."""
    try:
        return jsonify({
            "endpoint": "/api/summarize",
            "method": "POST",
            "description": "Summarize text by extracting key sentences based on word frequency",
            "parameters": {
                "text": "string to summarize (required)",
                "num_sentences": "number of sentences in summary (optional, default: 3, max: 50)"
            },
            "returns": {
                "success": "boolean",
                "summary": "summarized text",
                "sentence_count": "number of sentences in summary",
                "original_length": "character count of original text",
                "processing_time": "time taken in seconds"
            }
        }), 200
    except Exception as e:
        return handle_exception(e)