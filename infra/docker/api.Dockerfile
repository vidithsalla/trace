FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN pip install uv

COPY apps/api/pyproject.toml /app/pyproject.toml
RUN uv sync --frozen || uv sync

COPY apps/api/ /app/
COPY seed_data/ /app/seed_data/
COPY seed_truth/ /app/seed_truth/
COPY infra/scripts/api_start.sh /app/api_start.sh

RUN chmod +x /app/api_start.sh

CMD ["/app/api_start.sh"]
