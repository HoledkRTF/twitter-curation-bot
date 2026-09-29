FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for Playwright
RUN apt-get update && apt-get install -y \
    wget \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Chromium and all its OS dependencies
RUN playwright install --with-deps chromium

COPY . .

# Run the bot
CMD ["python", "bot.py"]
