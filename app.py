from flask import Flask, jsonify, request, Response
from flask_cors import CORS
import api.routes as api
from pydantic import BaseModel, ValidationError, EmailStr
import admin.admin as admin
from utils.discord_bot import setup_discord_bot, send_error_to_discord, send_contact_to_discord 
from error_handler import configure_error_handlers
from dotenv import load_dotenv
import os, logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


# INITIALIZE APP
app = Flask(__name__)
CORS(app)

# Initialize Discord bot
discord_bot = setup_discord_bot()
# Configure error handlers
configure_error_handlers(app, send_error_to_discord)

load_dotenv()
API_URL = os.getenv('API_URL')



# MOCKUP API ENDPOINT RESPONSE
api_endpoints = [
    # TEXT ANALYSIS
    {
        "name": "Text Analysis",
        "method": "POST",
        "endpoint": API_URL + "/api/text/analyze",
        "response_type": "JSON",
        "sample_response": {
            "entities": [
                {"text": "New York", "label": "GPE"},
                {"text": "Apple", "label": "ORG"}
            ],
            "keywords": ["analysis", "example", "keywords"],
            "word_count": 42,
            "pos_tags": [
                {"text": "Flask", "pos": "PROPN"},
                {"text": "is", "pos": "AUX"}
            ]
        },
        "part_description": "Analyzes text for named entities, keywords, word count, and POS tagging.",
        "description": "Analyzes text for named entities, keywords, word count, and POS tagging.",
        "params": [
            {"name": "text", "type": "String", "description": "Text to analyze"}
        ],
        "sample_request": {
            "text": "Explore the power of Softtouch's 100% free APIs for text analysis and more!"
        }
    },
    # SENTIMENT ANALYSIS
    {
        "name": "Sentiment Analysis",
        "method": "POST",
        "endpoint": API_URL + "/api/text/sentiment",
        "response_type": "JSON",
        "sample_response": {
            "sentiment": {
                "polarity": 0.2,
                "subjectivity": 0.5
            },
            "interpretation": {
                "polarity": "positive",
                "subjectivity": "neutral"
            }
        },
        "part_description": "Analyzes text sentiment and returns polarity and subjectivity scores.",
        "description": "Analyzes text sentiment and returns polarity and subjectivity scores.",
        "params": [
            {"name": "text", "type": "String", "description": "Text to analyze"}
        ],
        "sample_request": {
            "text": "Softtouch offers free APIs to empower developers worldwide."
        }
    },
    # TEXT TRANSLATION
    {
        "name": "Text Translation",
        "method": "POST",
        "endpoint": API_URL + "/api/text/translate",
        "response_type": "JSON",
        "sample_response": {
            "translated_text": "Hola, ¿cómo estás?",
            "src": "en",
            "dest": "es"
        },
        "part_description": "Translates text from a source language to a target language",
        "description": f"Translates text from a source language to a target language. Available languages: {api.LANGUAGES}",
        "params": [
            {"name": "text", "type": "String | List<String>", "description": "Text or list of texts to translate"},
            {"name": "dest", "type": "String", "description": "Target language code (e.g., 'es' for Spanish)"},
            {"name": "src", "type": "String (Optional)", "description": "Source language code (e.g., 'en' for English, defaults to 'auto')"}
        ],
        "sample_request": {
            "text": "Softtouch provides free APIs for everyone.",
            "dest": "es",
            "src": "en"
        },
    },
    # LANGUAGE DETECTION
    {
        "name": "Language Detection",
        "method": "POST",
        "endpoint": API_URL + "/api/text/translate/detect",
        "response_type": "JSON",
        "sample_response": {
            "language": "en",
            "confidence": 0.98
        },
        "part_description": "Detects the language of the provided text and returns the detected language code along with confidence level.",
        "description": "Detects the language of the provided text and returns the detected language code along with confidence level.",
        "params": [
            {"name": "text", "type": "String", "description": "Text to analyze for language detection"}
        ],
        "sample_request": {
            "text": "Try Softtouch's free APIs today!"
        }
    },
    # TEXT SUMMARIZATION
    {
        "name": "Text Summarization",
        "method": "POST",
        "endpoint": API_URL + "/api/text/summarize",
        "response_type": "JSON",
        "sample_response": {
            "summary": "This is a summary of the input text.",
            "sentence_count": 3,
            "original_length": 450
        },
        "part_description": "Extracts key sentences from input text to generate a summary.",
        "description": "Extracts key sentences from input text to generate a summary.",
        "params": [
            {"name": "text", "type": "String", "description": "Text to summarize"},
            {"name": "num_sentences", "type": "Integer (Optional, default=3)", "description": "Number of key sentences to include in the summary"}
        ],
        "sample_request": {
            "text": "Softtouch is committed to providing 100% free APIs to developers and creators globally, fostering innovation and accessibility in technology.",
            "num_sentences": 2
        }
    },
    # QR CODE GENERATOR
    {
        "name": "QR Code Generator",
        "method": "POST",
        "endpoint": API_URL + "/api/qr/generate",
        "response_type": "File",
        "sample_response": {
            "file": "QR code in specified format (PNG, JPG, or SVG)"
        },
        "part_description": "Generates a QR code with customizable options.",
        "description": "Generates a QR code with customizable options.",
        "params": [
            {"name": "data", "type": "String", "description": "Text or URL to encode (required)"},
            {"name": "format", "type": "String (Optional, default='png')", "description": "Output format: 'png', 'jpg', or 'svg'"},
            {"name": "fill_color", "type": "String (Optional, default='#000000')", "description": "QR code color in hex format (e.g., '#FF0000')"},
            {"name": "back_color", "type": "String (Optional, default='#FFFFFF')", "description": "Background color in hex format"},
            {"name": "box_size", "type": "Integer (Optional, default=10)", "description": "Size of each QR box (1-50)"},
            {"name": "border", "type": "Integer (Optional, default=4)", "description": "Border size in boxes (0-20)"},
            {"name": "image", "type": "File (Optional, multipart/form-data only)", "description": "Optional image file (e.g., logo) to embed (not supported for SVG)"}
        ],
        "sample_request": {
            "data": "https://softtouch.io/free-apis",
            "format": "png",
            "fill_color": "#000000",
            "back_color": "#FFFFFF",
            "box_size": "10",
            "border": "4",
            "image": ""
        }
    },
    # AUDIO TRANSCRIPTION
    {
        "name": "Audio Transcription",
        "method": "POST",
        "endpoint": API_URL + "/transcribe/transcribe",
        "response_type": "text/plain",
        "sample_response": "Hello, this is a test audio file for transcription.",
        "part_description": "Transcribes audio files to text using OpenAI Whisper, returning the transcription as plain text.",
        "description": "Transcribes audio files to text using OpenAI Whisper, returning the transcription as plain text.",
        "params": [
            {"name": "audio", "type": "File", "description": "Audio file to transcribe (supported formats: .mp3, .wav, .m4a)"},
            {"name": "language", "type": "String", "description": "Optional 2-character ISO language code (e.g., 'en') to specify the audio language"}
        ],
        "sample_request": {
            "audio": "test_audio.mp3",
            "language": "en"
        }
    }
]

