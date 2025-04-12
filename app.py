from flask import Flask, jsonify, request, Response, g
from flask_cors import CORS
import api.routes as api
from pydantic import BaseModel, ValidationError, EmailStr
import admin.admin as admin
from utils.discord_bot import setup_discord_bot, send_error_to_discord, send_contact_to_discord 
from error_handler import configure_error_handlers
from dotenv import load_dotenv
import os, logging, json, sqlite3, time
from datetime import datetime, timedelta
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

# SQLite Database Setup
DATABASE = 'api_stats.db'

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stats_summary (
                id INTEGER PRIMARY KEY,
                total_requests INTEGER,
                unique_users INTEGER,
                timestamp TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS api_stats (
                id INTEGER PRIMARY KEY,
                name TEXT,
                daily_requests INTEGER,
                weekly_requests INTEGER,
                monthly_requests INTEGER,
                average_response_time REAL,
                success_rate REAL,
                popularity REAL,
                last_updated TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS request_log (
                id INTEGER PRIMARY KEY,
                api_name TEXT,
                client_ip TEXT,
                response_time REAL,
                status_code INTEGER,
                timestamp TEXT
            )
        ''')
        
        db.commit()

# Statistics Tracking Functions
def update_summary_stats():
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute('SELECT COUNT(DISTINCT client_ip) FROM request_log')
    unique_users = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM request_log')
    total_requests = cursor.fetchone()[0]
    
    cursor.execute('''
        INSERT OR REPLACE INTO stats_summary 
        (id, total_requests, unique_users, timestamp)
        VALUES (1, ?, ?, ?)
    ''', (total_requests, unique_users, datetime.utcnow().isoformat()))
    
    db.commit()

def update_api_stats(api_name, response_time, status_code):
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute('SELECT * FROM api_stats WHERE name = ?', (api_name,))
    api = cursor.fetchone()
    
    current_time = datetime.utcnow()
    success = status_code < 400
    
    if api:
        daily_requests = api['daily_requests'] + 1
        weekly_requests = api['weekly_requests'] + 1
        monthly_requests = api['monthly_requests'] + 1
        
        last_updated = datetime.fromisoformat(api['last_updated'])
        reset_daily = current_time.date() > last_updated.date()
        reset_weekly = current_time - last_updated > timedelta(weeks=1)
        reset_monthly = current_time - last_updated > timedelta(days=30)
        
        if reset_daily:
            daily_requests = 1
            # Reset success rate and response time for the new day
            avg_response_time = response_time
            success_rate = 100 if success else 0
        else:
            # Update running averages
            avg_response_time = (
                (api['average_response_time'] * (api['daily_requests']) + response_time)
                / daily_requests
            )
            # Track successes explicitly
            prev_successes = (api['success_rate'] / 100) * api['daily_requests']
            new_successes = prev_successes + (1 if success else 0)
            success_rate = (new_successes / daily_requests) * 100
        
        if reset_weekly:
            weekly_requests = 1
        if reset_monthly:
            monthly_requests = 1
            
        popularity = min(100.0, monthly_requests / 10.0)
        
        cursor.execute('''
            UPDATE api_stats 
            SET daily_requests = ?, weekly_requests = ?, monthly_requests = ?,
                average_response_time = ?, success_rate = ?, popularity = ?,
                last_updated = ?
            WHERE name = ?
        ''', (
            daily_requests, weekly_requests, monthly_requests,
            avg_response_time, success_rate, popularity,
            current_time.isoformat(), api_name
        ))
    else:
        # Initialize new API stats
        cursor.execute('''
            INSERT INTO api_stats 
            (name, daily_requests, weekly_requests, monthly_requests,
             average_response_time, success_rate, popularity, last_updated)
            VALUES (?, 1, 1, 1, ?, ?, ?, ?)
        ''', (
            api_name, response_time, 
            100 if success else 0,  # Initial success rate
            0.1, current_time.isoformat()
        ))
    
    db.commit()


@app.before_request
def before_request():
    if request.path.startswith('/api'):
        request.start_time = time.time()
        g.client_ip = request.remote_addr

@app.after_request
def after_request(response):
    if request.path.startswith('/api'):
        db = get_db()
        cursor = db.cursor()
        
        response_time = (time.time() - request.start_time) * 1000  # ms
        
        cursor.execute('''
            INSERT INTO request_log 
            (api_name, client_ip, response_time, status_code, timestamp)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            request.path, g.client_ip, response_time,
            response.status_code, datetime.utcnow().isoformat()
        ))
        
        update_api_stats(request.path, response_time, response.status_code)
        update_summary_stats()
        
        db.commit()
    
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
app.register_blueprint(api.transcribe_api, url_prefix='/api/text')

# Statistics Endpoint
@app.route('/statistics', methods=['GET'])
def statistics_endpoints():
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute('SELECT * FROM stats_summary WHERE id = 1')
    summary = cursor.fetchone()
    
    cursor.execute('SELECT * FROM api_stats')
    apis = cursor.fetchall()
    
    stats = {
        "totalRequests": summary['total_requests'] if summary else 0,
        "uniqueUsers": summary['unique_users'] if summary else 0,
        "timestamp": summary['timestamp'] if summary else datetime.utcnow().isoformat(),
        "apis": [
            {
                "name": api['name'],
                "dailyRequests": api['daily_requests'],
                "weeklyRequests": api['weekly_requests'],
                "monthlyRequests": api['monthly_requests'],
                "averageResponseTime": api['average_response_time'],
                "successRate": api['success_rate'],
                "popularity": api['popularity']
            } for api in apis
        ]
    }
    
    return jsonify(stats)

# Existing Endpoints
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

if __name__ == '__main__':
    if not os.path.exists(DATABASE):
        init_db()
    app.run(debug=False, host='0.0.0.0', port=5000)