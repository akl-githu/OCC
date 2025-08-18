# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Install system dependencies required for building mysqlclient
# This is the key fix for the "pkg-config not found" error
RUN apt-get update && apt-get install -y \
    default-libmysqlclient-dev \
    build-essential \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
COPY . .

# Make port 5000 available to the world outside this container
EXPOSE 5000

# Run the app.py when the container launches
CMD ["python", "app.py"]
