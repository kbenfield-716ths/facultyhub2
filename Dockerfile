# Dockerfile — FacultyHub Adaptable (DOM multi-division)

FROM python:3.11-slim

WORKDIR /app

# Python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Backend code + optimizer + migrations
COPY backend /app/backend
COPY moonlighter_optimizer.py /app/moonlighter_optimizer.py
COPY migrations /app/migrations

# Seed data the app reads on first boot
COPY backend/seed_data/faculty.csv /app/faculty.csv

# Frontend: root-level static files plus the icons/ and admin/ trees.
# (.dockerignore keeps dev artifacts — staff.db, venv, dom-night-scheduling — out.)
COPY . /tmp/build/
RUN find /tmp/build -maxdepth 1 -type f \
      \( -iname "*.html" -o -iname "*.css" -o -iname "*.js" -o -iname "*.json" \
         -o -iname "*.svg" -o -iname "*.ico" \) -exec cp {} /app/ \; && \
    if [ -d /tmp/build/icons ]; then cp -r /tmp/build/icons /app/; fi && \
    if [ -d /tmp/build/admin ]; then cp -r /tmp/build/admin /app/; fi && \
    rm -rf /tmp/build

# Volume mount point for the SQLite database
RUN mkdir -p /data

# Entrypoint seeds the test instance (idempotent) then launches the app
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

ENV PYTHONUNBUFFERED=1
EXPOSE 8080

ENTRYPOINT ["/app/docker-entrypoint.sh"]
