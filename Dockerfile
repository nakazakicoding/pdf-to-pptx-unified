FROM python:3.11-slim

# Install system dependencies (tesseract, fonts)
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-jpn \
    tesseract-ocr-eng \
    libgl1 \
    fonts-noto-cjk \
    fonts-noto-cjk-extra \
    fonts-takao-gothic \
    fonts-takao-mincho \
    fonts-ipafont-gothic \
    fonts-ipafont-mincho \
    fonts-ipaexfont-gothic \
    fonts-ipaexfont-mincho \
    fonts-vlgothic \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 10000

# Run the application
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "10000"]
