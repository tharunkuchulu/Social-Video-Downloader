FROM python:3.9-slim

# Install dependencies for Chrome and ffmpeg
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install Chrome
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Expose the port
EXPOSE 8000

# Command to run the app
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-w", "4", "main:app", "--bind", "0.0.0.0:8000"]