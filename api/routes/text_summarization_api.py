from fastapi import APIRouter
from pydantic import BaseModel, Field
from collections import Counter
from typing import List, Tuple, Optional
import re, spacy, time
from rouge_score import rouge_scorer
from fastapi.responses import JSONResponse

summarize_api = APIRouter()

class SummarizeRequest(BaseModel):
    text: str = Field(..., description="Text to be summarized")
    num_sentences: int = Field(3, ge=1, description="Number of sentences in the summary (default is 3)")


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

@summarize_api.post('/v1/summarize')
def summarize_text(data: SummarizeRequest):
    # Validate input
    is_valid, error_msg = validate_input(data.text, data.num_sentences)
    if not is_valid:
        return JSONResponse(content={"error": error_msg}, status_code=400)

    start_time = time.time()

    original_text = preprocess_text(data.text)
    sentence_scores = advanced_score_sentences(original_text)
    if not sentence_scores:
        return JSONResponse(content={"error": "No valid sentences found"}, status_code=400)

    sorted_sentences = sorted(sentence_scores, key=lambda x: x[1], reverse=True)
    summary_sentences = [sent for sent, _ in sorted_sentences[:min(data.num_sentences, len(sorted_sentences))]]
    summary = ' '.join(sent.rstrip('.!?,') + '.' for sent in summary_sentences if sent.strip())

    processing_time = time.time() - start_time

    scorer = rouge_scorer.RougeScorer(['rouge1', 'rouge2'], use_stemmer=True)
    rouge_scores = scorer.score(original_text, summary)

    return {
        "success": True,
        "input_text": original_text,
        "summary": summary,
        "sentence_count": len(summary_sentences),
        "original_length": len(original_text),
        "processing_time": round(processing_time, 3),
        "rouge_scores": {
            "rouge1": {
                "precision": round(rouge_scores['rouge1'].precision, 3),
                "recall": round(rouge_scores['rouge1'].recall, 3),
                "f1": round(rouge_scores['rouge1'].fmeasure, 3)
            },
            "rouge2": {
                "precision": round(rouge_scores['rouge2'].precision, 3),
                "recall": round(rouge_scores['rouge2'].recall, 3),
                "f1": round(rouge_scores['rouge2'].fmeasure, 3)
            }
        }
    }