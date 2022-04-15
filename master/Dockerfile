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
    pip install --upgrade --cache-dir /pip_cache pip setuptools wheel

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
COPY master/requirements.txt .
RUN --mount=type=cache,target=/pip_cache pip install --cache-dir /pip_cache -r requirements.txt
COPY master/main.py /app/main.py
COPY master/logging.cfg /app/logging.cfg


ENV HTTP_PORT 8000
EXPOSE 8000

HEALTHCHECK --interval=1m \
    --timeout=3s \
    --retries=3 \
    CMD [\
        "http", \
        "-v", \
        "--timeout=0.5", \
        "--check-status", \
        "--pretty=format", \
        "--", \
        "GET", "localhost:8000/health" \
    ]

ARG userid
ARG username
RUN useradd -rmu ${userid} ${username} || echo "user already exists!"

RUN chown -R ${username} /app
USER ${username}
ENTRYPOINT ["python", "-W", "ignore", "/app/main.py"]
