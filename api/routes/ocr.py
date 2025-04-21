from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from PIL import Image
import pytesseract
import io
import pdf2image
import os
from datetime import datetime
from werkzeug.utils import secure_filename
import logging

# Set up logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

ocr_api = APIRouter()

ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'pdf'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def generate_response(success, message, status_code=200):
    response = {
        'success': success,
        'message': message
    }
    return JSONResponse(content=response, status_code=status_code)

class OCRProcessor:
    @staticmethod
    def extract_text_from_image(image_stream, file_extension):
        try:
            if file_extension.lower() == '.pdf':
                return OCRProcessor._process_pdf(image_stream)
            else:
                return OCRProcessor._process_image(image_stream)
        except Exception as e:
            logger.error(f"Error processing image: {str(e)}")
            raise

    @staticmethod
    def _process_image(image_stream):
        try:
            image_stream.seek(0)
            image = Image.open(image_stream)
            text = pytesseract.image_to_string(image)
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)

            result = {
                "text": text,
                "confidence": OCRProcessor._calculate_confidence(data),
                "word_count": len([w for w in data['text'] if w.strip() != ""]),
                "dimensions": {
                    "width": image.width,
                    "height": image.height
                }
            }
            return result
        except Exception as e:
            logger.error(f"Error in image processing: {str(e)}")
            raise

    @staticmethod
    def _process_pdf(pdf_stream):
        try:
            pdf_stream.seek(0)
            pages = pdf2image.convert_from_bytes(pdf_stream.read())

            results = []
            for i, page in enumerate(pages):
                img_byte_arr = io.BytesIO()
                page.save(img_byte_arr, format='PNG')
                img_byte_arr.seek(0)

                page_result = OCRProcessor._process_image(img_byte_arr)
                page_result["page"] = i + 1
                results.append(page_result)

            combined_text = '\n\n'.join([r["text"] for r in results])
            avg_confidence = sum([r["confidence"] for r in results]) / len(results) if results else 0

            return {
                "text": combined_text,
                "confidence": avg_confidence,
                "page_count": len(pages),
                "pages": results
            }
        except Exception as e:
            logger.error(f"Error in PDF processing: {str(e)}")
            raise

    @staticmethod
    def _calculate_confidence(data):
        confidences = [int(conf) for conf in data['conf'] if conf != '-1']
        return sum(confidences) / len(confidences) if confidences else 0


@ocr_api.post('/v1/ocr')
async def extract_text(file: UploadFile = File(...)):
    start_time = datetime.now()

    if not allowed_file(file.filename):
        ext = os.path.splitext(file.filename)[1]
        logger.warning(f"File type {ext} not allowed")
        return generate_response(False, f"File type {ext} not allowed. Supported formats: JPG, PNG, PDF", 400)

    file_extension = os.path.splitext(file.filename)[1]
    file_content = await file.read()
    file_stream = io.BytesIO(file_content)

    result = OCRProcessor.extract_text_from_image(file_stream, file_extension)
    processing_time = (datetime.now() - start_time).total_seconds()

    response_data = {
        "success": True,
        "filename": secure_filename(file.filename),
        "processing_time_seconds": processing_time,
        "timestamp": datetime.now().isoformat(),
        "result": result
    }

    logger.info(f"Successfully processed file: {file.filename}")
    return JSONResponse(content=response_data, status_code=200)