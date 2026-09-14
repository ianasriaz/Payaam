# Payaam (پیام) - Container Runtime for AWS AgentCore / ECS / Fargate
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Expose port for Visual Sandbox / Health Check API
EXPOSE 8000

# Default entrypoint runs the autonomous Purelymail background worker daemon
CMD ["python", "-m", "src.handlers.email_worker"]
