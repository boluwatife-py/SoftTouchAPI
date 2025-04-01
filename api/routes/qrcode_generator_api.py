from flask import Blueprint, request, jsonify
import qrcode
from qrcode.image.svg import SvgPathImage
from PIL import Image
import io
import re
import json
import base64
import traceback
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

qr_api = Blueprint('qr_api', __name__)

VALID_FORMATS = {'png', 'jpg', 'svg'}
MAX_FILE_SIZE = 5 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {'image/png', 'image/jpeg', 'image/gif'}

def validate_format(output_format):
    """Validate output format."""
    try:
        if not isinstance(output_format, str):
            return False, "Format must be a string."
        output_format = output_format.lower()
        if output_format not in VALID_FORMATS:
            return False, f"Unsupported format: {output_format}. Use 'png', 'jpg', or 'svg'."
        return True, output_format
    except Exception as e:
        logger.error(f"Format validation error: {str(e)}")
        return False, f"Format validation failed: {str(e)}"

def validate_color(color, field_name="color"):
    """Validate hex color code."""
    try:
        if not isinstance(color, str):
            return False, f"{field_name} must be a string."
        if not re.match(r'^#(?:[0-9a-fA-F]{3}){1,2}$', color):
            return False, f"Invalid {field_name}: {color}. Use hex code (e.g., '#FF0000')."
        return True, color
    except Exception as e:
        logger.error(f"Color validation error for {field_name}: {str(e)}")
        return False, f"{field_name} validation failed: {str(e)}"

def validate_integer(value, field_name, min_val, max_val):
    """Validate integer within range."""
    try:
        if not isinstance(value, (int, str)):
            return False, f"{field_name} must be an integer or string representation of an integer."
        val = int(value)
        if val < min_val or val > max_val:
            return False, f"{field_name} must be between {min_val} and {max_val}."
        return True, val
    except (ValueError, TypeError) as e:
        logger.error(f"Integer validation error for {field_name}: {str(e)}")
        return False, f"{field_name} must be a valid integer."

def handle_exception(e, status_code=500):
    """Generate detailed JSON error response from exception."""
    error_response = {
        'error': str(e),
        'traceback': traceback.format_exc() if isinstance(e, Exception) else None,
        'status': status_code
    }
    logger.error(f"Exception occurred: {error_response}")
    return jsonify(error_response), status_code

