FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for parsing libraries
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    git \
    libxml2-dev \
    libxslt-dev \
    curl \
    make \
    autoconf \
    automake \
    libtool \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Install Rust (required for pynotatin)
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

# Install uv for faster package installation
ADD https://astral.sh/uv/install.sh /tmp/uv-installer.sh
RUN sh /tmp/uv-installer.sh && rm /tmp/uv-installer.sh
ENV PATH="/root/.local/bin:${PATH}"

# Copy requirements and install Python dependencies with uv
COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY worker/ ./worker/

# Set Python path
ENV PYTHONPATH=/app

# Run the worker
CMD ["python", "-m", "worker.main"]