# MOCKUP STATISTICS RESPONSE DATA
statistics = {
    "totalRequests": 100,
    "uniqueUsers": 50,
    "timestamp": "2023-03-01T00:00:00",
    "apis": [
        {
            "name": "API 1",
            "dailyRequests": 20,
            "weeklyRequests": 100,
            "monthlyRequests": 500,
            "averageResponseTime": 100,
            "successRate": 99.9,
            "popularity": 99.9
        },
        {
            "name": "API 2",
            "dailyRequests": 30,
            "weeklyRequests": 150,
            "monthlyRequests": 750,
            "averageResponseTime": 150,
            "successRate": 99.9,
            "popularity": 99.9
        }
    ]
}

# API ROUTING
app.register_blueprint(api.translate_api, url_prefix='/api/text')
app.register_blueprint(api.summarize_api, url_prefix='/api/text')
app.register_blueprint(api.qr_api, url_prefix='/api/qr')
app.register_blueprint(api.text_api, url_prefix='/api/text')



@app.route('/', methods=['GET'])
def home_endpoints():
    return jsonify(api_endpoints)

@app.route('/statistics', methods=['GET'])
def statistics_endpoints():
    return jsonify(statistics)

@app.route('/endpoints', methods=['GET'])
def get_endpoints():
    return jsonify(api_endpoints), 200

# CONTACT FORM
class ContactForm(BaseModel):
    name: str
    email: EmailStr
    message: str
    subject: str

@app.route('/contact', methods=['POST'])
def submit_contact_form():
    try:
        data = ContactForm(**request.get_json())
        contact_data = {
            'name': data.name,
            'email': data.email,
            'subject': data.subject,
            'message': data.message,
        }
        
        # Send to Discord
        send_contact_to_discord(contact_data)
        return jsonify({'message': 'Form submitted successfully!'}) 
    
    except ValidationError as e:
        return jsonify({'error': 'Invalid form data', 'details': e.errors()}), 400
    except Exception as e:
        return jsonify({'error': 'Something went wrong on our end', 'details': str(e)}), 500



if __name__ == '__main__':
    app.run(debug=os.getenv("DEBUG", False), host='0.0.0.0', port=80)
