FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && find /usr/local/lib/python3.12/site-packages -depth \
      -type d \( -name tests -o -name __pycache__ \) -exec rm -rf '{}' + \
    && find /usr/local/lib/python3.12/site-packages \
      -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
COPY app ./app
EXPOSE 8008
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8008"]
