from .text_analyzer_api import text_api
from .text_translation_api import translate_api, LANGUAGES
from .text_summarization_api import summarize_api
from .qrcode_generator_api import qr_api
from .ocr import ocr_api

__all__ = ['text_api', 'translate_api', 'summarize_api', 'qr_api', 'LANGUAGES']
