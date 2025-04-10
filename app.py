from flask import Flask, jsonify, request, Response
from flask_cors import CORS
import api.routes as api
from pydantic import BaseModel, ValidationError, EmailStr
import admin.admin as admin
from utils.discord_bot import setup_discord_bot, send_error_to_discord, send_contact_to_discord 
from error_handler import configure_error_handlers
from dotenv import load_dotenv
import os, logging

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


# INITIALIZE APP
app = Flask(__name__)
CORS(app, supports_credentials=True, origins=["*"])


discord_token = os.getenv("DISCORD_TOKEN")
app.config['DISCORD_TOKEN'] = discord_token

if discord_token:
    configure_error_handlers(app, send_error_to_discord)
else:
    configure_error_handlers(app, None)

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
    "response_type": "File or JSON",
    "sample_response": {
        "file": "QR code file (e.g., qr_code.png or qr_code.svg) if Accept header matches mime_type",
        "json_png_jpg": {
            "format": "png",
            "style": "rounded_border",
            "mime_type": "image/png",
            "data": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg... (truncated base64 string)",
            "size_kb": 5.12,
            "dimensions": {
                "width": 600,
                "height": 600
            },
            "colors": {
                "fill": "#000000",
                "background": "#FFFFFF"
            },
            "resolution": 600,
            "border": 4,
            "timestamp": "2025-04-05 12:34:56 UTC"
        },
        "json_svg": {
            "format": "svg",
            "style": "square",
            "mime_type": "image/svg+xml",
            "svg_code": "<svg xmlns=\"http://www.w3.org/2000/svg\" ... (truncated SVG string)",
            "size_kb": 1.23,
            "colors": {
                "fill": "#000000",
                "background": "#FFFFFF"
            },
            "resolution": 600,
            "border": 4,
            "timestamp": "2025-04-05 12:34:56 UTC"
        }
    },
    "part_description": "Generates a stylized QR code with customizable options.",
    "description": "Generates a stylized QR code with specified resolution (default ~600x600 pixels). Returns a file download if the 'Accept' header matches the output mime_type (e.g., 'image/png' or 'image/svg+xml'), otherwise returns JSON with base64 data (PNG/JPG) or SVG code (SVG). 'rounded_border' style applies rounded corners to the entire image (PNG/JPG only).",
    "params": [
        {"name": "data", "type": "String", "description": "Text or URL to encode (required)"},
        {"name": "format", "type": "String (Optional, default='png')", "description": "Output format: 'png', 'jpg', or 'svg'"},
        {"name": "style", "type": "String (Optional, default='square')", "description": "QR module style: 'square', 'circle', 'rounded', 'gapped_square', 'vertical_bars', 'horizontal_bars', 'rounded_border' (rounded corners for PNG/JPG only)"},
        {"name": "fill_color", "type": "String (Optional, default='#000000')", "description": "QR code color in hex format (e.g., '#FF0000')"},
        {"name": "back_color", "type": "String (Optional, default='#FFFFFF')", "description": "Background color in hex format"},
        {"name": "resolution", "type": "Integer (Optional, default=600)", "description": "Desired width/height in pixels (100-2000)"},
        {"name": "border", "type": "Integer (Optional, default=4)", "description": "Border size in boxes (0-20)"},
        {"name": "image", "type": "File (Optional, multipart/form-data only)", "description": "Optional image file (e.g., logo) to embed (not supported for SVG, max 5MB)"}
    ],
    "sample_request": {
        "data": "https://softtouch.io/free-apis",
        "format": "svg",
        "style": "square",
        "fill_color": "#000000",
        "back_color": "#FFFFFF",
        "resolution": "600",
        "border": "4",
        "image": ""
    }
    },
        # AUDIO TRANSCRIPTION
    {
        "name": "Audio Transcription",
        "method": "POST",
        "endpoint": API_URL + "/api/text/transcribe",
        "response_type": "text/plain",
        "sample_response": "Hello, this is a test audio file for transcription.",
        "part_description": "Transcribes audio files to text using OpenAI Whisper, returning the transcription as plain text.",
        "description": "Transcribes audio files to text using OpenAI Whisper, returning the transcription as plain text.",
        "params": [
            {"name": "audio", "type": "File", "description": "Audio file to transcribe (supported formats: .mp3, .wav, .m4a)"},
            {"name": "language", "type": "String", "description": "Optional 2-character ISO language code (e.g., 'en') to specify the audio language"}
        ],
        "sample_request": {
            "audio": "softtouch.mp3",
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

#REGISTER THE ADMIN BLUEPRINT
app.register_blueprint(admin.admin_bp, url_prefix='/admin')

# API ROUTING
app.register_blueprint(api.translate_api, url_prefix='/api/text')
app.register_blueprint(api.summarize_api, url_prefix='/api/text')
app.register_blueprint(api.qr_api, url_prefix='/api/qr')
app.register_blueprint(api.text_api, url_prefix='/api/text')
app.register_blueprint(api.transcribe_api, url_prefix='/api/text')



@app.route('/', methods=['GET'])
def home_endpoints():
    return jsonify(api_endpoints)

@app.route('/statistics', methods=['GET'])
def statistics_endpoints():
    return jsonify(statistics)

@app.route('/endpoints', methods=['GET'])
def get_endpoints():
    return jsonify(api_endpoints), 200

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
        
        send_contact_to_discord(contact_data)
        return jsonify({'message': 'Form submitted successfully!'})
    
    except ValidationError as e:
        return jsonify({'error': 'Invalid form data', 'details': e.errors()}), 400



# setup_discord_bot()
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
