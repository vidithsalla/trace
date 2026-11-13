FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir uv==0.13.7

COPY apps/worker/pyproject.toml apps/worker/uv.lock /app/
RUN uv sync --frozen --no-install-project

COPY apps/worker/ /app/
COPY apps/api/app/ /app/app/
COPY seed_data/ /app/seed_data/
COPY seed_truth/ /app/seed_truth/
COPY infra/scripts/worker_start.sh /app/worker_start.sh

RUN chmod +x /app/worker_start.sh

CMD ["/app/worker_start.sh"]
