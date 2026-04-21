FROM python:3.12-slim

WORKDIR /app

COPY infra/scripts/mock_vllm.py /app/mock_vllm.py

CMD ["python", "/app/mock_vllm.py"]
