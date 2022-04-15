# syntax=docker/dockerfile:1.2
FROM python:3.8
RUN apt-get update -yqq && \
    apt-get upgrade -yqq && \
    apt-get install -yqq \
        httpie \
        telnet \
        tcpdump \
        net-tools \
        dnsutils \
        less \
        vim \
        iputils-ping \
        iproute2 \
        && \
    rm -rf /var/lib/apt/lists/*

RUN which ping
RUN which ip

RUN mkdir /pip_cache
RUN --mount=type=cache,target=/pip_cache \
    pip install \
        --upgrade \
        --cache-dir /pip_cache \
        pip setuptools wheel

COPY model_manager_lib/ /model_manager_lib

RUN --mount=type=cache,target=/pip_cache \
    pip install \
        --cache-dir /pip_cache \
        -r /model_manager_lib/requirements.txt

RUN --mount=type=cache,target=/pip_cache \
    pip install \
        --cache-dir /pip_cache \
        -e /model_manager_lib

WORKDIR /app
COPY remote_model_puller/requirements.txt .
RUN --mount=type=cache,target=/pip_cache \
    pip install \
        --cache-dir /pip_cache \
        -r requirements.txt
COPY remote_model_puller/main.py /app/main.py
COPY remote_model_puller/logging.cfg .

ENV HTTP_PORT 8001
EXPOSE 8001

HEALTHCHECK --interval=5m \
    --timeout=2s \
    --retries=12 \
    CMD [ \
        "http", \
        "-v", \
        "--timeout=0.5", \
        "--check-status", \
        "--pretty=format", \
        "--", \
        "GET", "localhost:8001/health"\
    ]

ARG userid
ARG username
RUN useradd -rmu ${userid} ${username} || echo "user already exists!"
RUN mkdir -p /home/${username}
RUN chown -R ${username} /home/${username}
RUN chown -R ${username} /app
USER ${username}
ENTRYPOINT ["python", "/app/main.py"]
