FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN pip install uv

COPY apps/worker/pyproject.toml /app/pyproject.toml
RUN uv sync --frozen || uv sync

COPY apps/worker/ /app/
COPY apps/api/app/ /app/app/
COPY seed_data/ /app/seed_data/
COPY seed_truth/ /app/seed_truth/
COPY infra/scripts/worker_start.sh /app/worker_start.sh

RUN chmod +x /app/worker_start.sh

CMD ["/app/worker_start.sh"]
