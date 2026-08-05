FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

RUN useradd --system --uid 10001 --home-dir /nonexistent --shell /usr/sbin/nologin connector \
    && mkdir -p /data \
    && chown connector:connector /data
USER connector
EXPOSE 8091
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8091", "--access-log"]
