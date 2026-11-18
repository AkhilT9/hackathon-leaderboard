FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy server code and seed data
COPY server_7400.py .
COPY leaderboard_data.json .

# Default port (Railway and Render provide $PORT)
EXPOSE 7400

# Run the server
CMD ["python", "server_7400.py"]

