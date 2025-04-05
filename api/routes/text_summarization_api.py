from flask import Blueprint, request, jsonify
from collections import Counter
from typing import List, Tuple, Optional
import re, spacy, time, json
from rouge_score import rouge_scorer

summarize_api = Blueprint('summarize_api', __name__)

# Load spaCy model
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    raise RuntimeError("Failed to load spaCy model. Run: python -m spacy download en_core_web_sm")

def preprocess_text(text: str) -> str:
    """Clean and normalize text."""
    text = re.sub(r'\s+', ' ', text.strip())  # Remove extra whitespace
    text = re.sub(r'[^\w\s.,!?]', '', text)   # Remove special characters except punctuation
    return text

def advanced_score_sentences(text: str) -> List[Tuple[str, float]]:
    """Score sentences using multiple factors: word frequency, position, and length."""
    doc = nlp(preprocess_text(text))
    sentences = [sent.text.strip() for sent in doc.sents if sent.text.strip()]
    if not sentences:
        raise ValueError("No valid sentences detected")

    # Word frequency scoring
    words = [token.text.lower() for token in doc if token.is_alpha and not token.is_stop]
    word_freq = Counter(words)
    max_freq = max(word_freq.values(), default=1)

    # Additional factors
    total_sentences = len(sentences)
    sentence_scores = []
    
    for i, sent in enumerate(sentences):
        sent_doc = nlp(sent)
        
        # Base frequency score
        freq_score = sum(word_freq[token.text.lower()] for token in sent_doc 
                        if token.is_alpha and not token.is_stop) / max_freq
        
        # Position score (early sentences often contain key info)
        position_score = 1.0 - (i / total_sentences) if total_sentences > 1 else 1.0
        
        # Length score (avoid very short sentences unless highly relevant)
        length_score = min(len(sent_doc) / 15, 1.0)  # Cap at ~15 tokens
        
        # Combined score
        combined_score = (freq_score * 0.5) + (position_score * 0.3) + (length_score * 0.2)
        normalized_score = combined_score / (len(sent_doc) or 1)
        
        sentence_scores.append((sent, normalized_score))
    
    return sentence_scores

def validate_input(text: Optional[str], num_sentences: Optional[int]) -> Tuple[bool, str]:
    """Validate input parameters."""
    if not isinstance(text, str):
        return False, "Text must be a string"
    if not text.strip():
        return False, "Text cannot be empty"
    if len(text) > 20000:
        return False, "Text exceeds 20000 characters"
    if not isinstance(num_sentences, int):
        return False, "Number of sentences must be an integer"
    if num_sentences < 1 or num_sentences > 100:
        return False, "Number of sentences must be between 1 and 100"
    return True, ""

@summarize_api.route('/summarize', methods=['POST'])
def summarize_text():
    """
    Summarize input text with enhanced scoring.
    Request body (JSON):
    - text: string (required)
    - num_sentences: integer (optional, default=3)
    Returns:
    - input_text: original text
    - summary: summarized text
    - sentence_count: number of sentences in summary
    - original_length: character count of original text
    - processing_time: seconds
    - rouge_scores: ROUGE-1/ROUGE-2 metrics
    """
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

    start_time = time.time()
    
    # Preprocess and score sentences
    original_text = preprocess_text(text)
    sentence_scores = advanced_score_sentences(original_text)
    if not sentence_scores:
        return jsonify({'error': 'No valid sentences found'}), 400

    # Select top sentences
    sorted_sentences = sorted(sentence_scores, key=lambda x: x[1], reverse=True)
    summary_sentences = [sent for sent, _ in sorted_sentences[:min(num_sentences, len(sorted_sentences))]]
    summary = ' '.join(sent.rstrip('.!?,') + '.' for sent in summary_sentences if sent.strip())

    # Additional features
    processing_time = time.time() - start_time
    
    # ROUGE scores (self-evaluation against original text)
    scorer = rouge_scorer.RougeScorer(['rouge1', 'rouge2'], use_stemmer=True)
    rouge_scores = scorer.score(original_text, summary)

    response = {
        'success': True,
        'input_text': original_text,
        'summary': summary,
        'sentence_count': len(summary_sentences),
        'original_length': len(original_text),
        'processing_time': round(processing_time, 3),
        'rouge_scores': {
            'rouge1': {
                'precision': round(rouge_scores['rouge1'].precision, 3),
                'recall': round(rouge_scores['rouge1'].recall, 3),
                'f1': round(rouge_scores['rouge1'].fmeasure, 3)
            },
            'rouge2': {
                'precision': round(rouge_scores['rouge2'].precision, 3),
                'recall': round(rouge_scores['rouge2'].recall, 3),
                'f1': round(rouge_scores['rouge2'].fmeasure, 3)
            }
        }
    }
    
    return jsonify(response), 200