# Deal Hunter -- API + scanner in one container.
# Build:  docker build -t deal-hunter .
# Run:    docker run -d --name deal-hunter --env-file .env -p 8000:8000 -v dealdata:/data deal-hunter
FROM mcr.microsoft.com/playwright/python:v1.49.1-noble

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    API_HOST=0.0.0.0 \
    API_PORT=8000 \
    DB_PATH=/data/deals.db \
    BACKUP_DIR=/data/backups \
    SITE_DIR=/app/site \
    RUN_MODE=all

COPY requirements.txt .
RUN pip install -r requirements.txt \
 # make sure the browser matches whatever Playwright version pip installed
 && python -m playwright install --with-deps chromium

COPY . .
RUN mkdir -p /data /app/logs

VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=60s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health').status==200 else 1)" || exit 1

# RUN_MODE: api (API only) | loop (scanner only) | all (both)
CMD ["sh", "-c", "python main.py ${RUN_MODE}"]
