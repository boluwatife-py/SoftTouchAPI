from fastapi import APIRouter, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from typing import Optional, Tuple
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
import logging
import time
import svgwrite

logger = logging.getLogger(__name__)
qr_api = APIRouter()

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
        return io.BytesIO(svg_code.encode()), mime_type, None
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


@qr_api.post("/v1/qr/generate")
async def generate_qr(
    request: Request,
    data: str = Form(...),
    format: str = Form('png'),
    style: str = Form('square'),
    fill_color: str = Form('#000000'),
    back_color: str = Form('#FFFFFF'),
    resolution: int = Form(600),
    border: int = Form(4),
    image: Optional[UploadFile] = File(None)
):
    content_type = request.headers.get("Content-Type", "")
    if "multipart/form-data" not in content_type:
        try:
            body = await request.body()
            json_data = json.loads(body)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid or missing JSON body")

        data = json_data.get('data')
        format = json_data.get('format', 'png')
        style = json_data.get('style', 'square')
        fill_color = json_data.get('fill_color', '#000000')
        back_color = json_data.get('back_color', '#FFFFFF')
        resolution = int(json_data.get('resolution', 600))
        border = int(json_data.get('border', 4))
        image = None

    if not data:
        raise HTTPException(status_code=400, detail="Missing 'data' field")

    is_valid_format, format_or_error = validate_format(format)
    if not is_valid_format:
        raise HTTPException(status_code=400, detail=format_or_error)
    format = format_or_error

    is_valid_style, style_or_error = validate_style(style)
    if not is_valid_style:
        raise HTTPException(status_code=400, detail=style_or_error)
    style = style_or_error

    is_valid_fill, fill_or_error = validate_color(fill_color, "fill_color")
    if not is_valid_fill:
        raise HTTPException(status_code=400, detail=fill_or_error)
    fill_color = fill_or_error

    is_valid_back, back_or_error = validate_color(back_color, "back_color")
    if not is_valid_back:
        raise HTTPException(status_code=400, detail=back_or_error)
    back_color = back_or_error

    is_valid_res, res_or_error = validate_integer(resolution, "resolution", 100, 2000)
    if not is_valid_res:
        raise HTTPException(status_code=400, detail=res_or_error)
    resolution = res_or_error

    is_valid_border, border_or_error = validate_integer(border, "border", 0, 20)
    if not is_valid_border:
        raise HTTPException(status_code=400, detail=border_or_error)
    border = border_or_error

    if image:
        if image.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(status_code=415, detail="Unsupported image type")
        if image.size and image.size > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="Image file too large")

    output, mime_type, qr_img = generate_qr_image(data, format, style, fill_color, back_color, resolution, border, image.file if image else None)

    filename = f"qr_code.{format}"
    return StreamingResponse(
        output,
        media_type=mime_type,
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Content-Length": str(output.getbuffer().nbytes),
        }
    )