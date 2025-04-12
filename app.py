from flask import Flask, jsonify, request, Response
from flask_cors import CORS
import api.routes as api
from pydantic import BaseModel, ValidationError, EmailStr
import admin.admin as admin
from utils.discord_bot import setup_discord_bot, send_error_to_discord, send_contact_to_discord 
from error_handler import configure_error_handlers
from dotenv import load_dotenv
import os, logging, json
from admin.admin import ApiEndpoint, Session, ApiEndpointSchema

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


# INITIALIZE APP
app = Flask(__name__)
CORS(app, supports_credentials=True, resources={
    r"/admin/*": {
        "origins": [os.getenv("FRONTEND_ADMIN_URL")],
        "expose_headers": ["Authorization"]
    },
    
    r"/*": {
        "origins": ["*"]
    }
})


discord_token = os.getenv("DISCORD_TOKEN")
app.config['DISCORD_TOKEN'] = discord_token

if discord_token:
    configure_error_handlers(app, send_error_to_discord)
else:
    configure_error_handlers(app, None)

load_dotenv()
API_URL = os.getenv('API_URL')

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


@app.route('/statistics', methods=['GET'])
def statistics_endpoints():
    return jsonify(statistics)


@app.route('/endpoint', methods=['GET'])
def get_enabled_endpoints():
    session = Session()
    try:
        endpoints = session.query(ApiEndpoint).filter_by(enabled=True).all()
        logger.info(f"Retrieved {len(endpoints)} enabled endpoints")
        
        
        api_endpoints = []
        for e in endpoints:
            try:
                params = json.loads(e.params) if e.params else []
            except json.JSONDecodeError:
                logger.warning(f"Invalid params JSON for endpoint {e.id}")
                params = []
            try:
                sample_request = json.loads(e.sample_request) if e.sample_request else {}
            except json.JSONDecodeError:
                logger.warning(f"Invalid sample_request JSON for endpoint {e.id}")
                sample_request = {}
            try:
                sample_response = json.loads(e.sample_response) if e.sample_response else {}
            except json.JSONDecodeError:
                logger.warning(f"Invalid sample_response JSON for endpoint {e.id}")
                sample_response = {}
            endpoint_data = ApiEndpointSchema(
                id=e.id,
                name=e.name,
                method=e.method,
                endpoint=e.endpoint,
                response_type=e.response_type,
                part_description=e.part_description,
                description=e.description,
                params=params,
                sample_request=sample_request,
                sample_response=sample_response,
                enabled=e.enabled,
                is_visible_in_stats=e.is_visible_in_stats
            )
            # Construct response in requested format
            formatted_endpoint = {
                "name": endpoint_data.name,
                "method": endpoint_data.method,
                "endpoint": f"{API_URL}{endpoint_data.endpoint}",
                "response_type": endpoint_data.response_type,
                "sample_response": endpoint_data.sample_response,
                "part_description": endpoint_data.part_description,
                "description": endpoint_data.description,
                "params": [
                    {
                        "name": p.name,
                        "type": p.type,
                        "description": p.description
                    } for p in endpoint_data.params
                ],
                "sample_request": endpoint_data.sample_request
            }
            api_endpoints.append(formatted_endpoint)
        
        return jsonify(api_endpoints)
    except Exception as e:
        logger.error(f"Failed to retrieve enabled endpoints: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        session.close()


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
