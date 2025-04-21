import logging
import traceback
import sys
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
    HTTP_405_METHOD_NOT_ALLOWED,
    HTTP_500_INTERNAL_SERVER_ERROR,
    HTTP_502_BAD_GATEWAY,
    HTTP_503_SERVICE_UNAVAILABLE
)


logging.getLogger('uvicorn.error').setLevel(logging.CRITICAL)
logging.getLogger('uvicorn.access').setLevel(logging.INFO)
logger = logging.getLogger('error_handler')
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

def configure_error_handlers(app: FastAPI, discord_callback=None):
    """Configure FastAPI error handlers with Discord notification for server errors and CORS headers"""

    CORS_HEADERS = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "*",
    }

    @app.exception_handler(Exception)
    def handle_exception(request: Request, exc: Exception):
        """Global exception handler for uncaught exceptions (server errors)"""
        exception_traceback = ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        error_info = {
            'error_type': str(exc),
            'message': str(exc),
            'route': request.url.path,
            'method': request.method,
            'status_code': HTTP_500_INTERNAL_SERVER_ERROR,
            'traceback': exception_traceback,
            'user_agent': request.headers.get('User-Agent', 'Unknown'),
            'remote_addr': request.client.host if request.client else 'Unknown'
        }
        
        sys.stderr = open('/dev/null', 'w')
        try:
            if discord_callback:
                discord_callback(error_info)
            else:
                logger.debug("Discord integration disabled, error not sent to Discord")
        finally:
            sys.stderr = sys.__stderr__

        response = JSONResponse(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                'error': 'Internal Server Error',
                'message': str(exc) if app.debug else 'An unexpected error occurred'
            },
            headers=CORS_HEADERS
        )
        return response
    
    @app.exception_handler(HTTPException)
    def http_exception_handler(request: Request, exc: HTTPException):
        """Handle specific HTTP exceptions"""
        status_code = exc.status_code
        error_map = {
            HTTP_400_BAD_REQUEST: 'Bad Request',
            HTTP_403_FORBIDDEN: 'Forbidden',
            HTTP_404_NOT_FOUND: 'Not Found',
            HTTP_405_METHOD_NOT_ALLOWED: 'Method Not Allowed',
            HTTP_500_INTERNAL_SERVER_ERROR: 'Internal Server Error',
            HTTP_502_BAD_GATEWAY: 'Bad Gateway',
            HTTP_503_SERVICE_UNAVAILABLE: 'Service Unavailable'
        }
        
        error_type = error_map.get(status_code, 'Unknown Error')
        message = str(exc.detail) if app.debug else {
            HTTP_400_BAD_REQUEST: 'The request was invalid or malformed',
            HTTP_403_FORBIDDEN: 'You do not have permission to access this resource',
            HTTP_404_NOT_FOUND: f"The requested URL {request.url.path} was not found",
            HTTP_405_METHOD_NOT_ALLOWED: f"Method {request.method} is not allowed for {request.url.path}",
            HTTP_500_INTERNAL_SERVER_ERROR: 'An unexpected error occurred',
            HTTP_502_BAD_GATEWAY: 'The server received an invalid response from an upstream server',
            HTTP_503_SERVICE_UNAVAILABLE: 'The server is temporarily unavailable'
        }.get(status_code, 'An error occurred')

        error_info = {
            'error_type': error_type,
            'SDH': str(exc.detail),
            'route': request.url.path,
            'method': request.method,
            'status_code': status_code,
            'user_agent': request.headers.get('User-Agent', 'Unknown'),
            'remote_addr': request.client.host if request.client else 'Unknown'
        }
        
        if status_code in [HTTP_500_INTERNAL_SERVER_ERROR, HTTP_502_BAD_GATEWAY, HTTP_503_SERVICE_UNAVAILABLE]:
            exception_traceback = ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            error_info['traceback'] = exception_traceback
            sys.stderr = open('/dev/null', 'w')
            try:
                if discord_callback:
                    discord_callback(error_info)
                else:
                    logger.debug(f"Discord integration disabled, {status_code} error not sent to Discord")
            finally:
                sys.stderr = sys.__stderr__
        response = JSONResponse(
            status_code=status_code,
            content={
                'error': error_type,
                'message': message
            },
            headers=CORS_HEADERS
        )
        return response