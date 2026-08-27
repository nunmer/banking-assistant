# DejaVu Sans: a Unicode TTF (Cyrillic + Latin) for the statement PDF —
# python:3.12-slim ships no fonts at all, and fpdf2's built-in core fonts
# are Latin-1 only, which can't render Russian/Kazakh statement text.
# Pulled from matplotlib's bundled copy via pip rather than apt-installed —
# deb.debian.org isn't reachable through this network's proxy for anything
# but tiny files; matplotlib itself is discarded, only its two font files
# are kept.
FROM python:3.12-slim AS fonts
RUN pip install --no-cache-dir matplotlib && \
    mkdir -p /fonts && \
    cp "$(python3 -c 'import matplotlib; print(matplotlib.get_data_path())')"/fonts/ttf/DejaVuSans.ttf /fonts/ && \
    cp "$(python3 -c 'import matplotlib; print(matplotlib.get_data_path())')"/fonts/ttf/DejaVuSans-Bold.ttf /fonts/

FROM python:3.12-slim

WORKDIR /app

COPY --from=fonts /fonts/DejaVuSans.ttf /fonts/DejaVuSans-Bold.ttf /usr/share/fonts/truetype/dejavu/

COPY orchestrator/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY orchestrator ./orchestrator

EXPOSE 8000

# Run Alembic migrations then start the server.
CMD ["sh", "-c", "alembic -c orchestrator/alembic.ini upgrade head && uvicorn orchestrator.main:app --host 0.0.0.0 --port 8000"]