@qr_api.route('/generate', methods=['POST'])
def generate_qr():
    """
    Generate a QR code with customizable options and return as JSON.
    Request body (multipart/form-data or JSON):
    - data: text or URL to encode (required)
    - format: output format (optional, default: 'png'; options: 'png', 'jpg', 'svg')
    - fill_color: QR code color (optional, default: '#000000')
    - back_color: background color (optional, default: '#FFFFFF')
    - box_size: pixel size of each box (optional, default: 10)
    - border: border size in boxes (optional, default: 4)
    - image: optional image file to embed (e.g., logo; not supported for SVG)
    Returns: JSON with base64-encoded QR code data.
    """
    try:
        # Check content length
        if request.content_length and request.content_length > MAX_FILE_SIZE:
            return handle_exception(ValueError(f"Request size exceeds maximum limit of {MAX_FILE_SIZE // 1024}KB"), 413)

        # Parse request data
        if request.content_type and request.content_type.startswith('multipart/form-data'):
            if not request.form:
                return handle_exception(ValueError("No form data provided in multipart request"), 400)
            data = request.form.get('data')
            output_format = request.form.get('format', 'png')
            fill_color = request.form.get('fill_color', '#000000')
            back_color = request.form.get('back_color', '#FFFFFF')
            box_size = request.form.get('box_size', '10')
            border = request.form.get('border', '4')
            image_file = request.files.get('image')
        elif request.content_type and 'application/json' in request.content_type:
            json_data = request.get_json(silent=True)
            if json_data is None:
                raw_data = request.data.decode('utf-8', errors='ignore')
                if not raw_data:
                    return handle_exception(ValueError("Request body is empty"), 400)
                try:
                    json_data = json.loads(raw_data)
                except json.JSONDecodeError as e:
                    return handle_exception(ValueError(f"Invalid JSON format in request body: {str(e)}"), 400)

            if not isinstance(json_data, dict):
                return handle_exception(ValueError("Request body must be a JSON object"), 400)

            data = json_data.get('data')
            output_format = json_data.get('format', 'png')
            fill_color = json_data.get('fill_color', '#000000')
            back_color = json_data.get('back_color', '#FFFFFF')
            box_size = json_data.get('box_size', '10')
            border = json_data.get('border', '4')
            image_file = None
        else:
            return handle_exception(ValueError(f"Unsupported Content-Type: {request.content_type}"), 415)

        # Validate inputs
        if not data or not isinstance(data, str) or not data.strip():
            return handle_exception(ValueError("Missing or invalid 'data' field: must be a non-empty string"), 400)

        is_valid_format, format_or_error = validate_format(output_format)
        if not is_valid_format:
            return handle_exception(ValueError(format_or_error), 400)

        is_valid_fill, fill_or_error = validate_color(fill_color, "fill_color")
        if not is_valid_fill:
            return handle_exception(ValueError(fill_or_error), 400)

        is_valid_back, back_or_error = validate_color(back_color, "back_color")
        if not is_valid_back:
            return handle_exception(ValueError(back_or_error), 400)

        is_valid_box, box_or_error = validate_integer(box_size, "box_size", 1, 50)
        if not is_valid_box:
            return handle_exception(ValueError(box_or_error), 400)
        box_size = box_or_error

        is_valid_border, border_or_error = validate_integer(border, "border", 0, 20)
        if not is_valid_border:
            return handle_exception(ValueError(border_or_error), 400)
        border = border_or_error

        # Validate image file if provided
        if image_file:
            if output_format == 'svg':
                return handle_exception(ValueError("Image embedding not supported for SVG format"), 400)
            if image_file.content_length > MAX_FILE_SIZE:
                return handle_exception(ValueError(f"Image size exceeds maximum limit of {MAX_FILE_SIZE // 1024}KB"), 413)
            if image_file.mimetype not in ALLOWED_IMAGE_TYPES:
                return handle_exception(ValueError(f"Unsupported image type: {image_file.mimetype}. Allowed: {', '.join(ALLOWED_IMAGE_TYPES)}"), 415)

        # Generate QR code
        try:
            qr = qrcode.QRCode(
                version=None,
                error_correction=qrcode.constants.ERROR_CORRECT_H,
                box_size=box_size,
                border=border
            )
            qr.add_data(data)
            qr.make(fit=True)
        except Exception as e:
            return handle_exception(ValueError(f"Failed to generate QR code: {str(e)}"), 500)

        # Prepare output
        try:
            output = io.BytesIO()
            if output_format == 'svg':
                qr_img = qr.make_image(image_factory=SvgPathImage, fill_color=fill_color, back_color=back_color)
                qr_img.save(output)
                mime_type = 'image/svg+xml'
            else:
                qr_img = qr.make_image(fill_color=fill_color, back_color=back_color)
                if image_file:
                    try:
                        logo = Image.open(image_file)
                        if logo.mode not in ('RGB', 'RGBA'):
                            logo = logo.convert('RGBA')
                        qr_width, qr_height = qr_img.size
                        logo_size = qr_width // 4
                        logo = logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
                        logo_pos = ((qr_width - logo_size) // 2, (qr_height - logo_size) // 2)
                        qr_img = qr_img.convert('RGBA')
                        qr_img.paste(logo, logo_pos, logo if logo.mode == 'RGBA' else None)
                    except Exception as e:
                        return handle_exception(ValueError(f"Failed to embed image: {str(e)}"), 400)

                qr_img.save(output, format=output_format.upper())
                mime_type = 'image/png' if output_format == 'png' else 'image/jpeg'

            output.seek(0)
            qr_base64 = base64.b64encode(output.getvalue()).decode('utf-8')
            output.close()
        except Exception as e:
            return handle_exception(ValueError(f"Failed to process QR image: {str(e)}"), 500)

        # Return JSON response
        response = {
            'success': True,
            'format': output_format,
            'mime_type': mime_type,
            'data': f'data:{mime_type};base64,{qr_base64}',
            'size': len(qr_base64) // 1024  # Size in KB
        }
        logger.info(f"QR code generated successfully: {output_format}, size: {response['size']}KB")
        return jsonify(response), 200

    except Exception as e:
        return handle_exception(e)

@qr_api.route('/info', methods=['GET'])
def qr_info():
    """Return API info as JSON."""
    try:
        info = {
            "endpoint": "/api/qr/generate",
            "method": "POST",
            "description": "Generate a customizable QR code",
            "parameters": {
                "data": "text or URL to encode (required, string)",
                "format": "output format (optional, default: 'png'; options: 'png', 'jpg', 'svg')",
                "fill_color": "QR code color (optional, default: '#000000', hex code)",
                "back_color": "background color (optional, default: '#FFFFFF', hex code)",
                "box_size": "pixel size of each box (optional, default: 10, integer 1-50)",
                "border": "border size in boxes (optional, default: 4, integer 0-20)",
                "image": "optional image file to embed (multipart/form-data only, not supported for SVG, max 5MB)"
            },
            "returns": "JSON object with base64-encoded QR code data",
            "max_file_size": f"{MAX_FILE_SIZE // 1024}KB"
        }
        logger.info("API info requested")
        return jsonify(info), 200
    except Exception as e:
        return handle_exception(e)