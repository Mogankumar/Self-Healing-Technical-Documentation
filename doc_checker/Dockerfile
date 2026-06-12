# doc_checker/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install git (needed for diff parsing)
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Entry point
CMD ["python", "-m", "doc_checker.main"]