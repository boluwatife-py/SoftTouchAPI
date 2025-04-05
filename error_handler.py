import logging
import traceback
import sys
from flask import request, jsonify, render_template

# Configure logging - suppress error messages to console, they will only go to Discord
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create a custom filter to suppress error messages
class SuppressErrorFilter(logging.Filter):
    def filter(self, record):
        return record.levelno < logging.ERROR  # Only allow records below ERROR level

# Add the filter to the logger
logger.addFilter(SuppressErrorFilter())

def configure_error_handlers(app, discord_callback):
    """Configure Flask error handlers with Discord notification"""
    
    @app.errorhandler(Exception)
    def handle_exception(e):
        """Global exception handler that reports errors to Discord"""
        # Get exception details
        exc_type, exc_value, exc_traceback = sys.exc_info()
        exception_traceback = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        
        # Log the error
        logger.error(f"Unhandled exception: {str(e)}\n{exception_traceback}")
        
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
        
        # Send to Discord if callback is provided
        if discord_callback:
            discord_callback(error_info)
        else:
            logger.info("Discord integration disabled, error not sent to Discord")
        
        # Return appropriate response based on request type
        from datetime import datetime
        if request.path.startswith('/api'):
            return jsonify({
                'error': 'Internal Server Error',
                'message': str(e) if app.debug else 'An unexpected error occurred'
            }), 500
        else:
            return render_template('error.html', 
                                  error=str(e) if app.debug else 'An unexpected error occurred', 
                                  now=datetime.now()), 500
    
    @app.errorhandler(404)
    def page_not_found(e):
        """Handle 404 errors and report to Discord"""
        # Log the error
        logger.warning(f"404 error: {request.path}")
        
        # Prepare error information for Discord
        error_info = {
            'error_type': 'NotFound',
            'message': f"Page not found: {request.path}",
            'route': request.path,
            'method': request.method,
            'status_code': 404,
            'user_agent': request.headers.get('User-Agent'),
            'remote_addr': request.remote_addr
        }
        
        # Send to Discord if callback is provided
        if discord_callback:
            discord_callback(error_info)
        else:
            logger.info("Discord integration disabled, 404 error not sent to Discord")
        
        # Return appropriate response based on request type
        from datetime import datetime
        if request.path.startswith('/api'):
            return jsonify({
                'error': 'Not Found',
                'message': f"The requested URL {request.path} was not found"
            }), 404
        else:
            return render_template('error.html', error=f"The requested URL {request.path} was not found", now=datetime.now()), 404
    
    @app.errorhandler(500)
    def internal_server_error(e):
        """Handle 500 errors"""
        # This is mostly a fallback, as most 500 errors should be caught by the Exception handler
        from datetime import datetime
        return render_template('error.html', error="Internal Server Error", now=datetime.now()), 500

    if discord_callback:
        logger.info("Error handlers configured with Discord notifications")
    else:
        logger.info("Error handlers configured without Discord notifications")
