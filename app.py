from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from shared.database import get_db, Session, ApiEndpoint, Statistic, RequestLog, ApiStat
from shared.schema import ApiEndpointSchema, ContactForm
from dotenv import load_dotenv
import os, time, json
import datetime as dt
from datetime import datetime, timedelta, timezone
from starlette.middleware.base import BaseHTTPMiddleware
from utils.discord_bot import send_contact_to_discord, send_error_to_discord, setup_discord_bot
from pydantic import ValidationError
from error_handler import configure_error_handlers
import api.routes as routes
import asyncio
from typing import Callable
import logging
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

load_dotenv()
app = FastAPI()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/softtouch")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Define the RequestLog model
class RequestLog(Base):
    __tablename__ = "request_logs"

    id = Column(Integer, primary_key=True, index=True)
    endpoint = Column(String)
    method = Column(String)
    status_code = Column(Integer)
    response_time = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow)
    request_body = Column(Text, nullable=True)
    response_body = Column(Text, nullable=True)

# Create tables
Base.metadata.create_all(bind=engine)

class LoggingMiddleware:
    def __init__(self, app: FastAPI):
        self.app = app

    async def __call__(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()
        
        # Get request body
        request_body = None
        if request.method in ["POST", "PUT", "PATCH"]:
            try:
                request_body = await request.body()
                request_body = request_body.decode()
            except:
                request_body = "Could not read request body"

        # Process the request
        response = await call_next(request)
        
        # Calculate response time
        process_time = time.time() - start_time
        
        # Get response body
        response_body = None
        if isinstance(response, JSONResponse):
            response_body = response.body.decode()
        
        # Create log entry
        log_entry = {
            "endpoint": str(request.url.path),
            "method": request.method,
            "status_code": response.status_code,
            "response_time": process_time,
            "request_body": request_body,
            "response_body": response_body
        }
        
        # Log to console
        logger.info(f"Request: {request.method} {request.url.path} - Status: {response.status_code} - Time: {process_time:.2f}s")
        
        # Store log in database asynchronously
        asyncio.create_task(self._store_log(log_entry))
        
        return response
    
    async def _store_log(self, log_entry: dict):
        try:
            db = SessionLocal()
            log = RequestLog(**log_entry)
            db.add(log)
            db.commit()
        except Exception as e:
            logger.error(f"Error storing log: {str(e)}")
        finally:
            db.close()

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)
app.add_middleware(LoggingMiddleware)

discord_token = os.getenv("DISCORD_TOKEN")
if discord_token:
    setup_discord_bot()
    configure_error_handlers(app, send_error_to_discord)
else:
    configure_error_handlers(app, None)

app.include_router(routes.translate_api, prefix="/api")
app.include_router(routes.summarize_api, prefix="/api")
app.include_router(routes.text_api, prefix="/api")
app.include_router(routes.qr_api, prefix="/api")
app.include_router(routes.ocr_api, prefix="/api")

API_URL = os.getenv('API_URL')

@app.get("/", tags=['Root'])
def root():
    return {"message": "SoftTouch API is running"}

@app.get("/statistics")
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
            "timestamp": stat.timestamp.isoformat() if stat else datetime.now(dt.UTC).isoformat(),
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
        return stats
    finally:
        session.close()

@app.get("/endpoint")
def get_enabled_endpoints():
    session = Session()
    try:
        endpoints = session.query(ApiEndpoint).filter_by(enabled=True).all()
        
        api_endpoints = []
        for e in endpoints:
            try:
                params = json.loads(e.params) if e.params else []
            except json.JSONDecodeError:
                params = []
            try:
                sample_request = json.loads(e.sample_request) if e.sample_request else {}
            except json.JSONDecodeError:
                sample_request = {}
            try:
                sample_response = json.loads(e.sample_response) if e.sample_response else {}
            except json.JSONDecodeError:
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
        
        return api_endpoints
    finally:
        session.close()

@app.post("/contact")
def submit_contact_form(data: ContactForm):
    try:
        contact_data = {
            'name': data.name,
            'email': data.email,
            'subject': data.subject,
            'message': data.message,
        }
        
        send_contact_to_discord(contact_data)
        return JSONResponse(content={'message': 'Form submitted successfully!'})
    
    except ValidationError as e:
        return JSONResponse(
            status_code=400,
            content={'error': 'Invalid form data', 'details': e.errors()}
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)