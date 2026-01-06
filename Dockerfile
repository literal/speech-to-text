FROM debian:trixie-slim

# Install base dependencies (no device access needed - pure transcription API)
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    curl \
    procps \
    python3 \
    python3-pip \
    python3-venv

# Install whisper dependencies
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    python3-charset-normalizer \
    python3-filelock \
    python3-fsspec \
    python3-jinja2 \
    python3-llvmlite \
    python3-markupsafe \
    python3-more-itertools \
    python3-mpmath \
    python3-networkx \
    python3-numba \
    python3-numpy \
    python3-regex \
    python3-requests \
    python3-setuptools \
    python3-sympy \
    python3-typing-extensions

# Install test dependencies (portaudio for sounddevice)
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    portaudio19-dev \
    python3-evdev \
    python3-iniconfig \
    python3-mypy \
    python3-pluggy \
    python3-pygments \
    python3-pytest

# Set the UID/GID of the user:group to the IDs of the user using this Dockerfile
ARG USER=nonroot
ARG GROUP=nonroot
ARG UID=1000
ARG GID=1000
RUN echo user:group ${USER}:${GROUP}
RUN echo uid:gid ${UID}:${GID}
RUN getent group ${GROUP} || groupadd --non-unique --gid ${GID} ${GROUP}
RUN getent passwd ${USER} || useradd --uid ${UID} --gid ${GID} --create-home --shell /bin/bash ${USER}
RUN if [ "${GID}" != "1000" ] || [ "${UID}" != "1000" ]; then \
      groupmod --non-unique --gid ${GID} ${GROUP} && \
      usermod --uid ${UID} --gid ${GID} ${USER} && \
      chown -R ${UID}:${GID} /home/${USER}; \
    fi

ENV XDG_CACHE_HOME=/.whisper
RUN mkdir ${XDG_CACHE_HOME} && chown -R ${USER}:${USER} ${XDG_CACHE_HOME} && chmod 0700 ${XDG_CACHE_HOME}

WORKDIR /app
RUN chown -R ${USER}:${USER} /app && chmod 0700 /app
USER ${USER}

RUN whoami
RUN id

COPY --chown=nonroot:nonroot requirements.txt .
RUN cd /home/${USER} && python3 -m venv --system-site-packages venv && . venv/bin/activate
# Debian's python3-torch is slow
# Use two step installation as a workaround to install cpu-only torch
# See https://github.com/huggingface/transformers/issues/39780
RUN . /home/${USER}/venv/bin/activate && python -m pip install torch==2.* --index-url https://download.pytorch.org/whl/cpu
RUN . /home/${USER}/venv/bin/activate && python -m pip install -r requirements.txt
RUN echo "if [ -f /home/${USER}/venv/bin/activate  ]; then . /home/${USER}/venv/bin/activate; fi" >> /home/${USER}/.bashrc

COPY --chown=nonroot:nonroot transcription_server.py .

# Avoid overloading the system with too many openblas threads
ENV OPENBLAS_NUM_THREADS=1

# Expose the HTTP API port
EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

CMD ["/home/nonroot/venv/bin/python", "/app/transcription_server.py"]
