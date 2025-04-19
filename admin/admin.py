from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from typing import Optional
import datetime
import json
import jwt
import bcrypt
from dotenv import load_dotenv
import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import logging
from shared.database import Session, User, ApiEndpoint
from shared.schema import ApiEndpointSchema, InsertUser

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# JWT Secret
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    raise ValueError("SECRET_KEY must be set in .env file")

# Create APIRouter
admin_router = APIRouter(tags=["admin"])

# Authentication dependency
async def check_admin_auth(request: Request) -> Optional[dict]:
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        raise HTTPException(status_code=401, detail={"message": "Unauthorized"})
    
    token = auth_header.split(' ')[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        session = Session()
        try:
            user = session.query(User).filter_by(id=payload['user_id']).first()
            if not user:
                raise HTTPException(status_code=401, detail={"message": "User not found"})
            if not user.is_admin:
                raise HTTPException(status_code=403, detail={"message": "Admin access required"})
            return payload
        finally:
            session.close()
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail={"message": "Token expired"})
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail={"message": "Invalid token"})

@admin_router.get("/user")
async def get_current_user(payload: dict = Depends(check_admin_auth)):
    session = Session()
    try:
        user = session.query(User).filter_by(id=payload['user_id']).first()
        if user:
            return {"id": user.id, "username": user.username}
        raise HTTPException(status_code=404, detail={"message": "User not found"})
    finally:
        session.close()

@admin_router.post("/login")
async def login(data: InsertUser):
    session = Session()
    try:
        user = session.query(User).filter_by(username=data.username).first()
        if not user:
            raise HTTPException(status_code=401, detail={"message": "Incorrect username"})
        
        if not bcrypt.checkpw(data.password.encode('utf-8'), user.password.encode('utf-8')):
            raise HTTPException(status_code=401, detail={"message": "Incorrect password"})
        
        token = jwt.encode({
            'user_id': user.id,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        }, SECRET_KEY, algorithm='HS256')
        
        return {
            "id": user.id,
            "username": user.username,
            "token": token
        }
    except ValidationError as e:
        raise HTTPException(status_code=400, detail={"message": "Validation failed", "details": e.errors()})
    finally:
        session.close()

@admin_router.post("/logout")
async def logout():
    return JSONResponse(status_code=204, content={})

# API CRUD Operations
@admin_router.get("/endpoints")
async def get_endpoints(payload: dict = Depends(check_admin_auth)):
    session = Session()
    try:
        endpoints = session.query(ApiEndpoint).all()
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
        return {
            "endpoints": response_data,
            "count": len(endpoints),
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat()
        }
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail={"error": "Invalid JSON in database"})
    finally:
        session.close()

@admin_router.get("/endpoints/{endpoint_id}")
async def get_endpoint(endpoint_id: str, payload: dict = Depends(check_admin_auth)):
    session = Session()
    try:
        endpoint = session.query(ApiEndpoint).filter_by(id=endpoint_id).first()
        if endpoint:
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
            return response_data.model_dump()
        raise HTTPException(status_code=404, detail={"error": "Endpoint not found"})
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail={"error": "Invalid JSON in database"})
    finally:
        session.close()

@admin_router.post("/endpoints")
async def create_endpoint(data: ApiEndpointSchema, payload: dict = Depends(check_admin_auth)):
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
        return JSONResponse(
            status_code=201,
            content={
                "message": "Endpoint created successfully",
                "endpoint": response_data.model_dump()
            }
        )
    except ValidationError as e:
        raise HTTPException(status_code=400, detail={"error": "Validation failed", "details": e.errors()})
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail={"error": "Invalid JSON in input"})
    finally:
        session.close()

@admin_router.put("/endpoints/{endpoint_id}")
async def update_endpoint(endpoint_id: str, data: ApiEndpointSchema, payload: dict = Depends(check_admin_auth)):
    session = Session()
    try:
        endpoint = session.query(ApiEndpoint).filter_by(id=endpoint_id).first()
        if not endpoint:
            raise HTTPException(status_code=404, detail={"error": "Endpoint not found"})
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
        return {
            "message": "Endpoint updated successfully",
            "endpoint": response_data.model_dump()
        }
    except ValidationError as e:
        raise HTTPException(status_code=400, detail={"error": "Validation failed", "details": e.errors()})
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail={"error": "Invalid JSON in input"})
    finally:
        session.close()

@admin_router.delete("/endpoints/{endpoint_id}")
async def delete_endpoint(endpoint_id: str, payload: dict = Depends(check_admin_auth)):
    session = Session()
    try:
        endpoint = session.query(ApiEndpoint).filter_by(id=endpoint_id).first()
        if endpoint:
            session.delete(endpoint)
            session.commit()
            return {"message": "Endpoint deleted successfully"}
        raise HTTPException(status_code=404, detail={"error": "Endpoint not found"})
    finally:
        session.close()

# Enable/Disable Endpoints
@admin_router.post("/endpoints/{endpoint_id}/enable")
async def enable_endpoint(endpoint_id: str, payload: dict = Depends(check_admin_auth)):
    session = Session()
    try:
        endpoint = session.query(ApiEndpoint).filter_by(id=endpoint_id).first()
        if not endpoint:
            raise HTTPException(status_code=404, detail={"error": "Endpoint not found"})
        if endpoint.enabled:
            return {"message": "Endpoint is already enabled"}
        endpoint.enabled = True
        session.commit()
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
        return {
            "message": "Endpoint enabled successfully",
            "endpoint": response_data.model_dump()
        }
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail={"error": "Invalid JSON in database"})
    finally:
        session.close()

