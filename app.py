from flask import Flask, jsonify, request, Response, g
from flask_cors import CORS
import api.routes as api
from pydantic import BaseModel, ValidationError, EmailStr
import admin.admin as admin
from utils.discord_bot import setup_discord_bot, send_error_to_discord, send_contact_to_discord 
from error_handler import configure_error_handlers
from dotenv import load_dotenv
import os, logging, json, time
from datetime import datetime, timedelta
from shared.database import get_db, Session, ApiEndpoint, Statistic, RequestLog, ApiStat
from shared.schema import ApiEndpointSchema

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

# Database Setup
DATABASE = 'api.db'

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    pass

# Statistics Tracking Functions
def update_summary_stats():
    session = Session()
    try:
        stat = session.query(Statistic).filter_by(id=1).first()
        request_logs = session.query(RequestLog).all()
        unique_users = len({log.client_ip for log in request_logs})
        total_requests = len(request_logs)
        
        if not stat:
            stat = Statistic(id=1, total_requests=total_requests, unique_users=unique_users, timestamp=datetime.utcnow())
            session.add(stat)
        else:
            stat.total_requests = total_requests
            stat.unique_users = unique_users
            stat.timestamp = datetime.utcnow()
        
        session.commit()
    finally:
        session.close()

def update_api_stats(api_name, response_time, status_code):
    session = Session()
    try:
        api = session.query(ApiStat).filter_by(name=api_name).first()
        current_time = datetime.utcnow()
        success = status_code < 400
        
        if api:
            daily_requests = api.daily_requests + 1
            weekly_requests = api.weekly_requests + 1
            monthly_requests = api.monthly_requests + 1
            
            last_updated = api.last_updated or current_time
            reset_daily = current_time.date() > last_updated.date()
            reset_weekly = current_time - last_updated > timedelta(weeks=1)
            reset_monthly = current_time - last_updated > timedelta(days=30)
            
            if reset_daily:
                daily_requests = 1
                avg_response_time = response_time
                success_rate = 100 if success else 0
            else:
                avg_response_time = (
                    (api.average_response_time * api.daily_requests + response_time)
                    / daily_requests
                )
                prev_successes = (api.success_rate / 100) * api.daily_requests
                new_successes = prev_successes + (1 if success else 0)
                success_rate = (new_successes / daily_requests) * 100
            
            if reset_weekly:
                weekly_requests = 1
            if reset_monthly:
                monthly_requests = 1
                
            popularity = min(100.0, monthly_requests / 10.0)
            
            api.daily_requests = daily_requests
            api.weekly_requests = weekly_requests
            api.monthly_requests = monthly_requests
            api.average_response_time = avg_response_time
            api.success_rate = success_rate
            api.popularity = popularity
            api.last_updated = current_time
        else:
            api = ApiStat(
                name=api_name,
                daily_requests=1,
                weekly_requests=1,
                monthly_requests=1,
                average_response_time=response_time,
                success_rate=100 if success else 0,
                popularity=0.1,
                last_updated=current_time
            )
            session.add(api)
        
        session.commit()
    finally:
        session.close()

@app.before_request
def before_request():
    if request.path.startswith('/api'):
        request.start_time = time.time()
        g.client_ip = request.remote_addr

@app.after_request
def after_request(response):
    if request.path.startswith('/api'):
        session = Session()
        try:
            response_time = (time.time() - request.start_time) * 1000  # ms
            request_log = RequestLog(
                api_name=request.path,
                client_ip=g.client_ip,
                response_time=response_time,
                status_code=response.status_code,
                timestamp=datetime.utcnow()
            )
            session.add(request_log)
            session.commit()
            
            update_api_stats(request.path, response_time, response.status_code)
            update_summary_stats()
        finally:
            session.close()
    
    return response

# Discord and Environment Setup
discord_token = os.getenv("DISCORD_TOKEN")
app.config['DISCORD_TOKEN'] = discord_token

if discord_token:
    configure_error_handlers(app, send_error_to_discord)
else:
    configure_error_handlers(app, None)

API_URL = os.getenv('API_URL')

# Blueprints Registration
app.register_blueprint(admin.admin_bp, url_prefix='/admin')
app.register_blueprint(api.translate_api, url_prefix='/api/text')
app.register_blueprint(api.summarize_api, url_prefix='/api/text')
app.register_blueprint(api.qr_api, url_prefix='/api/qr')
app.register_blueprint(api.text_api, url_prefix='/api/text')
# app.register_blueprint(api.transcribe_api, url_prefix='/api/text')

# Statistics Endpoint
@app.route('/statistics', methods=['GET'])
def statistics_endpoints():
    session = Session()
    try:
        stat = session.query(Statistic).filter_by(id=1).first()
        visible_endpoints = session.query(ApiEndpoint).filter_by(is_visible_in_stats=True).all()
        visible_ed = {e.endpoint for e in visible_endpoints}
        apis = session.query(ApiStat).filter(ApiStat.name.in_(visible_ed)).all()
        
        stats = {
            "totalRequests": stat.total_requests if stat else 0,
            "uniqueUsers": stat.unique_users if stat else 0,
            "timestamp": stat.timestamp.isoformat() if stat else datetime.utcnow().isoformat(),
            "apis": [
                {
                    "name": api.name,
                    "dailyRequests": api.daily_requests,
                    "weeklyRequests": api.weekly_requests,
                    "monthlyRequests": api.monthly_requests,
                    "averageResponseTime": api.average_response_time,
                    "successRate": api.success_rate,
                    "popularity": api.popularity
                } for api in apis
            ]
        }
        
        return jsonify(stats)
    finally:
        session.close()

@app.route('/endpoint', methods=['GET'])
def get_enabled_endpoints():
    session = Session()
    try:
        endpoints = session.query(ApiEndpoint).filter_by(enabled=True).all()
        
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
                        "name": p.name,           # Fixed: Use dot notation
                        "type": p.type,           # Fixed: Use dot notation
                        "description": p.description  # Fixed: Use dot notation
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

setup_discord_bot()
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)