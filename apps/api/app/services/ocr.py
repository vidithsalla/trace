from __future__ import annotations

from dataclasses import dataclass, field

from app.core.config import settings


@dataclass(slots=True)
class OCRResult:
    text: str
    confidence: float | None
    status: str
    metadata: dict = field(default_factory=dict)


class OCRService:
    def recognize_image(self, content: bytes, *, content_type: str) -> OCRResult:
        raise NotImplementedError

    def recognize_pdf_page(self, content: bytes, *, page_number: int) -> OCRResult:
        raise NotImplementedError


class DisabledOCRService(OCRService):
    def recognize_image(self, content: bytes, *, content_type: str) -> OCRResult:
        return OCRResult(
            text="",
            confidence=None,
            status="unavailable",
            metadata={
                "provider": "disabled",
                "reason": "OCR is optional in the lightweight local stack.",
                "content_type": content_type,
                "byte_length": len(content),
            },
        )

    def recognize_pdf_page(self, content: bytes, *, page_number: int) -> OCRResult:
        return OCRResult(
            text="",
            confidence=None,
            status="unavailable",
            metadata={
                "provider": "disabled",
                "reason": "OCR is optional in the lightweight local stack.",
                "page_number": page_number,
                "byte_length": len(content),
            },
        )


def get_ocr_service() -> OCRService:
    # Phase 3 keeps heavy OCR out of the default local path. Future providers can
    # implement this same interface for pytesseract, ocrmypdf, or an HTTP add-on.
    if settings.ocr_provider != "disabled":
        return DisabledOCRService()
    return DisabledOCRService()
