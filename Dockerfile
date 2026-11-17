FROM pgvector/pgvector:0.8.1-pg16-bookworm
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3-venv libgomp1 tini ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/hospital
ENV PATH="/opt/venv/bin:$PATH" MODEL_DIR=/opt/models \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TOKENIZERS_PARALLELISM=false
COPY requirements.txt scripts/fetch_embedding.py /opt/hospital/
RUN python3 -m venv /opt/venv \
    && pip install --no-cache-dir -r requirements.txt \
    && python fetch_embedding.py
COPY app /opt/hospital/app
COPY deploy/start.sh /usr/local/bin/start-hospital
RUN chmod 755 /usr/local/bin/start-hospital
EXPOSE 8080
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/start-hospital"]
