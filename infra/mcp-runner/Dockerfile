FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY runner.py mcp_config.json ./

# Mount Docker socket at runtime: -v /var/run/docker.sock:/var/run/docker.sock
ENV PYTHONUNBUFFERED=1
CMD ["python", "runner.py"]
