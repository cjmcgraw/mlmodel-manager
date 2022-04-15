# syntax=docker/dockerfile:1.2
FROM python:3.8 as base
ARG userid
ARG username
RUN useradd -rmu ${userid} ${username} || echo "user already exists!"

RUN apt-get update -yqq && apt-get upgrade -yqq
RUN apt-get install -yqq tree
RUN mkdir /pip_cache
WORKDIR /app
RUN --mount=type=cache,target=/pip_cache pip install --cache-dir /pip_cache --upgrade pip
COPY requirements.txt .
RUN --mount=type=cache,target=/pip_cache pip install --cache-dir /pip_cache -r requirements.txt
COPY tests/ .
COPY docker-entrypoint.sh .
RUN curl -sSL https://sdk.cloud.google.com | bash
RUN mv /root/google-cloud-sdk /google-cloud-sdk
ENV PATH "${PATH}:/google-cloud-sdk/bin"
WORKDIR /app

RUN mkdir -p /home/${username}
RUN mkdir -p /tmp
RUN chown -R ${username} /home/${username}
RUN chown -R ${username} /app
RUN chown -R ${username} /tmp

USER ${username}
ENTRYPOINT ["/app/docker-entrypoint.sh"]
