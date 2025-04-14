from flask import Blueprint, jsonify, request
from pydantic import ValidationError
import datetime
import json
import jwt
import bcrypt
from dotenv import load_dotenv
import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import logging
from shared.database import Session, User, ApiEndpoint, ApiStat, Statistic
from shared.schema import ApiEndpointSchema, ApiStatSchema, InsertUser

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# JWT Secret
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    raise ValueError("SECRET_KEY must be set in .env file")

# Create Blueprint
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# Authentication middleware
def check_admin_auth():
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        logger.warning("No Authorization header provided")
        return jsonify({"message": "Unauthorized"}), 401
    
    token = auth_header.split(' ')[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        session = Session()
        try:
            user = session.query(User).filter_by(id=payload['user_id']).first()
            if not user:
                logger.warning("User not found for token")
                return jsonify({"message": "User not found"}), 401
            if not user.is_admin:
                logger.warning(f"Non-admin user attempted access: {user.username}")
                return jsonify({"message": "Admin access required"}), 403
            request.user_id = payload['user_id']
            return None
        finally:
            session.close()
    except jwt.ExpiredSignatureError:
        logger.warning("Token expired")
        return jsonify({"message": "Token expired"}), 401
    except jwt.InvalidTokenError:
        logger.warning("Invalid token")
        return jsonify({"message": "Invalid token"}), 401

@admin_bp.route('/user', methods=['GET'])
def get_current_user():
    auth_response = check_admin_auth()
    if auth_response:
        return auth_response
    session = Session()
    try:
        user = session.query(User).filter_by(id=request.user_id).first()
        if user:
            logger.info(f"User retrieved: {user.username}")
            return jsonify({"id": user.id, "username": user.username})
        return jsonify({"message": "User not found"}), 404
    finally:
        session.close()

@admin_bp.route('/login', methods=['POST'])
def login():
    try:
        data = InsertUser(**request.get_json())
        session = Session()
        try:
            user = session.query(User).filter_by(username=data.username).first()
            if not user:
                logger.warning(f"Login failed: Invalid username {data.username}")
                return jsonify({"message": "Incorrect username"}), 401
            
            if not bcrypt.checkpw(data.password.encode('utf-8'), user.password.encode('utf-8')):
                logger.warning(f"Login failed: Invalid password for {data.username}")
                return jsonify({"message": "Incorrect password"}), 401
            
            token = jwt.encode({
                'user_id': user.id,
                'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
            }, SECRET_KEY, algorithm='HS256')
            
            logger.info(f"User logged in: {user.username}")
            response = jsonify({"id": user.id, "username": user.username})
            response.headers['Authorization'] = f'Bearer {token}'
            return response
        finally:
            session.close()
    except ValidationError as e:
        logger.error(f"Login validation failed: {e.errors()}")
        return jsonify({"message": "Validation failed", "details": e.errors()}), 400

@admin_bp.route('/logout', methods=['POST'])
def logout():
    logger.info("User logged out (client-side token discard)")
    return '', 204

# API CRUD Operations
@admin_bp.route('/endpoints', methods=['GET'])
def get_endpoints():
    auth_response = check_admin_auth()
    if auth_response:
        return auth_response
    session = Session()
    try:
        endpoints = session.query(ApiEndpoint).all()
        logger.info(f"Retrieved {len(endpoints)} endpoints")
        response_data = [
            ApiEndpointSchema(
                id=e.id,
                name=e.name,
                method=e.method,
                endpoint=e.endpoint,
                response_type=e.response_type,
                part_description=e.part_description,
                description=e.description,
                params=json.loads(e.params),
                sample_request=json.loads(e.sample_request) if e.sample_request else None,
                sample_response=json.loads(e.sample_response) if e.sample_response else None,
                enabled=e.enabled,
                is_visible_in_stats=e.is_visible_in_stats
            ).model_dump() for e in endpoints
        ]
        return jsonify({
            "endpoints": response_data,
            "count": len(endpoints),
            "timestamp": datetime.datetime.utcnow().isoformat()
        })
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON fields: {str(e)}")
        return jsonify({"error": "Invalid JSON in database"}), 500
    finally:
        session.close()

@admin_bp.route('/endpoints/<endpoint_id>', methods=['GET'])
def get_endpoint(endpoint_id: str):
    auth_response = check_admin_auth()
    if auth_response:
        return auth_response
    session = Session()
    try:
        endpoint = session.query(ApiEndpoint).filter_by(id=endpoint_id).first()
        if endpoint:
            logger.info(f"Retrieved endpoint: {endpoint_id}")
            response_data = ApiEndpointSchema(
                id=endpoint.id,
                name=endpoint.name,
                method=endpoint.method,
                endpoint=endpoint.endpoint,
                response_type=endpoint.response_type,
                part_description=endpoint.part_description,
                description=endpoint.description,
                params=json.loads(endpoint.params),
                sample_request=json.loads(endpoint.sample_request) if endpoint.sample_request else None,
                sample_response=json.loads(endpoint.sample_response) if endpoint.sample_response else None,
                enabled=endpoint.enabled,
                is_visible_in_stats=endpoint.is_visible_in_stats
            )
            return jsonify(response_data.model_dump())
        logger.warning(f"Endpoint not found: {endpoint_id}")
        return jsonify({"error": "Endpoint not found"}), 404
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON fields: {str(e)}")
        return jsonify({"error": "Invalid JSON in database"}), 500
    finally:
        session.close()

@admin_bp.route('/endpoints', methods=['POST'])
def create_endpoint():
    auth_response = check_admin_auth()
    if auth_response:
        return auth_response
    try:
        data = ApiEndpointSchema(**request.get_json())
        session = Session()
        try:
            new_endpoint = ApiEndpoint(
                id=data.id,
                name=data.name,
                method=data.method,
                endpoint=data.endpoint,
                response_type=data.response_type,
                part_description=data.part_description,
                description=data.description,
                params=json.dumps([p.model_dump() for p in data.params]),
                sample_request=json.dumps(data.sample_request) if data.sample_request else None,
                sample_response=json.dumps(data.sample_response) if data.sample_response else None,
                enabled=data.enabled,
                is_visible_in_stats=data.is_visible_in_stats
            )
            session.add(new_endpoint)
            session.commit()
            logger.info(f"Created endpoint: {data.name}")
            response_data = ApiEndpointSchema(
                id=new_endpoint.id,
                name=new_endpoint.name,
                method=new_endpoint.method,
                endpoint=new_endpoint.endpoint,
                response_type=new_endpoint.response_type,
                part_description=new_endpoint.part_description,
                description=new_endpoint.description,
                params=json.loads(new_endpoint.params),
                sample_request=json.loads(new_endpoint.sample_request) if new_endpoint.sample_request else None,
                sample_response=json.loads(new_endpoint.sample_response) if new_endpoint.sample_response else None,
                enabled=new_endpoint.enabled,
                is_visible_in_stats=new_endpoint.is_visible_in_stats
            )
            return jsonify({
                "message": "Endpoint created successfully",
                "endpoint": response_data.model_dump()
            }), 201
        finally:
            session.close()
    except ValidationError as e:
        logger.error(f"Endpoint creation failed: {e.errors()}")
        return jsonify({"error": "Validation failed", "details": e.errors()}), 400
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON fields: {str(e)}")
        return jsonify({"error": "Invalid JSON in input"}), 400

@admin_bp.route('/endpoints/<endpoint_id>', methods=['PUT'])
def update_endpoint(endpoint_id: str):
    auth_response = check_admin_auth()
    if auth_response:
        return auth_response
    try:
        data = ApiEndpointSchema(**request.get_json())
        session = Session()
        try:
            endpoint = session.query(ApiEndpoint).filter_by(id=endpoint_id).first()
            if not endpoint:
                logger.warning(f"Endpoint not found for update: {endpoint_id}")
                return jsonify({"error": "Endpoint not found"}), 404
            endpoint.name = data.name
            endpoint.method = data.method
            endpoint.endpoint = data.endpoint
            endpoint.response_type = data.response_type
            endpoint.part_description = data.part_description
            endpoint.description = data.description
            endpoint.params = json.dumps([p.model_dump() for p in data.params])
            endpoint.sample_request = json.dumps(data.sample_request) if data.sample_request else None
            endpoint.sample_response = json.dumps(data.sample_response) if data.sample_response else None
            endpoint.enabled = data.enabled
            endpoint.is_visible_in_stats = data.is_visible_in_stats
            session.commit()
            logger.info(f"Updated endpoint: {endpoint_id}")
            response_data = ApiEndpointSchema(
                id=endpoint.id,
                name=endpoint.name,
                method=endpoint.method,
                endpoint=endpoint.endpoint,
                response_type=endpoint.response_type,
                part_description=endpoint.part_description,
                description=endpoint.description,
                params=json.loads(endpoint.params),
                sample_request=json.loads(endpoint.sample_request) if endpoint.sample_request else None,
                sample_response=json.loads(endpoint.sample_response) if endpoint.sample_response else None,
                enabled=endpoint.enabled,
                is_visible_in_stats=endpoint.is_visible_in_stats
            )
            return jsonify({
                "message": "Endpoint updated successfully",
                "endpoint": response_data.model_dump()
            })
        finally:
            session.close()
    except ValidationError as e:
        logger.error(f"Endpoint update failed: {e.errors()}")
        return jsonify({"error": "Validation failed", "details": e.errors()}), 400
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON fields: {str(e)}")
        return jsonify({"error": "Invalid JSON in input"}), 400

@admin_bp.route('/endpoints/<endpoint_id>', methods=['DELETE'])
def delete_endpoint(endpoint_id: str):
    auth_response = check_admin_auth()
    if auth_response:
        return auth_response
    session = Session()
    try:
        endpoint = session.query(ApiEndpoint).filter_by(id=endpoint_id).first()
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
    auth_response = check_admin_auth()
    if auth_response:
        return auth_response
    session = Session()
    try:
        endpoint = session.query(ApiEndpoint).filter_by(id=endpoint_id).first()
        if not endpoint:
            logger.warning(f"Endpoint not found to enable: {endpoint_id}")
            return jsonify({"error": "Endpoint not found"}), 404
        if endpoint.enabled:
            return jsonify({"message": "Endpoint is already enabled"})
        endpoint.enabled = True
        session.commit()
        logger.info(f"Enabled endpoint: {endpoint_id}")
        response_data = ApiEndpointSchema(
            id=endpoint.id,
            name=endpoint.name,
            method=endpoint.method,
            endpoint=endpoint.endpoint,
            response_type=endpoint.response_type,
            part_description=endpoint.part_description,
            description=endpoint.description,
            params=json.loads(endpoint.params),
            sample_request=json.loads(endpoint.sample_request) if endpoint.sample_request else None,
            sample_response=json.loads(endpoint.sample_response) if endpoint.sample_response else None,
            enabled=endpoint.enabled,
            is_visible_in_stats=endpoint.is_visible_in_stats
        )
        return jsonify({
            "message": "Endpoint enabled successfully",
            "endpoint": response_data.model_dump()
        })
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON fields: {str(e)}")
        return jsonify({"error": "Invalid JSON in database"}), 500
    finally:
        session.close()

@admin_bp.route('/endpoints/<endpoint_id>/disable', methods=['POST'])
def disable_endpoint(endpoint_id: str):
    auth_response = check_admin_auth()
    if auth_response:
        return auth_response
    session = Session()
    try:
        endpoint = session.query(ApiEndpoint).filter_by(id=endpoint_id).first()
        if not endpoint:
            logger.warning(f"Endpoint not found to disable: {endpoint_id}")
            return jsonify({"error": "Endpoint not found"}), 404
        if not endpoint.enabled:
            return jsonify({"message": "Endpoint is already disabled"})
        endpoint.enabled = False
        session.commit()
        logger.info(f"Disabled endpoint: {endpoint_id}")
        response_data = ApiEndpointSchema(
            id=endpoint.id,
            name=endpoint.name,
            method=endpoint.method,
            endpoint=endpoint.endpoint,
            response_type=endpoint.response_type,
            part_description=endpoint.part_description,
            description=endpoint.description,
            params=json.loads(endpoint.params),
            sample_request=json.loads(endpoint.sample_request) if endpoint.sample_request else None,
            sample_response=json.loads(endpoint.sample_response) if endpoint.sample_response else None,
            enabled=endpoint.enabled,
            is_visible_in_stats=endpoint.is_visible_in_stats
        )
        return jsonify({
            "message": "Endpoint disabled successfully",
            "endpoint": response_data.model_dump()
        })
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON fields: {str(e)}")
        return jsonify({"error": "Invalid JSON in database"}), 500
    finally:
        session.close()

# Enable/Disable All Endpoints
@admin_bp.route('/endpoints/enable-all', methods=['POST'])
def enable_all_endpoints():
    auth_response = check_admin_auth()
    if auth_response:
        return auth_response
    session = Session()
    try:
        endpoints = session.query(ApiEndpoint).all()
        if not endpoints:
            logger.warning("No endpoints found to enable")
            return jsonify({"message": "No endpoints found"}), 404
        
        updated_count = 0
        for endpoint in endpoints:
            if not endpoint.enabled:
                endpoint.enabled = True
                updated_count += 1
        
        if updated_count == 0:
            return jsonify({"message": "All endpoints are already enabled"})
        
        session.commit()
        logger.info(f"Enabled {updated_count} endpoints")
        
        response_data = [
            ApiEndpointSchema(
                id=e.id,
                name=e.name,
                method=e.method,
                endpoint=e.endpoint,
                response_type=e.response_type,
                part_description=e.part_description,
                description=e.description,
                params=json.loads(e.params),
                sample_request=json.loads(e.sample_request) if e.sample_request else None,
                sample_response=json.loads(e.sample_response) if e.sample_response else None,
                enabled=e.enabled,
                is_visible_in_stats=e.is_visible_in_stats
            ).model_dump() for e in endpoints
        ]
        
        return jsonify({
            "message": f"Successfully enabled {updated_count} endpoints",
            "endpoints": response_data
        })
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON fields: {str(e)}")
        return jsonify({"error": "Invalid JSON in database"}), 500
    finally:
        session.close()

@admin_bp.route('/endpoints/disable-all', methods=['POST'])
def disable_all_endpoints():
    auth_response = check_admin_auth()
    if auth_response:
        return auth_response
    session = Session()
    try:
        endpoints = session.query(ApiEndpoint).all()
        if not endpoints:
            logger.warning("No endpoints found to disable")
            return jsonify({"message": "No endpoints found"}), 404
        
        updated_count = 0
        for endpoint in endpoints:
            if endpoint.enabled:
                endpoint.enabled = False
                updated_count += 1
        
        if updated_count == 0:
            return jsonify({"message": "All endpoints are already disabled"})
        
        session.commit()
        logger.info(f"Disabled {updated_count} endpoints")
        
        response_data = [
            ApiEndpointSchema(
                id=e.id,
                name=e.name,
                method=e.method,
                endpoint=e.endpoint,
                response_type=e.response_type,
                part_description=e.part_description,
                description=e.description,
                params=json.loads(e.params),
                sample_request=json.loads(e.sample_request) if e.sample_request else None,
                sample_response=json.loads(e.sample_response) if e.sample_response else None,
                enabled=e.enabled,
                is_visible_in_stats=e.is_visible_in_stats
            ).model_dump() for e in endpoints
        ]
        
        return jsonify({
            "message": f"Successfully disabled {updated_count} endpoints",
            "endpoints": response_data
        })
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON fields: {str(e)}")
        return jsonify({"error": "Invalid JSON in database"}), 500
    finally:
        session.close()

# Show/Hide in Statistics
@admin_bp.route('/endpoints/<endpoint_id>/stats/show', methods=['POST'])
def show_in_stats(endpoint_id: str):
    auth_response = check_admin_auth()
    if auth_response:
        return auth_response
    session = Session()
    try:
        endpoint = session.query(ApiEndpoint).filter_by(id=endpoint_id).first()
        if not endpoint:
            logger.warning(f"Endpoint not found to show in stats: {endpoint_id}")
            return jsonify({"error": "Endpoint not found"}), 404
        if endpoint.is_visible_in_stats:
            return jsonify({"message": "Endpoint is already visible in stats"})
        endpoint.is_visible_in_stats = True
        session.commit()
        logger.info(f"Set endpoint visible in stats: {endpoint_id}")
        response_data = ApiEndpointSchema(
            id=endpoint.id,
            name=endpoint.name,
            method=endpoint.method,
            endpoint=endpoint.endpoint,
            response_type=endpoint.response_type,
            part_description=endpoint.part_description,
            description=endpoint.description,
            params=json.loads(endpoint.params),
            sample_request=json.loads(endpoint.sample_request) if endpoint.sample_request else None,
            sample_response=json.loads(endpoint.sample_response) if endpoint.sample_response else None,
            enabled=endpoint.enabled,
            is_visible_in_stats=endpoint.is_visible_in_stats
        )
        return jsonify({
            "message": "Endpoint set to visible in stats",
            "endpoint": response_data.model_dump()
        })
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON fields: {str(e)}")
        return jsonify({"error": "Invalid JSON in database"}), 500
    finally:
        session.close()

@admin_bp.route('/endpoints/<endpoint_id>/stats/hide', methods=['POST'])
def hide_in_stats(endpoint_id: str):
    auth_response = check_admin_auth()
    if auth_response:
        return auth_response
    session = Session()
    try:
        endpoint = session.query(ApiEndpoint).filter_by(id=endpoint_id).first()
        if not endpoint:
            logger.warning(f"Endpoint not found to hide in stats: {endpoint_id}")
            return jsonify({"error": "Endpoint not found"}), 404
        if not endpoint.is_visible_in_stats:
            return jsonify({"message": "Endpoint is already hidden from stats"})
        endpoint.is_visible_in_stats = False
        session.commit()
        logger.info(f"Hid endpoint from stats: {endpoint_id}")
        response_data = ApiEndpointSchema(
            id=endpoint.id,
            name=endpoint.name,
            method=endpoint.method,
            endpoint=endpoint.endpoint,
            response_type=endpoint.response_type,
            part_description=endpoint.part_description,
            description=endpoint.description,
            params=json.loads(endpoint.params),
            sample_request=json.loads(endpoint.sample_request) if endpoint.sample_request else None,
            sample_response=json.loads(endpoint.sample_response) if endpoint.sample_response else None,
            enabled=endpoint.enabled,
            is_visible_in_stats=endpoint.is_visible_in_stats
        )
        return jsonify({
            "message": "Endpoint hidden from stats",
            "endpoint": response_data.model_dump()
        })
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON fields: {str(e)}")
        return jsonify({"error": "Invalid JSON in database"}), 500
    finally:
        session.close()

# Statistics Routes
@admin_bp.route('/stats', methods=['GET'])
def get_statistics():
    auth_response = check_admin_auth()
    if auth_response:
        return auth_response
    session = Session()
    try:
        stats = session.query(Statistic).first()
        visible_endpoints = session.query(ApiEndpoint).filter_by(is_visible_in_stats=True).all()
        visible_names = {e.name for e in visible_endpoints}
        apis = session.query(ApiStat).filter(ApiStat.name.in_(visible_names)).all()
        if not stats:
            stats = Statistic(total_requests=0, unique_users=0)
            session.add(stats)
            session.commit()
        logger.info("Retrieved statistics")
        api_stats = [
            ApiStatSchema(
                name=api.name,
                daily_requests=api.daily_requests,
                weekly_requests=api.weekly_requests,
                monthly_requests=api.monthly_requests,
                average_response_time=api.average_response_time,
                success_rate=api.success_rate,
                popularity=api.popularity
            ).model_dump(by_alias=True) for api in apis
        ]
        return jsonify({
            "totalRequests": stats.total_requests,
            "uniqueUsers": stats.unique_users,
            "timestamp": stats.timestamp.isoformat() if stats.timestamp else datetime.utcnow().isoformat(),
            "apis": api_stats
        })
    finally:
        session.close()

@admin_bp.route('/stats/api/<api_name>', methods=['GET'])
def get_api_stats(api_name: str):
    auth_response = check_admin_auth()
    if auth_response:
        return auth_response
    session = Session()
    try:
        endpoint = session.query(ApiEndpoint).filter_by(name=api_name).first()
        if not endpoint or not endpoint.is_visible_in_stats:
            logger.warning(f"API stats not found or not visible: {api_name}")
            return jsonify({"error": "API stats not found or not visible"}), 404
        api_stat = session.query(ApiStat).filter_by(name=api_name).first()
        if api_stat:
            logger.info(f"Retrieved stats for API: {api_name}")
            response_data = ApiStatSchema(
                name=api_stat.name,
                daily_requests=api_stat.daily_requests,
                weekly_requests=api_stat.weekly_requests,
                monthly_requests=api_stat.monthly_requests,
                average_response_time=api_stat.average_response_time,
                success_rate=api_stat.success_rate,
                popularity=api_stat.popularity
            )
            return jsonify({
                "api": response_data.model_dump(by_alias=True),
                "timestamp": datetime.datetime.utcnow().isoformat()
            })
        return jsonify({"error": "API stats not found"}), 404
    finally:
        session.close()