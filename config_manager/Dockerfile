# syntax=docker/dockerfile:1.2
FROM python:3.8
RUN mkdir /pip_cache


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

RUN --mount=type=cache,target=/pip_cache pip install --cache-dir /pip_cache --upgrade pip setuptools wheel

COPY model_manager_lib/ /model_manager_lib
RUN --mount=type=cache,target=/pip_cache pip install --cache-dir /pip_cache -r /model_manager_lib/requirements.txt
RUN --mount=type=cache,target=/pip_cache pip install --cache-dir /pip_cache -e /model_manager_lib
RUN python -m pytest /model_manager_lib

WORKDIR /app
ADD config_manager/requirements.txt .
RUN --mount=type=cache,target=/pip_cache pip install --cache-dir /pip_cache -r /app/requirements.txt
COPY config_manager/main.py .
COPY config_manager/logging.cfg .

ENV PORT 8002
EXPOSE 8002

HEALTHCHECK --interval=1m \
    --timeout=2s \
    --retries=15 \
    CMD [\
        "http", \
        "-v", \
        "--timeout=0.5", \
        "--check-status", \
        "--pretty=format", \
        "--", \
        "GET", "localhost:8002/health" \
   ]

ARG userid
ARG username
RUN useradd -rmu ${userid} ${username} || echo "user already exists!"
RUN mkdir -p /home/${username}
RUN chown -R ${username} /home/${username}
RUN chown -R ${username} /app
USER ${username}
ENTRYPOINT ["python", "-W", "ignore", "/app/main.py"]

