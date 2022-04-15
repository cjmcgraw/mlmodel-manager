FROM tensorflow/serving:2.5.1 as base
RUN apt-get -yqq update && \
    apt-get install -yqq python3-dev python3-pip google-perftools && \
    apt-get install -yqq telnet tcpdump net-tools dnsutils iproute2 iputils-ping less vim && \
    apt-get install -yqq python3.8 && \
    rm -rf /var/lib/apt/lists/*

ENV LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libtcmalloc.so.4.3.0

RUN mkdir /pip_cache
RUN --mount=type=cache,target=/pip_cache \
    python3.8 \
        -m pip \
            --cache-dir /pip_cache \
            install --upgrade pip

ADD model_manager_lib /model_manager_lib
RUN --mount=type=cache,target=/pip_cache \
    python3.8 \
        -m pip \
            --cache-dir /pip_cache \
            install -r /model_manager_lib/requirements.txt

RUN --mount=type=cache,target=/pip_cache \
    python3.8 \
        -m pip \
            --cache-dir /pip_cache \
            install -e /model_manager_lib

WORKDIR /app
COPY tfserving/requirements.txt .
RUN --mount=type=cache,target=/pip_cache \
    python3.8 \
        -m pip \
            --cache-dir /pip_cache \
            install -r requirements.txt

COPY tfserving/model-server-entrypoint.sh .
COPY tfserving/healthcheck.py .
COPY tfserving/monitoring.config .

HEALTHCHECK --interval=1m \
    --timeout=5s \
    --retries=3 \
    CMD ["python3.8" ,"/app/healthcheck.py"]

ARG userid
ARG username

RUN useradd -rmu ${userid} ${username} | echo "user already exists"
USER ${username}
ENTRYPOINT [ "/app/model-server-entrypoint.sh" ]
