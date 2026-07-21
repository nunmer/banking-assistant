# Web voice-bot gateway + static UI.
# Serves HTTPS with a self-signed cert: browsers require a secure context for
# microphone access, and the pilot has no domain for a CA-issued cert.
FROM python:3.11-slim

WORKDIR /app

COPY web/requirements.txt /app/web/requirements.txt
RUN pip install --no-cache-dir -r /app/web/requirements.txt

# Self-signed TLS cert (pilot only — replace with a real cert behind a domain).
RUN mkdir -p /certs && \
    apt-get update && apt-get install -y --no-install-recommends openssl && \
    openssl req -x509 -newkey rsa:2048 -nodes -days 730 \
      -keyout /certs/key.pem -out /certs/cert.pem \
      -subj "/CN=forte-voice-pilot" && \
    apt-get purge -y openssl && apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

COPY web /app/web

EXPOSE 8443

CMD ["uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "8443", \
     "--ssl-keyfile", "/certs/key.pem", "--ssl-certfile", "/certs/cert.pem"]
