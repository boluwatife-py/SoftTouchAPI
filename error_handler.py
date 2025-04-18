import logging
import traceback
import sys
from flask import request, jsonify, render_template

def configure_error_handlers(app, discord_callback):
    """Configure Flask error handlers with Discord notification for server errors and CORS headers"""
    
    def add_cors_headers(response):
        """Helper function to add CORS headers to a response"""
        if request.path.startswith('/api'):
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        elif request.path.startswith('/admin'):
            frontend_origin = app.config.get('FRONTEND_ADMIN_URL', 'http://localhost:5173')
            response.headers['Access-Control-Allow-Origin'] = frontend_origin
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
            response.headers['Access-Control-Expose-Headers'] = 'Authorization'
            response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response

    @app.errorhandler(Exception)
    def handle_exception(e):
        """Global exception handler for uncaught exceptions (server errors)"""
        exc_type, exc_value, exc_traceback = sys.exc_info()
        exception_traceback = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        
        error_info = {
            'error_type': exc_type.__name__ if exc_type else type(e).__name__,
            'message': str(e),
            'route': request.path,
            'method': request.method,
            'status_code': 500,
            'traceback': exception_traceback,
            'user_agent': request.headers.get('User-Agent'),
            'remote_addr': request.remote_addr
        }
        
        print(e)
        if discord_callback:
            discord_callback(error_info)
        else:
            print("Discord integration disabled, error not sent to Discord")

        response = jsonify({
            'error': 'Internal Server Error',
            'message': str(e) if app.debug else 'An unexpected error occurred'
        })
        response.status_code = 500
        return add_cors_headers(response)
    
    @app.errorhandler(400)
    def bad_request(e):
        """Handle 400 Bad Request errors (client-side, no Discord notification)"""
        response = jsonify({
            'error': 'Bad Request',
            'message': str(e) if app.debug else 'The request was invalid or malformed'
        })
        response.status_code = 400
        return add_cors_headers(response)
    
    @app.errorhandler(403)
    def forbidden(e):
        """Handle 403 Forbidden errors (client-side, no Discord notification)"""
        response = jsonify({
            'error': 'Forbidden',
            'message': str(e) if app.debug else 'You do not have permission to access this resource'
        })
        response.status_code = 403
        return add_cors_headers(response)
    
    @app.errorhandler(404)
    def page_not_found(e):
        """Handle 404 Not Found errors (client-side, no Discord notification)"""
        response = jsonify({
            'error': 'Not Found',
            'message': f"The requested URL {request.path} was not found"
        })
        response.status_code = 404
        return add_cors_headers(response)
    
    @app.errorhandler(405)
    def method_not_allowed(e):
        """Handle 405 Method Not Allowed errors (client-side, no Discord notification)"""
        response = jsonify({
            'error': 'Method Not Allowed',
            'message': str(e) if app.debug else f"Method {request.method} is not allowed for {request.path}"
        })
        response.status_code = 405
        return add_cors_headers(response)
    
    @app.errorhandler(500)
    def internal_server_error(e):
        """Handle 500 Internal Server Error (explicit 500, with Discord notification)"""
        exc_type, exc_value, exc_traceback = sys.exc_info()
        exception_traceback = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        
        error_info = {
            'error_type': 'InternalServerError',
            'message': str(e),
            'route': request.path,
            'method': request.method,
            'status_code': 500,
            'traceback': exception_traceback,
            'user_agent': request.headers.get('User-Agent'),
            'remote_addr': request.remote_addr
        }
        
        if discord_callback:
            discord_callback(error_info)
        else:
            print("Discord integration disabled, 500 error not sent to Discord")
        
        response = jsonify({
            'error': 'Internal Server Error',
            'message': str(e) if app.debug else 'An unexpected error occurred'
        })
        response.status_code = 500
        return add_cors_headers(response)
    
    @app.errorhandler(502)
    def bad_gateway(e):
        """Handle 502 Bad Gateway errors (server-side, with Discord notification)"""
        error_info = {
            'error_type': 'BadGateway',
            'message': str(e),
            'route': request.path,
            'method': request.method,
            'status_code': 502,
            'user_agent': request.headers.get('User-Agent'),
            'remote_addr': request.remote_addr
        }
        
        if discord_callback:
            discord_callback(error_info)
        else:
            print("Discord integration disabled, 502 error not sent to Discord")
        
        response = jsonify({
            'error': 'Bad Gateway',
            'message': str(e) if app.debug else 'The server received an invalid response from an upstream server'
        })
        response.status_code = 502
        return add_cors_headers(response)
    
    @app.errorhandler(503)
    def service_unavailable(e):
        """Handle 503 Service Unavailable errors (server-side, with Discord notification)"""
        error_info = {
            'error_type': 'ServiceUnavailable',
            'message': str(e),
            'route': request.path,
            'method': request.method,
            'status_code': 503,
            'user_agent': request.headers.get('User-Agent'),
            'remote_addr': request.remote_addr
        }
        
        if discord_callback:
            discord_callback(error_info)
        else:
            print("Discord integration disabled, 503 error not sent to Discord")
        
        response = jsonify({
            'error': 'Service Unavailable',
            'message': str(e) if app.debug else 'The server is temporarily unavailable'
        })
        response.status_code = 503
        return add_cors_headers(response)