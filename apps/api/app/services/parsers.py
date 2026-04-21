from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from io import BytesIO, StringIO
from pathlib import Path
from typing import Protocol

import fitz
from docx import Document as DocxDocument
from openpyxl import load_workbook

from app.services.ocr import OCRService, get_ocr_service


WHITESPACE_RE = re.compile(r"[ \t\r\f\v]+")
LINE_GAP_RE = re.compile(r"\n{3,}")


@dataclass(slots=True)
class ParsedPage:
    page_number: int
    raw_text: str
    normalized_text: str
    has_text_layer: bool
    ocr_confidence: float | None = None
    image_storage_key: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class ParseResult:
    pages: list[ParsedPage]
    parse_status: str
    ocr_status: str
    extraction_quality_score: float
    metadata: dict = field(default_factory=dict)


class DocumentParser(Protocol):
    supported_mime_types: set[str]
    supported_extensions: set[str]

    def parse(self, content: bytes, *, file_name: str) -> ParseResult:
        ...


def normalize_text(text: str) -> str:
    text = text.replace("\x00", "")
    text = "\n".join(WHITESPACE_RE.sub(" ", line).strip() for line in text.splitlines())
    return LINE_GAP_RE.sub("\n\n", text).strip()


def _decode_text(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _quality_score(pages: list[ParsedPage]) -> float:
    if not pages:
        return 0.0
    text_pages = sum(1 for page in pages if page.normalized_text)
    char_count = sum(len(page.normalized_text) for page in pages)
    density = min(char_count / max(len(pages) * 1200, 1), 1.0)
    coverage = text_pages / len(pages)
    return round((coverage * 0.7) + (density * 0.3), 2)


class TextParser:
    supported_mime_types = {"text/plain"}
    supported_extensions = {".txt", ".text", ".log"}

    def parse(self, content: bytes, *, file_name: str) -> ParseResult:
        raw_text = _decode_text(content)
        page = ParsedPage(
            page_number=1,
            raw_text=raw_text,
            normalized_text=normalize_text(raw_text),
            has_text_layer=True,
            metadata={"parser": "txt"},
        )
        return ParseResult(
            pages=[page],
            parse_status="completed",
            ocr_status="not_needed",
            extraction_quality_score=_quality_score([page]),
            metadata={"parser": "txt"},
        )


class CSVParser:
    supported_mime_types = {"text/csv", "application/csv"}
    supported_extensions = {".csv"}

    def parse(self, content: bytes, *, file_name: str) -> ParseResult:
        decoded = _decode_text(content)
        rows = csv.reader(StringIO(decoded))
        rendered = "\n".join(" | ".join(cell.strip() for cell in row) for row in rows)
        page = ParsedPage(
            page_number=1,
            raw_text=rendered,
            normalized_text=normalize_text(rendered),
            has_text_layer=True,
            metadata={"parser": "csv"},
        )
        return ParseResult(
            pages=[page],
            parse_status="completed",
            ocr_status="not_needed",
            extraction_quality_score=_quality_score([page]),
            metadata={"parser": "csv"},
        )


class DOCXParser:
    supported_mime_types = {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    supported_extensions = {".docx"}

    def parse(self, content: bytes, *, file_name: str) -> ParseResult:
        document = DocxDocument(BytesIO(content))
        parts = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
        for table in document.tables:
            for row in table.rows:
                parts.append(" | ".join(cell.text.strip() for cell in row.cells))
        raw_text = "\n".join(parts)
        page = ParsedPage(
            page_number=1,
            raw_text=raw_text,
            normalized_text=normalize_text(raw_text),
            has_text_layer=True,
            metadata={"parser": "docx", "paragraph_count": len(document.paragraphs)},
        )
        return ParseResult(
            pages=[page],
            parse_status="completed",
            ocr_status="not_needed",
            extraction_quality_score=_quality_score([page]),
            metadata={"parser": "docx"},
        )


class XLSXParser:
    supported_mime_types = {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
    supported_extensions = {".xlsx"}

    def parse(self, content: bytes, *, file_name: str) -> ParseResult:
        workbook = load_workbook(BytesIO(content), data_only=True, read_only=True)
        pages: list[ParsedPage] = []
        for index, sheet in enumerate(workbook.worksheets, start=1):
            lines = []
            for row in sheet.iter_rows(values_only=True):
                values = ["" if value is None else str(value).strip() for value in row]
                if any(values):
                    lines.append(" | ".join(values))
            raw_text = "\n".join(lines)
            pages.append(
                ParsedPage(
                    page_number=index,
                    raw_text=raw_text,
                    normalized_text=normalize_text(raw_text),
                    has_text_layer=True,
                    metadata={"parser": "xlsx", "sheet_name": sheet.title},
                )
            )
        return ParseResult(
            pages=pages,
            parse_status="completed",
            ocr_status="not_needed",
            extraction_quality_score=_quality_score(pages),
            metadata={"parser": "xlsx", "sheet_count": len(pages)},
        )


class PDFParser:
    supported_mime_types = {"application/pdf"}
    supported_extensions = {".pdf"}

    def __init__(self, ocr_service: OCRService | None = None) -> None:
        self.ocr_service = ocr_service or get_ocr_service()

    def parse(self, content: bytes, *, file_name: str) -> ParseResult:
        document = fitz.open(stream=content, filetype="pdf")
        pages: list[ParsedPage] = []
        ocr_needed = False
        ocr_unavailable = False
        try:
            for index, pdf_page in enumerate(document, start=1):
                raw_text = pdf_page.get_text("text")
                normalized = normalize_text(raw_text)
                has_text_layer = len(normalized) >= 20
                metadata = {"parser": "pdf", "text_char_count": len(normalized)}
                confidence = None
                if not has_text_layer:
                    ocr_needed = True
                    ocr_result = self.ocr_service.recognize_pdf_page(content, page_number=index)
                    metadata["ocr"] = ocr_result.metadata
                    confidence = ocr_result.confidence
                    if ocr_result.text:
                        raw_text = ocr_result.text
                        normalized = normalize_text(ocr_result.text)
                    else:
                        ocr_unavailable = True
                pages.append(
                    ParsedPage(
                        page_number=index,
                        raw_text=raw_text,
                        normalized_text=normalized,
                        has_text_layer=has_text_layer,
                        ocr_confidence=confidence,
                        metadata=metadata,
                    )
                )
        finally:
            document.close()

        return ParseResult(
            pages=pages,
            parse_status="completed",
            ocr_status="unavailable" if ocr_unavailable else "needed" if ocr_needed else "not_needed",
            extraction_quality_score=_quality_score(pages),
            metadata={"parser": "pdf", "page_count": len(pages)},
        )


class ImageParser:
    supported_mime_types = {"image/png", "image/jpeg"}
    supported_extensions = {".png", ".jpg", ".jpeg"}

    def __init__(self, ocr_service: OCRService | None = None) -> None:
        self.ocr_service = ocr_service or get_ocr_service()

    def parse(self, content: bytes, *, file_name: str) -> ParseResult:
        content_type = "image/png" if Path(file_name).suffix.lower() == ".png" else "image/jpeg"
        ocr_result = self.ocr_service.recognize_image(content, content_type=content_type)
        normalized = normalize_text(ocr_result.text)
        page = ParsedPage(
            page_number=1,
            raw_text=ocr_result.text,
            normalized_text=normalized,
            has_text_layer=False,
            ocr_confidence=ocr_result.confidence,
            metadata={"parser": "image", "ocr": ocr_result.metadata},
        )
        return ParseResult(
            pages=[page],
            parse_status="completed",
            ocr_status="completed" if normalized else ocr_result.status,
            extraction_quality_score=_quality_score([page]),
            metadata={"parser": "image"},
        )


PARSERS: tuple[DocumentParser, ...] = (
    PDFParser(),
    DOCXParser(),
    XLSXParser(),
    TextParser(),
    CSVParser(),
    ImageParser(),
)


def get_parser(content_type: str, file_name: str) -> DocumentParser:
    suffix = Path(file_name).suffix.lower()
    normalized_type = content_type.split(";")[0].strip().lower()
    for parser in PARSERS:
        if normalized_type in parser.supported_mime_types and suffix in parser.supported_extensions:
            return parser
    for parser in PARSERS:
        if suffix in parser.supported_extensions:
            return parser
    raise ValueError(f"No parser registered for {normalized_type or suffix}")
