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

# Install Rust system-wide (required for pynotatin)
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal
ENV PATH="/root/.cargo/bin:${PATH}"

# Install uv for faster package installation
ADD https://astral.sh/uv/install.sh /tmp/uv-installer.sh
RUN sh /tmp/uv-installer.sh && rm /tmp/uv-installer.sh
ENV PATH="/root/.local/bin:${PATH}"

# Copy requirements and install Python dependencies with uv
COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

# Create non-root user for running the worker
RUN groupadd -r oai --gid=1000 && \
    useradd -r -g oai --uid=1000 --home-dir=/home/oai --shell=/bin/bash oai && \
    mkdir -p /home/oai /data/investigations /tmp && \
    chown -R oai:oai /home/oai /data/investigations && \
    chmod 1777 /tmp

# Copy application code and set ownership
COPY app/ ./app/
COPY worker/ ./worker/
RUN chown -R oai:oai /app

# Switch to non-root user
USER oai

# Set Python path
ENV PYTHONPATH=/app

# Run the worker
CMD ["python", "-m", "worker.main"]
