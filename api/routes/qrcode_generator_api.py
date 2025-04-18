from flask import Blueprint, request, jsonify, send_file, Response
import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import (
    SquareModuleDrawer, CircleModuleDrawer, RoundedModuleDrawer,
    GappedSquareModuleDrawer, VerticalBarsDrawer, HorizontalBarsDrawer
)
from PIL import Image, ImageDraw
import io
import re
import json
import base64
import logging
import time
import svgwrite
from typing import Optional, Tuple

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

qr_api = Blueprint('qr_api', __name__)

VALID_FORMATS = {'png', 'jpg', 'svg'}
VALID_STYLES = {
    'square': 'square',
    'circle': 'circle',
    'rounded': 'rounded',
    'gapped_square': 'gapped_square',
    'vertical_bars': 'vertical_bars',
    'horizontal_bars': 'horizontal_bars',
    'rounded_border': 'square'
}
MAX_FILE_SIZE = 5 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {'image/png', 'image/jpeg', 'image/gif'}

def validate_format(output_format: str) -> Tuple[bool, str]:
    """Validate output format."""
    if not isinstance(output_format, str):
        return False, "Format must be a string."
    output_format = output_format.lower()
    if output_format not in VALID_FORMATS:
        return False, f"Unsupported format: {output_format}. Use {', '.join(VALID_FORMATS)}."
    return True, output_format


def validate_style(style: str) -> Tuple[bool, str]:
    """Validate QR style."""
    if not isinstance(style, str):
        return False, "Style must be a string."
    style = style.lower()
    if style not in VALID_STYLES:
        return False, f"Unsupported style: {style}. Use {', '.join(VALID_STYLES.keys())}."
    return True, style


def validate_color(color: str, field_name: str = "color") -> Tuple[bool, str]:
    """Validate hex color code."""
    if not isinstance(color, str):
        return False, f"{field_name} must be a string."
    if not re.match(r'^#(?:[0-9a-fA-F]{3}){1,2}$', color):
        return False, f"Invalid {field_name}: {color}. Use hex code (e.g., '#FF0000')."
    return True, color


def validate_integer(value: any, field_name: str, min_val: int, max_val: int) -> Tuple[bool, int]:
    """Validate integer within range."""
    if not isinstance(value, (int, str)):
        return False, f"{field_name} must be an integer or string representation of an integer."
    try:
        val = int(value)
        if val < min_val or val > max_val:
            return False, f"{field_name} must be between {min_val} and {max_val}."
        return True, val
    except (ValueError, TypeError):
        return False, f"{field_name} must be a valid integer."


