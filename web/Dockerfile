# syntax=docker/dockerfile:1.4
# Web voice-assistant gateway + static UI.
# Serves HTTPS with a self-signed cert: browsers require a secure context for
# microphone access, and the pilot has no domain for a CA-issued cert.
FROM mwader/static-ffmpeg:7.1 AS ffmpeg

FROM python:3.11-slim

WORKDIR /app

COPY web/requirements.txt /app/web/requirements.txt
RUN pip install --no-cache-dir -r /app/web/requirements.txt

# ffmpeg: transcode browser recordings (WebM/Opus, MP4/AAC) to WAV for STT.
# Copied from a static-binary image rather than apt-installed — deb.debian.org
# isn't reachable through this network's proxy for anything but tiny files.
COPY --from=ffmpeg /ffmpeg /usr/local/bin/ffmpeg

# Self-signed TLS cert (pilot only — replace with a real cert behind a domain).
# Generated with Python's cryptography lib instead of the openssl CLI, same
# apt-unreachable reason as ffmpeg above.
RUN mkdir -p /certs && pip install --no-cache-dir cryptography && python3 <<'PYEOF'
import datetime
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "forte-voice-pilot")])
now = datetime.datetime.now(datetime.timezone.utc)
cert = (
    x509.CertificateBuilder()
    .subject_name(name)
    .issuer_name(name)
    .public_key(key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(now)
    .not_valid_after(now + datetime.timedelta(days=730))
    .sign(key, hashes.SHA256())
)
with open("/certs/key.pem", "wb") as f:
    f.write(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ))
with open("/certs/cert.pem", "wb") as f:
    f.write(cert.public_bytes(serialization.Encoding.PEM))
PYEOF
RUN pip uninstall -y cryptography

COPY web /app/web

EXPOSE 8443

CMD ["uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "8443", \
     "--ssl-keyfile", "/certs/key.pem", "--ssl-certfile", "/certs/cert.pem"]
