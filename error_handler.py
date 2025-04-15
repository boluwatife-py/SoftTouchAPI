import logging
import traceback
import sys
from flask import request, jsonify, render_template


def configure_error_handlers(app, discord_callback):
    """Configure Flask error handlers with Discord notification for server errors only"""
    
    @app.errorhandler(Exception)
    def handle_exception(e):
        """Global exception handler for uncaught exceptions (server errors)"""
        # Get exception details
        exc_type, exc_value, exc_traceback = sys.exc_info()
        exception_traceback = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        
        # Prepare error information for Discord
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
        # Send to Discord if callback is provided (only for server errors)
        if discord_callback:
            discord_callback(error_info)
        else:
            print("Discord integration disabled, error not sent to Discord")

        return jsonify({
            'error': 'Internal Server Error',
            'message': str(e) if app.debug else 'An unexpected error occurred'
        }), 500
    
    @app.errorhandler(400)
    def bad_request(e):
        """Handle 400 Bad Request errors (client-side, no Discord notification)"""
        return jsonify({
            'error': 'Bad Request',
            'message': str(e) if app.debug else 'The request was invalid or malformed'
        }), 400
    
    @app.errorhandler(403)
    def forbidden(e):
        """Handle 403 Forbidden errors (client-side, no Discord notification)"""
        return jsonify({
            'error': 'Forbidden',
            'message': str(e) if app.debug else 'You do not have permission to access this resource'
        }), 403
    
    @app.errorhandler(404)
    def page_not_found(e):
        """Handle 404 Not Found errors (client-side, no Discord notification)"""
        return jsonify({
            'error': 'Not Found',
            'message': f"The requested URL {request.path} was not found"
        }), 404
    
    @app.errorhandler(405)
    def method_not_allowed(e):
        """Handle 405 Method Not Allowed errors (client-side, no Discord notification)"""
        return jsonify({
            'error': 'Method Not Allowed',
            'message': str(e) if app.debug else f"Method {request.method} is not allowed for {request.path}"
        }), 405
    
    @app.errorhandler(500)
    def internal_server_error(e):
        """Handle 500 Internal Server Error (explicit 500, with Discord notification)"""
        # Get exception details
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
        
        return jsonify({
            'error': 'Internal Server Error',
            'message': str(e) if app.debug else 'An unexpected error occurred'
        }), 500
    
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
        
        return jsonify({
            'error': 'Bad Gateway',
            'message': str(e) if app.debug else 'The server received an invalid response from an upstream server'
        }), 502
    
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
        
        return jsonify({
            'error': 'Service Unavailable',
            'message': str(e) if app.debug else 'The server is temporarily unavailable'
        }), 503