# 1. Use a slim Python image for production efficiency
FROM python:3.11-slim

# 2. Set environment variables to prevent Python from writing .pyc files
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 3. Set work directory
WORKDIR /app

# 4. Install system dependencies (if needed for extensions)
RUN apt-get update && apt-get install -y --no-install-recommends gcc && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 5. Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copy application code
COPY . .

# 7. Expose the port (Documentary only)
EXPOSE 8000

# 8. Run the application
# We use '0.0.0.0' to allow external access inside the container
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]