@admin_router.post("/endpoints/{endpoint_id}/disable")
async def disable_endpoint(endpoint_id: str, payload: dict = Depends(check_admin_auth)):
    session = Session()
    try:
        endpoint = session.query(ApiEndpoint).filter_by(id=endpoint_id).first()
        if not endpoint:
            raise HTTPException(status_code=404, detail={"error": "Endpoint not found"})
        if not endpoint.enabled:
            return {"message": "Endpoint is already disabled"}
        endpoint.enabled = False
        session.commit()
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
        return {
            "message": "Endpoint disabled successfully",
            "endpoint": response_data.model_dump()
        }
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail={"error": "Invalid JSON in database"})
    finally:
        session.close()

# Enable/Disable All Endpoints
@admin_router.post("/endpoints/enable-all")
async def enable_all_endpoints(payload: dict = Depends(check_admin_auth)):
    session = Session()
    try:
        endpoints = session.query(ApiEndpoint).all()
        if not endpoints:
            raise HTTPException(status_code=404, detail={"message": "No endpoints found"})
        
        updated_count = 0
        for endpoint in endpoints:
            if not endpoint.enabled:
                endpoint.enabled = True
                updated_count += 1
        
        if updated_count == 0:
            return {"message": "All endpoints are already enabled"}
        
        session.commit()
        
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
        
        return {
            "message": f"Successfully enabled {updated_count} endpoints",
            "endpoints": response_data
        }
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail={"error": "Invalid JSON in database"})
    finally:
        session.close()

@admin_router.post("/endpoints/disable-all")
async def disable_all_endpoints(payload: dict = Depends(check_admin_auth)):
    session = Session()
    try:
        endpoints = session.query(ApiEndpoint).all()
        if not endpoints:
            raise HTTPException(status_code=404, detail={"message": "No endpoints found"})
        
        updated_count = 0
        for endpoint in endpoints:
            if endpoint.enabled:
                endpoint.enabled = False
                updated_count += 1
        
        if updated_count == 0:
            return {"message": "All endpoints are already disabled"}
        
        session.commit()
        
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
        
        return {
            "message": f"Successfully disabled {updated_count} endpoints",
            "endpoints": response_data
        }
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail={"error": "Invalid JSON in database"})
    finally:
        session.close()

# Show/Hide in Statistics
@admin_router.post("/endpoints/{endpoint_id}/stats/show")
async def show_in_stats(endpoint_id: str, payload: dict = Depends(check_admin_auth)):
    session = Session()
    try:
        endpoint = session.query(ApiEndpoint).filter_by(id=endpoint_id).first()
        if not endpoint:
            raise HTTPException(status_code=404, detail={"error": "Endpoint not found"})
        if endpoint.is_visible_in_stats:
            return {"message": "Endpoint is already visible in stats"}
        endpoint.is_visible_in_stats = True
        session.commit()
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
        return {
            "message": "Endpoint set to visible in stats",
            "endpoint": response_data.model_dump()
        }
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail={"error": "Invalid JSON in database"})
    finally:
        session.close()

@admin_router.post("/endpoints/{endpoint_id}/stats/hide")
async def hide_in_stats(endpoint_id: str, payload: dict = Depends(check_admin_auth)):
    session = Session()
    try:
        endpoint = session.query(ApiEndpoint).filter_by(id=endpoint_id).first()
        if not endpoint:
            raise HTTPException(status_code=404, detail={"error": "Endpoint not found"})
        if not endpoint.is_visible_in_stats:
            return {"message": "Endpoint is already hidden from stats"}
        endpoint.is_visible_in_stats = False
        session.commit()
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
        return {
            "message": "Endpoint hidden from stats",
            "endpoint": response_data.model_dump()
        }
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail={"error": "Invalid JSON in database"})
    finally:
        session.close()

@admin_router.post("/endpoints/show-all-in-stats")
async def show_all_in_stats(payload: dict = Depends(check_admin_auth)):
    session = Session()
    try:
        endpoints = session.query(ApiEndpoint).all()
        if not endpoints:
            raise HTTPException(status_code=404, detail={"message": "No endpoints found"})
        
        updated_count = 0
        for endpoint in endpoints:
            if not endpoint.is_visible_in_stats:
                endpoint.is_visible_in_stats = True
                updated_count += 1
        
        if updated_count == 0:
            return {"message": "All endpoints are already visible in stats"}
        
        session.commit()
        
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
        
        return {
            "message": f"Successfully set {updated_count} endpoints visible in stats",
            "endpoints": response_data
        }
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail={"error": "Invalid JSON in database"})
    finally:
        session.close()

@admin_router.post("/endpoints/hide-all-from-stats")
async def hide_all_from_stats(payload: dict = Depends(check_admin_auth)):
    session = Session()
    try:
        endpoints = session.query(ApiEndpoint).all()
        if not endpoints:
            raise HTTPException(status_code=404, detail={"message": "No endpoints found"})
        
        updated_count = 0
        for endpoint in endpoints:
            if endpoint.is_visible_in_stats:
                endpoint.is_visible_in_stats = False
                updated_count += 1
        
        if updated_count == 0:
            return {"message": "All endpoints are already hidden from stats"}
        
        session.commit()
        
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
        
        return {
            "message": f"Successfully hid {updated_count} endpoints from stats",
            "endpoints": response_data
        }
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail={"error": "Invalid JSON in database"})
    finally:
        session.close()