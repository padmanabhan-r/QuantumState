FROM python:3.12-slim

# Install uv (for uvx docker-mcp)
RUN pip install --no-cache-dir uv

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY runner.py mcp_config.json ./

# Mount Docker socket at runtime: -v /var/run/docker.sock:/var/run/docker.sock
CMD ["python", "runner.py"]
