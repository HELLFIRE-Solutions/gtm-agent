# Minimal image for gtm_agent.inbox.server -- the CLI/orchestrator itself
# still runs wherever Bob invokes it, unpackaged. This Dockerfile exists
# only to keep the one persistent piece (the chat widget's HTTP endpoint)
# running on the session-02 droplet.
FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml ./
COPY src/ ./src/

RUN pip install --no-cache-dir ".[pg]"

EXPOSE 8090
CMD ["python", "-m", "gtm_agent.inbox.server"]
