# Use official Python base image
FROM python:3.13.3-alpine@sha256:18159b2be11db91f84b8f8f655cd860f805dbd9e49a583ddaac8ab39bf4fe1a7

# Set work directory
WORKDIR /app

# Copy files
COPY . /app

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose port 5001
EXPOSE 5001

# Run the app
CMD ["python", "app.py"]
