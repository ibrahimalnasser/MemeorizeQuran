#!/bin/bash

# Quran Hifz Platform - Startup Script
# For VPS deployment

echo "Starting Quran Memorization Platform..."

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install/update requirements
echo "Installing requirements..."
pip install -r requirements.txt

# Set permissions for database
chmod 644 hifz.db 2>/dev/null || echo "Database file not found, will be created on first run"

# Start Streamlit
echo "Starting Streamlit on port 8501..."
streamlit run app.py --server.port=8501 --server.address=0.0.0.0
