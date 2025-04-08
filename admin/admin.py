from flask import Blueprint, jsonify, request, Flask
from flask_cors import CORS
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import create_engine, Column, String, Boolean, Integer, Float, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from typing import List, Optional
import datetime
import uuid
import json
import jwt
import bcrypt
from dotenv import load_dotenv
import os
import logging
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Database setup
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///api_management.db')
engine = create_engine(DATABASE_URL, echo=False)  # Set echo=False in production
Base = declarative_base()
Session = sessionmaker(bind=engine)

# JWT Secret
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    raise ValueError("SECRET_KEY must be set in .env file")

# Database Models
class UserDB(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String, nullable=False, unique=True)
    password_hash = Column(String, nullable=False)  # Hashed with bcrypt
    is_admin = Column(Boolean, default=False)

class ApiEndpointDB(Base):
    __tablename__ = 'api_endpoints'
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    method = Column(String, nullable=False)
    endpoint = Column(String, nullable=False, unique=True)
    response_type = Column(String, nullable=False)
    part_description = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    params = Column(Text, nullable=False)  # JSON string of params
    enabled = Column(Boolean, default=True)
    is_visible_in_stats = Column(Boolean, default=True)

class ApiStatsDB(Base):
    __tablename__ = 'api_stats'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    daily_requests = Column(Integer, default=0)
    weekly_requests = Column(Integer, default=0)
    monthly_requests = Column(Integer, default=0)
    average_response_time = Column(Float, default=0.0)
    success_rate = Column(Float, default=0.0)
    popularity = Column(Float, default=0.0)

class StatisticsDB(Base):
    __tablename__ = 'statistics'
    id = Column(Integer, primary_key=True)
    total_requests = Column(Integer, default=0)
    unique_users = Column(Integer, default=0)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

# Create tables
Base.metadata.create_all(engine)

# Create Blueprint
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# Pydantic Models
class ApiParam(BaseModel):
    name: str
    type: str
    description: str

