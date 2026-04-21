# Parser Contract

Every parser should implement:

```python
class DocumentParser:
    def can_handle(self, mime_type: str) -> bool: ...
    def parse(self, file_path: str) -> ParsedDocument: ...
```

Initial parser targets:

- PDF text parser
- OCR PDF parser
- DOCX parser
- TXT parser
- CSV/XLSX extractor
- image OCR parser
