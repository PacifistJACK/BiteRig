# ---- Base image ----
FROM python:3.11-slim

# Set working directory inside container
WORKDIR /app

# Install dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Expose the port uvicorn listens on
EXPOSE 8000

# Start the server
# Azure Container Apps injects PORT env var; fall back to 8000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
