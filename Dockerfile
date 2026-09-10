FROM python:3.12-slim

WORKDIR /app

# Install system utilities & GDAL/rasterio runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libgdal-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency specifications
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Initialize DB & sample datasets during build
RUN python -c "from app.db.session import init_db; from scripts.generate_sample import generate_all_samples; init_db(); generate_all_samples()"

EXPOSE 8000

CMD ["python", "run.py", "--host", "0.0.0.0", "--port", "8000"]
