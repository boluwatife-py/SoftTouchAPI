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

load_dotenv()
app = FastAPI()


class LoggingMiddleware(BaseHTTPMiddleware):
    def update_summary_stats(self):
        session = Session()
        try:
            stat = session.query(Statistic).filter_by(id=1).first()
            request_logs = session.query(RequestLog).all()
            unique_users = len({log.client_ip for log in request_logs})
            total_requests = len(request_logs)
            
            if not stat:
                stat = Statistic(id=1, total_requests=total_requests, unique_users=unique_users, timestamp=datetime.now(dt.UTC))
                session.add(stat)
            else:
                stat.total_requests = total_requests
                stat.unique_users = unique_users
                stat.timestamp = datetime.now(dt.UTC)
            
            session.commit()
        finally:
            session.close()

    def update_api_stats(self, api_name, response_time, status_code):
        session = Session()
        try:
            api = session.query(ApiStat).filter_by(name=api_name).first()
            current_time = datetime.now(dt.UTC)
            success = status_code < 400
            
            if api:
                daily_requests = api.daily_requests + 1
                weekly_requests = api.weekly_requests + 1
                monthly_requests = api.monthly_requests + 1
                
                last_updated = api.last_updated or current_time
                # Ensure last_updated is offset-aware
                if last_updated.tzinfo is None:
                    last_updated = last_updated.replace(tzinfo=dt.UTC)
                
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

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api"):
            start_time = time.time()
            client_ip = request.client.host

            response = Response("Internal server error", status_code=500)
            try:
                response = await call_next(request)
                response_time = (time.time() - start_time) * 1000

                db = Session()
                try:
                    request_log = RequestLog(
                        api_name=request.url.path,
                        client_ip=client_ip,
                        response_time=response_time,
                        status_code=response.status_code,
                        timestamp=datetime.now(timezone.utc)
                    )
                    db.add(request_log)
                    db.commit()

                    self.update_api_stats(request.url.path, response_time, response.status_code)
                    self.update_summary_stats()
                except Exception as e:
                    db.rollback()
                finally:
                    db.close()

            except Exception as e:
                raise
            return response
        else:
            return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)
app.add_middleware(LoggingMiddleware)


discord_token = os.getenv("DISCORD_TOKEN")
if discord_token:
    setup_discord_bot()
    configure_error_handlers(app, send_error_to_discord)
else:
    configure_error_handlers(app, None)

# REGISTER ALL ROUTES
app.include_router(routes.translate_api, prefix="/api")
app.include_router(routes.summarize_api, prefix="/api")











API_URL = os.getenv('API_URL')

@app.get("/", tags=['Root'])
def root():
    return {"message": "SoftTouch API is running"}


@app.get("/statistics")
def statistics_endpoints():
    session = Session()
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


@app.get("/endpoint")
def get_enabled_endpoints():
    session = Session()
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