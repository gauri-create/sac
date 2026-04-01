FROM python:3.11-slim

# Install system dependencies for dlib + OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
    cmake \
    build-essential \
    libopenblas-dev \
    liblapack-dev \
    libx11-dev \
    libgtk-3-dev \
    libboost-all-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

# Create required directories
RUN mkdir -p data/known_faces data/unknown_faces models

EXPOSE 5050

# Default: run dashboard (camera via API start button or env)
CMD ["python", "scripts/run.py"]
