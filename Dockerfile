FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

# Switch to root to install dependencies if needed, though this image comes with mostly everything
USER root

WORKDIR /app

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install the exact chromium version required by this playwright version
RUN playwright install chromium

COPY . .

# Run the bot
CMD ["python", "bot.py"]
