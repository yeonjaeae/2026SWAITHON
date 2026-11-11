FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

FROM base AS gateway
COPY gateway /app/gateway
RUN pip install -r /app/gateway/requirements.txt
CMD ["python", "-m", "uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", "8000", "--limit-concurrency", "32"]

FROM base AS candidate
COPY candidate-recommender-v2 /app
RUN pip install -r requirements-postgis.txt
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--limit-concurrency", "16"]

FROM base AS deficit
COPY gateway/requirements*.txt /requirements/
RUN pip install -r /requirements/requirements-deficit.txt
COPY green-deficit /app
CMD ["python", "-m", "uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000", "--limit-concurrency", "16"]

FROM base AS design
COPY gateway/requirements*.txt /requirements/
RUN pip install -r /requirements/requirements-design.txt
COPY green-design-backend /app
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--limit-concurrency", "16"]

FROM base AS ai
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
COPY ai /app
RUN pip install -r requirements.txt
ENV HF_HOME=/model-cache
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--limit-concurrency", "4"]