def apply_rounded_border(image: Image.Image, radius: int = 40) -> Image.Image:
    """Apply a rounded border to the image."""
    mask = Image.new('L', image.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle(
        [(0, 0), image.size],
        radius=radius,
        fill=255
    )
    output = Image.new('RGBA', image.size, (0, 0, 0, 0))
    output.paste(image, (0, 0), mask)
    return output


def calculate_box_size(qr: qrcode.QRCode, resolution: int) -> int:
    """Calculate box_size based on desired resolution and QR module count."""
    module_count = qr.modules_count + 2 * qr.border
    box_size = max(1, resolution // module_count)
    return box_size


def generate_svg_qr(qr: qrcode.QRCode, style: str, fill_color: str, back_color: str, resolution: int) -> str:
    """Generate SVG QR code with specified style."""
    
    box_size = calculate_box_size(qr, resolution)
    total_size = (qr.modules_count + 2 * qr.border) * box_size
    dwg = svgwrite.Drawing(size=(total_size, total_size))

    # Background
    dwg.add(dwg.rect(insert=(0, 0), size=(total_size, total_size), fill=back_color))

    # QR modules
    for y in range(qr.modules_count):
        for x in range(qr.modules_count):
            if qr.modules[y][x]:
                pos_x = (x + qr.border) * box_size
                pos_y = (y + qr.border) * box_size
                if style == 'circle':
                    dwg.add(dwg.circle(center=(pos_x + box_size / 2, pos_y + box_size / 2),
                                        r=box_size / 2 * 0.8, fill=fill_color))
                elif style == 'rounded':
                    dwg.add(dwg.rect(insert=(pos_x, pos_y), size=(box_size, box_size),
                                    rx=box_size * 0.2, ry=box_size * 0.2, fill=fill_color))
                elif style == 'gapped_square':
                    inset = box_size * 0.2
                    dwg.add(dwg.rect(insert=(pos_x + inset, pos_y + inset),
                                    size=(box_size - 2 * inset, box_size - 2 * inset), fill=fill_color))
                elif style == 'vertical_bars':
                    dwg.add(dwg.rect(insert=(pos_x, pos_y), size=(box_size / 2, box_size), fill=fill_color))
                elif style == 'horizontal_bars':
                    dwg.add(dwg.rect(insert=(pos_x, pos_y), size=(box_size, box_size / 2), fill=fill_color))
                else:  # square or rounded_border
                    dwg.add(dwg.rect(insert=(pos_x, pos_y), size=(box_size, box_size), fill=fill_color))

    return dwg.tostring()


def generate_qr_image(data: str, output_format: str, style: str, fill_color: str, back_color: str, 
                    resolution: int, border: int, image_file: Optional[object] = None) -> Tuple[object, str, Optional[Image.Image]]:
    """Generate QR code with specified resolution, returning buffer or SVG string."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=1,
        border=border
    )
    qr.add_data(data)
    qr.make(fit=True)
    
    box_size = calculate_box_size(qr, resolution)
    qr.box_size = box_size

    if output_format == 'svg':
        svg_code = generate_svg_qr(qr, style, fill_color, back_color, resolution)
        if style == 'rounded_border':
            # Wrap in a rounded rect (simplified for SVG)
            total_size = (qr.modules_count + 2 * qr.border) * box_size
            svg_code = (
                f'<svg width="{total_size}" height="{total_size}" xmlns="http://www.w3.org/2000/svg">'
                f'<rect width="100%" height="100%" rx="{total_size * 0.05}" ry="{total_size * 0.05}" fill="none" clip-path="url(#clip)"/>'
                f'<clipPath id="clip"><rect width="100%" height="100%" rx="{total_size * 0.05}" ry="{total_size * 0.05}"/></clipPath>'
                f'{svg_code}</svg>'
            )
            
        mime_type = 'image/svg+xml'
        return svg_code, mime_type, None
    else:
        module_drawer = {
            'square': SquareModuleDrawer(),
            'circle': CircleModuleDrawer(),
            'rounded': RoundedModuleDrawer(),
            'gapped_square': GappedSquareModuleDrawer(),
            'vertical_bars': VerticalBarsDrawer(),
            'horizontal_bars': HorizontalBarsDrawer(),
            'rounded_border': SquareModuleDrawer()
        }[style]
        qr_img = qr.make_image(
            image_factory=StyledPilImage,
            module_drawer=module_drawer,
            fill_color=fill_color,
            back_color=back_color
        )
        
        if image_file:
            logo = Image.open(image_file)
            if logo.mode not in ('RGB', 'RGBA'):
                logo = logo.convert('RGBA')
            qr_width, qr_height = qr_img.size
            logo_size = qr_width // 4
            logo = logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
            logo_pos = ((qr_width - logo_size) // 2, (qr_height - logo_size) // 2)
            qr_img = qr_img.convert('RGBA')
            qr_img.paste(logo, logo_pos, logo if logo.mode == 'RGBA' else None)

        if style == 'rounded_border':
            qr_img = apply_rounded_border(qr_img)

        output = io.BytesIO()
        save_format = output_format.upper()
        if save_format == 'JPG':
            save_format = 'JPEG'
        qr_img.save(output, format=save_format)
        mime_type = 'image/png' if output_format == 'png' else 'image/jpeg'
        output.seek(0)
        return output, mime_type, qr_img


@qr_api.route('/v1/generate', methods=['POST'])
def generate_qr():
    """
    Generate and return a stylized QR code with specified resolution, either as a file or raw SVG/JSON.
    Request body (multipart/form-data or JSON):
    - data: text or URL to encode (required)
    - format: output format (optional, default: 'png'; options: 'png', 'jpg', 'svg')
    - style: QR module style (optional, default: 'square'; options: 'square', 'circle', 'rounded', 'gapped_square', 'vertical_bars', 'horizontal_bars', 'rounded_border')
    - fill_color: QR code color (optional, default: '#000000')
    - back_color: background color (optional, default: '#FFFFFF')
    - resolution: desired width/height in pixels (optional, default: 600; range: 100-2000)
    - border: border size in boxes (optional, default: 4)
    - image: optional image file to embed (e.g., logo; PNG/JPG only)
    Returns: File download if 'Accept' matches mime_type, raw SVG string if 'svg' and 'application/json', otherwise JSON with base64 data.
    """
    if request.content_length and request.content_length > MAX_FILE_SIZE:
        return jsonify({'error': f"Request size exceeds maximum limit of {MAX_FILE_SIZE // 1024}KB"}), 413

    # Parse request data
    if request.content_type and request.content_type.startswith('multipart/form-data'):
        if not request.form:
            return jsonify({'error': "No form data provided in multipart request"}), 400
        data = request.form.get('data')
        output_format = request.form.get('format', 'png')
        style = request.form.get('style', 'square')
        fill_color = request.form.get('fill_color', '#000000')
        back_color = request.form.get('back_color', '#FFFFFF')
        resolution = request.form.get('resolution', '600')
        border = request.form.get('border', '4')
        image_file = request.files.get('image')
    elif request.content_type and 'application/json' in request.content_type:
        json_data = request.get_json(silent=True)
        if json_data is None:
            raw_data = request.data.decode('utf-8', errors='ignore')
            if not raw_data:
                return jsonify({'error': "Request body is empty"}), 400
            try:
                json_data = json.loads(raw_data)
            except json.JSONDecodeError:
                return jsonify({'error': "Invalid JSON format in request body"}), 400

        if not isinstance(json_data, dict):
            return jsonify({'error': "Request body must be a JSON object"}), 400

        data = json_data.get('data')
        output_format = json_data.get('format', 'png')
        style = json_data.get('style', 'square')
        fill_color = json_data.get('fill_color', '#000000')
        back_color = json_data.get('back_color', '#FFFFFF')
        resolution = json_data.get('resolution', '600')
        border = json_data.get('border', '4')
        image_file = None
    else:
        return jsonify({'error': f"Unsupported Content-Type: {request.content_type}"}), 415

    # Validate inputs
    if not data or not isinstance(data, str) or not data.strip():
        return jsonify({'error': "Missing or invalid 'data' field: must be a non-empty string"}), 400

    is_valid_format, format_or_error = validate_format(output_format)
    if not is_valid_format:
        return jsonify({'error': format_or_error}), 400
    output_format = format_or_error

    is_valid_style, style_or_error = validate_style(style)
    if not is_valid_style:
        return jsonify({'error': style_or_error}), 400
    style = style_or_error

    is_valid_fill, fill_or_error = validate_color(fill_color, "fill_color")
    if not is_valid_fill:
        return jsonify({'error': fill_or_error}), 400
    fill_color = fill_or_error

    is_valid_back, back_or_error = validate_color(back_color, "back_color")
    if not is_valid_back:
        return jsonify({'error': back_or_error}), 400
    back_color = back_or_error

    is_valid_res, res_or_error = validate_integer(resolution, "resolution", 100, 2000)
    if not is_valid_res:
        return jsonify({'error': res_or_error}), 400
    resolution = res_or_error

    is_valid_border, border_or_error = validate_integer(border, "border", 0, 20)
    if not is_valid_border:
        return jsonify({'error': border_or_error}), 400
    border = border_or_error

    if image_file:
        if image_file.content_length > MAX_FILE_SIZE:
            return jsonify({'error': f"Image size exceeds maximum limit of {MAX_FILE_SIZE // 1024}KB"}), 413
        if image_file.mimetype not in ALLOWED_IMAGE_TYPES:
            return jsonify({'error': f"Unsupported image type: {image_file.mimetype}. Allowed: {', '.join(ALLOWED_IMAGE_TYPES)}"}), 415

    # Generate QR code
    output, mime_type, qr_img = generate_qr_image(data, output_format, style, fill_color, back_color, resolution, border, image_file)
    
    # Check Accept header to determine response type
    accept_header = request.headers.get('Accept', '*/*')
    if mime_type in accept_header or '*/*' in accept_header or 'application/octet-stream' in accept_header:
        if output_format == 'svg':
            return Response(
                output,
                mimetype='image/svg+xml',
                headers={'Content-Disposition': 'attachment; filename=qr_code.svg'}
            )
        else:
            filename = f"qr_code.{output_format}"
            return send_file(
                output,
                mimetype=mime_type,
                as_attachment=True,
                download_name=filename
            )
    else:
        if output_format == 'svg':
            response = {
                'format': output_format,
                'style': style,
                'mime_type': mime_type,
                'svg_code': output,
                'size_kb': round(len(output) / 1024, 2),
                'colors': {
                    'fill': fill_color,
                    'background': back_color
                },
                'resolution': resolution,
                'border': border,
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())
            }
            return jsonify(response), 200
        else:
            qr_base64 = base64.b64encode(output.getvalue()).decode('utf-8')
            response = {
                'format': output_format,
                'style': style,
                'mime_type': mime_type,
                'data': f'data:{mime_type};base64,{qr_base64}',
                'size_kb': round(len(qr_base64) / 1024, 2),
                'dimensions': {
                    'width': qr_img.size[0] if qr_img else None,
                    'height': qr_img.size[1] if qr_img else None
                },
                'colors': {
                    'fill': fill_color,
                    'background': back_color
                },
                'resolution': resolution,
                'border': border,
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())
            }
            output.close()
            return jsonify(response), 200