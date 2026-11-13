# Trace - Sovereign Discovery Copilot Local Development

The default path assumes Docker Desktop on Apple Silicon with limited memory. Run the lightweight core stack first:

```bash
cp .env.example .env
make phase0-verify
make up
```

Useful URLs:

- Web app: `http://localhost:3000`
- API docs: `http://localhost:8000/docs`
- Readiness: `http://localhost:8000/health/ready`
- Metrics: `http://localhost:8000/metrics`

Demo credentials after seeding:

- `attorney@trace.local`
- `admin@trace.local`
- `reviewer@trace.local`
- Password: `trace-demo-password`

Seed and eval commands:

- `make seed`: fast Mode B bootstrap from processed text artifacts.
- `make seed-raw`: Mode A raw-ingestion seed using `seed_data/raw/acme_matter`.
- `make eval`: run the Acme MVP eval harness.

Optional add-ons:

- `make up-model`: starts the optional model-serving overlay.
- `make up-ocr`: starts the optional OCR overlay.
- `make up-full`: starts core plus optional model and OCR overlays.

The core app does not require local vLLM or OCR services. The default model provider remains `MockModelClient`; production/self-hosted inference remains behind the OpenAI-compatible adapter.
