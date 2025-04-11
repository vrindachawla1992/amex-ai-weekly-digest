# Stage 1: Build stage
FROM python:3.9-slim AS builder

# Set the working directory in the container
WORKDIR /app

# Copy only the requirements file first to leverage Docker cache
COPY requirements.txt .

# Install build dependencies and requirements
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Stage 2: Runtime stage
FROM python:3.9-slim

# Set the working directory
WORKDIR /app

# Create directories for reports and logs
RUN mkdir -p reports logs

# Copy only necessary files from builder stage
COPY --from=builder /app /app
COPY --from=builder /usr/local/lib/python3.9/site-packages /usr/local/lib/python3.9/site-packages

# Use build arguments for sensitive data with defaults
ARG BREVO_API_KEY=""
ARG SENDER_EMAIL=""
ARG RECIPIENT_EMAILS=""
ARG ANTHROPIC_API_KEY=""
ARG LLM_PROVIDER="anthropic"
ARG LLM_MODEL="claude-3-opus-20240229"

# Set environment variables from build arguments
ENV BREVO_API_KEY=${BREVO_API_KEY}
ENV SENDER_EMAIL=${SENDER_EMAIL}
ENV RECIPIENT_EMAILS=${RECIPIENT_EMAILS}
ENV ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
ENV LLM_PROVIDER=${LLM_PROVIDER}
ENV LLM_MODEL=${LLM_MODEL}

# Optional: Copy .env file if it exists
COPY .env* ./

# Set Python to unbuffered mode
ENV PYTHONUNBUFFERED=1

# Run the script
CMD ["python", "main.py"]
