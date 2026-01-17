FROM python:3.13-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt /app/
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

RUN echo 'import urllib.request \n\
import sys \n\
 \n\
def check_health(): \n\
    try: \n\
        # Checks the Django app on port 8000\n\
        urllib.request.urlopen("http://localhost:8000/", timeout=5) \n\
        sys.exit(0) \n\
    except Exception: \n\
        sys.exit(1) \n\
 \n\
if __name__ == "__main__": \n\
    check_health()' > /app/healthcheck.py

# Define the healthcheck within the image
HEALTHCHECK --interval=20s --timeout=10s --start-period=10s --retries=3 \
  CMD python /app/healthcheck.py

COPY . /app/

# Create staticfiles directory
RUN mkdir -p /app/staticfiles

# Expose port
EXPOSE 8000