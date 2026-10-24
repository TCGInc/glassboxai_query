FROM python:3.12-slim

# Run as the host user so files written to the bind mounts (notebooks, tests,
# agent) are not owned by root. start.sh passes the real IDs.
ARG HOST_UID=1000
ARG HOST_GID=1000
RUN groupadd --gid "$HOST_GID" glassbox \
    && useradd --uid "$HOST_UID" --gid "$HOST_GID" --create-home glassbox

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

ENV PYTHONPATH=/workspace
RUN mkdir /workspace && chown glassbox:glassbox /workspace
WORKDIR /workspace
USER glassbox
