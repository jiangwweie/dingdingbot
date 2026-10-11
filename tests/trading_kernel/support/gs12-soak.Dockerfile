# Local/disposable GS-12 tooling only, never a Tokyo runtime image.
# Build from repository root: docker build -f tests/trading_kernel/support/gs12-soak.Dockerfile -t brc-gs12-python:local-20261011 .
FROM postgres:16-alpine@sha256:4e6e670bb069649261c9c18031f0aded7bb249a5b6664ddec29c013a89310d50
RUN apk add --no-cache python3 py3-pip && python3 -m venv /opt/gs12-venv
COPY requirements.txt /opt/gs12-requirements.txt
COPY tests/trading_kernel/support/gs12-soak-constraints.txt /opt/gs12-constraints.txt
RUN /opt/gs12-venv/bin/pip install --no-cache-dir -r /opt/gs12-requirements.txt -c /opt/gs12-constraints.txt pytest pytest-asyncio
ENV PYTHONDONTWRITEBYTECODE=1
ENTRYPOINT ["/opt/gs12-venv/bin/python"]
