FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app/ ./app/

# Run - Railway sets PORT env variable
ENV PORT=8000
EXPOSE $PORT
CMD uvicorn app.main:app --host 0.0.0.0 --port $PORT
