# Use Python 3.11 as specified in the project guide
FROM python:3.11-slim

# Prevent Python from writing pyc files to disc and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set the working directory to /app
WORKDIR /app

# Copy the requirements file first to leverage Docker cache
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into a 'backend' directory
# This preserves the package structure so relative imports (e.g. 'from .routers') work
# when running as 'uvicorn backend.main:app'
COPY . ./backend

# Set PYTHONPATH so python can find the 'backend' package
ENV PYTHONPATH=/app

# Expose the default FastAPI port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
