from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, validator
from typing import Tuple
import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import (
    SquareModuleDrawer, CircleModuleDrawer, RoundedModuleDrawer,
    GappedSquareModuleDrawer, VerticalBarsDrawer, HorizontalBarsDrawer
)
import io
import re
import logging
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
    'horizontal_bars': 'horizontal_bars'
}

class QRRequest(BaseModel):
    data: str = Field(..., min_length=1)
    format: str = Field(default='png')
    style: str = Field(default='square')
    fill_color: str = Field(default='#000000')
    back_color: str = Field(default='#FFFFFF')
    resolution: int = Field(default=600, ge=100, le=2000)
    border: int = Field(default=4, ge=0, le=20)

    @validator('format')
    def validate_format(cls, v):
        if v.lower() not in VALID_FORMATS:
            raise ValueError(f"Unsupported format: {v}. Use {', '.join(VALID_FORMATS)}.")
        return v.lower()

    @validator('style')
    def validate_style(cls, v):
        if v.lower() not in VALID_STYLES:
            raise ValueError(f"Unsupported style: {v}. Use {', '.join(VALID_STYLES.keys())}.")
        return v.lower()

    @validator('fill_color', 'back_color')
    def validate_color(cls, v):
        if not re.match(r'^#(?:[0-9a-fA-F]{3}){1,2}$', v):
            raise ValueError(f"Invalid color: {v}. Use hex code (e.g., '#FF0000').")
        return v

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
                    dwg.add(dwg.circle(
                        center=(pos_x + box_size / 2, pos_y + box_size / 2),
                        r=box_size / 2.2,  # Slightly smaller circles for better spacing
                        fill=fill_color
                    ))
                elif style == 'rounded':
                    dwg.add(dwg.rect(
                        insert=(pos_x + box_size * 0.1, pos_y + box_size * 0.1),
                        size=(box_size * 0.8, box_size * 0.8),
                        rx=box_size * 0.2,
                        ry=box_size * 0.2,
                        fill=fill_color
                    ))
                elif style == 'gapped_square':
                    inset = box_size * 0.25
                    dwg.add(dwg.rect(
                        insert=(pos_x + inset, pos_y + inset),
                        size=(box_size - 2 * inset, box_size - 2 * inset),
                        fill=fill_color
                    ))
                elif style == 'vertical_bars':
                    dwg.add(dwg.rect(
                        insert=(pos_x + box_size * 0.25, pos_y),
                        size=(box_size * 0.5, box_size),
                        fill=fill_color
                    ))
                elif style == 'horizontal_bars':
                    dwg.add(dwg.rect(
                        insert=(pos_x, pos_y + box_size * 0.25),
                        size=(box_size, box_size * 0.5),
                        fill=fill_color
                    ))
                else:  # square
                    dwg.add(dwg.rect(
                        insert=(pos_x, pos_y),
                        size=(box_size, box_size),
                        fill=fill_color
                    ))

    return dwg.tostring()

def generate_qr_image(data: str, output_format: str, style: str, fill_color: str, back_color: str, 
                     resolution: int, border: int) -> Tuple[io.BytesIO, str]:
    """Generate QR code with specified resolution."""
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
        mime_type = 'image/svg+xml'
        return io.BytesIO(svg_code.encode()), mime_type
    else:
        module_drawer = {
            'square': SquareModuleDrawer(),
            'circle': CircleModuleDrawer(),
            'rounded': RoundedModuleDrawer(),
            'gapped_square': GappedSquareModuleDrawer(),
            'vertical_bars': VerticalBarsDrawer(),
            'horizontal_bars': HorizontalBarsDrawer()
        }[style]
        qr_img = qr.make_image(
            image_factory=StyledPilImage,
            module_drawer=module_drawer,
            fill_color=fill_color,
            back_color=back_color
        )

        output = io.BytesIO()
        save_format = output_format.upper()
        if save_format == 'JPG':
            save_format = 'JPEG'
        qr_img.save(output, format=save_format)
        mime_type = 'image/png' if output_format == 'png' else 'image/jpeg'
        output.seek(0)
        return output, mime_type

@qr_api.post("/v1/qr/generate")
async def generate_qr(request: QRRequest):
    output, mime_type = generate_qr_image(
        data=request.data,
        output_format=request.format,
        style=request.style,
        fill_color=request.fill_color,
        back_color=request.back_color,
        resolution=request.resolution,
        border=request.border
    )

    filename = f"qr_code.{request.format}"
    return StreamingResponse(
        output,
        media_type=mime_type,
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Content-Length": str(output.getbuffer().nbytes),
        }
    )