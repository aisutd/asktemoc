FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

WORKDIR /app

# System deps (if you add more heavy libs later, extend this)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install a minimal, container-focused dependency set to avoid resolver issues
# from the much larger local development requirements.
COPY requirements-docker.txt /app/requirements-docker.txt
RUN pip install --upgrade pip && pip install -r /app/requirements-docker.txt

# Copy application code
COPY . /app

# Expose FastAPI default port
EXPOSE 8000

# Uvicorn entrypoint
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

