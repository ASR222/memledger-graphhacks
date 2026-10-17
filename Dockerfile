# MemLedger: API + console in one container. Cloud Run sets $PORT.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

# libstdc++/libgcc are needed by the embedded FalkorDB binary (MEMLEDGER_EMBEDDED_DB=1).
RUN apt-get update \
 && apt-get install -y --no-install-recommends libstdc++6 libgcc-s1 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY memledger ./memledger
COPY scripts ./scripts
COPY data ./data

RUN useradd --create-home app && chown -R app /app
USER app

ENV PORT=8080 \
    MEMLEDGER_EXTRACT=cache \
    MEMLEDGER_AGENTS=live \
    MEMLEDGER_DEMO_STATE=/tmp/memledger/demo_state.json
EXPOSE 8080
CMD ["python", "-m", "memledger.serve"]
