FROM python:3.12-slim AS builder

# Install build tools needed for asyncpg, parsers, and git for notatin
# Also install WeasyPrint dependencies (Cairo, Pango, GDK-PixBuf)
# Also install unar for RAR archive extraction (free alternative to unrar)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    git \
    libpq-dev \
    libxml2-dev \
    libxslt-dev \
    curl \
    make \
    autoconf \
    automake \
    libtool \
    pkg-config \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    unar \
    && rm -rf /var/lib/apt/lists/*

# Install Rust (required for pynotatin)
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

# Install uv for faster package installation
ADD https://astral.sh/uv/install.sh /tmp/uv-installer.sh
RUN sh /tmp/uv-installer.sh && rm /tmp/uv-installer.sh
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app
COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

# Copy application code (the Docker context is the ./api directory)
COPY . .

EXPOSE 8000

# The package root inside the container is "app", not "api"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
