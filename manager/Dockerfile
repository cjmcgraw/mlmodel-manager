FROM tiangolo/uvicorn-gunicorn-fastapi:python3.7

MAINTAINER carlm@accretivetg.com

ARG BUILD_ID
RUN apt-get update -y
RUN apt-get install -y \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg-agent \
    software-properties-common
RUN curl -fsSL https://download.docker.com/linux/debian/gpg | apt-key add -
RUN apt-key fingerprint 0EBFCD88
RUN add-apt-repository \
   "deb [arch=amd64] https://download.docker.com/linux/debian \
   $(lsb_release -cs) \
   stable"
RUN apt-get update -y
RUN apt-get install -y docker-ce docker-ce-cli containerd.io
COPY ./requirements.txt /app/requirements.txt
RUN pip3 install -r /app/requirements.txt

COPY ./server.py /app/server.py
COPY ./swarm.py /app/swarm.py
COPY ./templates /app/templates

EXPOSE 80
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=2 CMD curl --fail localhost:80/health/test
ENV APP_MODULE server:app
ENV ENVIRONMENT development
ENV BUILD_ID $BUILD_ID