class ApiEndpoint(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    method: str
    endpoint: str
    response_type: str
    part_description: str
    description: str
    params: List[ApiParam]
    enabled: bool = True
    is_visible_in_stats: bool = True

class ApiStats(BaseModel):
    name: str
    dailyRequests: int = Field(alias='daily_requests')
    weeklyRequests: int = Field(alias='weekly_requests')
    monthlyRequests: int = Field(alias='monthly_requests')
    averageResponseTime: float = Field(alias='average_response_time')
    successRate: float = Field(alias='success_rate')
    popularity: float

class Statistics(BaseModel):
    totalRequests: int = Field(alias='total_requests')
    uniqueUsers: int = Field(alias='unique_users')
    timestamp: str
    apis: List[ApiStats]

class LoginData(BaseModel):
    username: str
    password: str

# Authentication middleware
def check_admin_auth():
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        logger.warning("No Authorization header provided")
        return jsonify({"error": "Unauthorized"}), 401
    
    token = auth_header.split(' ')[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        request.user_id = payload['user_id']  # Attach user_id to request for later use
        return None
    except jwt.ExpiredSignatureError:
        logger.warning("Token expired")
        return jsonify({"error": "Token expired"}), 401
    except jwt.InvalidTokenError:
        logger.warning("Invalid token")
        return jsonify({"error": "Invalid token"}), 401

@admin_bp.before_request
def require_admin():
    auth_response = check_admin_auth()
    if auth_response:
        return auth_response

# Route checker for non-admin routes
def check_route_enabled(endpoint: str):
    session = Session()
    try:
        api_endpoint = session.query(ApiEndpointDB).filter_by(endpoint=endpoint).first()
        if api_endpoint and not api_endpoint.enabled:
            logger.info(f"Disabled endpoint accessed: {endpoint}")
            return jsonify({"error": "Endpoint not found"}), 404
        return None
    finally:
        session.close()

# User API Endpoints
@admin_bp.route('/user', methods=['GET'])
def get_current_user():
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify(None), 401  # Matches frontend expectation
    
    token = auth_header.split(' ')[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        session = Session()
        try:
            user = session.query(UserDB).filter_by(id=payload['user_id']).first()
            if user:
                logger.info(f"User retrieved: {user.username}")
                return jsonify({"id": user.id, "username": user.username})
            return jsonify(None), 401
        finally:
            session.close()
    except jwt.InvalidTokenError:
        return jsonify(None), 401

@admin_bp.route('/login', methods=['POST'])
def login():
    try:
        data = LoginData(**request.get_json())
        session = Session()
        try:
            user = session.query(UserDB).filter_by(username=data.username).first()
            if not user:
                logger.warning(f"Login failed: Invalid username {data.username}")
                return jsonify({"error": "Invalid username"}), 401
            
            if not bcrypt.checkpw(data.password.encode('utf-8'), user.password_hash.encode('utf-8')):
                logger.warning(f"Login failed: Invalid password for {data.username}")
                return jsonify({"error": "Invalid password"}), 401
            
            # Generate JWT token
            token = jwt.encode({
                'user_id': user.id,
                'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)  # Token expires in 24 hours
            }, SECRET_KEY, algorithm='HS256')
            
            logger.info(f"User logged in: {user.username}")
            response = jsonify({"id": user.id, "username": user.username})
            response.headers['Authorization'] = f'Bearer {token}'
            return response
        finally:
            session.close()
    except ValidationError as e:
        logger.error(f"Login validation failed: {e.errors()}")
        return jsonify({"error": "Validation failed", "details": e.errors()}), 400

@admin_bp.route('/logout', methods=['POST'])
def logout():
    # Since JWT is stateless, logout is handled client-side by discarding the token
    # This endpoint is here to match the frontend expectation
    logger.info("User logged out (client-side token discard)")
    return jsonify({"message": "Logged out successfully"})

# API CRUD Operations (unchanged but with logging)
@admin_bp.route('/endpoints', methods=['GET'])
def get_endpoints():
    session = Session()
    try:
        endpoints = session.query(ApiEndpointDB).all()
        logger.info(f"Retrieved {len(endpoints)} endpoints")
        return jsonify({
            "endpoints": [{
                **e.__dict__,
                "params": json.loads(e.params),
                "enabled": e.enabled,
                "is_visible_in_stats": e.is_visible_in_stats
            } for e in endpoints],
            "count": len(endpoints),
            "timestamp": datetime.datetime.utcnow().isoformat()
        })
    finally:
        session.close()

@admin_bp.route('/endpoints/<endpoint_id>', methods=['GET'])
def get_endpoint(endpoint_id: str):
    session = Session()
    try:
        endpoint = session.query(ApiEndpointDB).filter_by(id=endpoint_id).first()
        if endpoint:
            logger.info(f"Retrieved endpoint: {endpoint_id}")
            return jsonify({
                **endpoint.__dict__,
                "params": json.loads(endpoint.params)
            })
        logger.warning(f"Endpoint not found: {endpoint_id}")
        return jsonify({"error": "Endpoint not found"}), 404
    finally:
        session.close()

@admin_bp.route('/endpoints', methods=['POST'])
def create_endpoint():
    try:
        data = ApiEndpoint(**request.get_json())
        session = Session()
        try:
            new_endpoint = ApiEndpointDB(
                id=data.id,
                name=data.name,
                method=data.method,
                endpoint=data.endpoint,
                response_type=data.response_type,
                part_description=data.part_description,
                description=data.description,
                params=json.dumps([p.dict() for p in data.params]),
                enabled=data.enabled,
                is_visible_in_stats=data.is_visible_in_stats
            )
            session.add(new_endpoint)
            session.commit()
            logger.info(f"Created endpoint: {data.name}")
            return jsonify({
                "message": "Endpoint created successfully",
                "endpoint": data.dict()
            }), 201
        finally:
            session.close()
    except ValidationError as e:
        logger.error(f"Endpoint creation failed: {e.errors()}")
        return jsonify({"error": "Validation failed", "details": e.errors()}), 400

@admin_bp.route('/endpoints/<endpoint_id>', methods=['PUT'])
def update_endpoint(endpoint_id: str):
    try:
        data = ApiEndpoint(**request.get_json())
        session = Session()
        try:
            endpoint = session.query(ApiEndpointDB).filter_by(id=endpoint_id).first()
            if not endpoint:
                logger.warning(f"Endpoint not found for update: {endpoint_id}")
                return jsonify({"error": "Endpoint not found"}), 404
            
            endpoint.name = data.name
            endpoint.method = data.method
            endpoint.endpoint = data.endpoint
            endpoint.response_type = data.response_type
            endpoint.part_description = data.part_description
            endpoint.description = data.description
            endpoint.params = json.dumps([p.dict() for p in data.params])
            endpoint.enabled = data.enabled
            endpoint.is_visible_in_stats = data.is_visible_in_stats
            session.commit()
            logger.info(f"Updated endpoint: {endpoint_id}")
            return jsonify({
                "message": "Endpoint updated successfully",
                "endpoint": data.dict()
            })
        finally:
            session.close()
    except ValidationError as e:
        logger.error(f"Endpoint update failed: {e.errors()}")
        return jsonify({"error": "Validation failed", "details": e.errors()}), 400

@admin_bp.route('/endpoints/<endpoint_id>', methods=['DELETE'])
def delete_endpoint(endpoint_id: str):
    session = Session()
    try:
        endpoint = session.query(ApiEndpointDB).filter_by(id=endpoint_id).first()
        if endpoint:
            session.delete(endpoint)
            session.commit()
            logger.info(f"Deleted endpoint: {endpoint_id}")
            return jsonify({"message": "Endpoint deleted successfully"})
        logger.warning(f"Endpoint not found for deletion: {endpoint_id}")
        return jsonify({"error": "Endpoint not found"}), 404
    finally:
        session.close()

# Enable/Disable Endpoints
@admin_bp.route('/endpoints/<endpoint_id>/enable', methods=['POST'])
def enable_endpoint(endpoint_id: str):
    session = Session()
    try:
        endpoint = session.query(ApiEndpointDB).filter_by(id=endpoint_id).first()
        if not endpoint:
            logger.warning(f"Endpoint not found to enable: {endpoint_id}")
            return jsonify({"error": "Endpoint not found"}), 404
        
        if endpoint.enabled:
            return jsonify({"message": "Endpoint is already enabled"})
        
        endpoint.enabled = True
        session.commit()
        logger.info(f"Enabled endpoint: {endpoint_id}")
        return jsonify({
            "message": "Endpoint enabled successfully",
            "endpoint": {**endpoint.__dict__, "params": json.loads(endpoint.params)}
        })
    finally:
        session.close()

@admin_bp.route('/endpoints/<endpoint_id>/disable', methods=['POST'])
def disable_endpoint(endpoint_id: str):
    session = Session()
    try:
        endpoint = session.query(ApiEndpointDB).filter_by(id=endpoint_id).first()
        if not endpoint:
            logger.warning(f"Endpoint not found to disable: {endpoint_id}")
            return jsonify({"error": "Endpoint not found"}), 404
        
        if not endpoint.enabled:
            return jsonify({"message": "Endpoint is already disabled"})
        
        endpoint.enabled = False
        session.commit()
        logger.info(f"Disabled endpoint: {endpoint_id}")
        return jsonify({
            "message": "Endpoint disabled successfully",
            "endpoint": {**endpoint.__dict__, "params": json.loads(endpoint.params)}
        })
    finally:
        session.close()

# Show/Hide in Statistics
@admin_bp.route('/endpoints/<endpoint_id>/stats/show', methods=['POST'])
def show_in_stats(endpoint_id: str):
    session = Session()
    try:
        endpoint = session.query(ApiEndpointDB).filter_by(id=endpoint_id).first()
        if not endpoint:
            logger.warning(f"Endpoint not found to show in stats: {endpoint_id}")
            return jsonify({"error": "Endpoint not found"}), 404
        
        if endpoint.is_visible_in_stats:
            return jsonify({"message": "Endpoint is already visible in stats"})
        
        endpoint.is_visible_in_stats = True
        session.commit()
        logger.info(f"Set endpoint visible in stats: {endpoint_id}")
        return jsonify({
            "message": "Endpoint set to visible in stats",
            "endpoint": {**endpoint.__dict__, "params": json.loads(endpoint.params)}
        })
    finally:
        session.close()

@admin_bp.route('/endpoints/<endpoint_id>/stats/hide', methods=['POST'])
def hide_in_stats(endpoint_id: str):
    session = Session()
    try:
        endpoint = session.query(ApiEndpointDB).filter_by(id=endpoint_id).first()
        if not endpoint:
            logger.warning(f"Endpoint not found to hide in stats: {endpoint_id}")
            return jsonify({"error": "Endpoint not found"}), 404
        
        if not endpoint.is_visible_in_stats:
            return jsonify({"message": "Endpoint is already hidden from stats"})
        
        endpoint.is_visible_in_stats = False
        session.commit()
        logger.info(f"Hid endpoint from stats: {endpoint_id}")
        return jsonify({
            "message": "Endpoint hidden from stats",
            "endpoint": {**endpoint.__dict__, "params": json.loads(endpoint.params)}
        })
    finally:
        session.close()

# Statistics Routes
@admin_bp.route('/stats', methods=['GET'])
def get_statistics():
    session = Session()
    try:
        stats = session.query(StatisticsDB).first()
        visible_endpoints = session.query(ApiEndpointDB).filter_by(is_visible_in_stats=True).all()
        visible_names = {e.name for e in visible_endpoints}
        apis = session.query(ApiStatsDB).filter(ApiStatsDB.name.in_(visible_names)).all()
        
        if not stats:
            stats = StatisticsDB(total_requests=0, unique_users=0)
            session.add(stats)
            session.commit()
        
        logger.info("Retrieved statistics")
        return jsonify({
            "totalRequests": stats.total_requests,
            "uniqueUsers": stats.unique_users,
            "timestamp": stats.timestamp.isoformat(),
            "apis": [api.__dict__ for api in apis]
        })
    finally:
        session.close()

@admin_bp.route('/stats/api/<api_name>', methods=['GET'])
def get_api_stats(api_name: str):
    session = Session()
    try:
        endpoint = session.query(ApiEndpointDB).filter_by(name=api_name).first()
        if not endpoint or not endpoint.is_visible_in_stats:
            logger.warning(f"API stats not found or not visible: {api_name}")
            return jsonify({"error": "API stats not found or not visible"}), 404
        
        api_stat = session.query(ApiStatsDB).filter_by(name=api_name).first()
        if api_stat:
            logger.info(f"Retrieved stats for API: {api_name}")
            return jsonify({
                "api": api_stat.__dict__,
                "timestamp": datetime.datetime.utcnow().isoformat()
            })
        return jsonify({"error": "API stats not found"}), 404
    finally:
        session.close()