FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd -m civic && mkdir -p /app/var/media && chown -R civic /app
USER civic
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && python -m app.cli bootstrap-admin-from-env && (python -m app.demo ensure || echo demo-setup-skipped) && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
