FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy notifier script
COPY notifier.py .
RUN chmod +x notifier.py

# Run the notifier
CMD ["python", "-u", "notifier.py"]
