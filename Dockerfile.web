FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and config directories
COPY src/ src/
COPY static/ static/
COPY config/ config/

# Copy only catalogue.json and workday.csv from data directory
RUN mkdir -p data
COPY data/catalogue.json data/workday.csv ./data/

# Expose the application port
EXPOSE 8080

# Run FastAPI web app using uvicorn
CMD uvicorn src.web.app:app --host 0.0.0.0 --port 8080
