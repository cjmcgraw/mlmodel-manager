FROM python:3.7
RUN apt-get update -y
WORKDIR /app/
ADD requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt
ADD docker-entrypoint.sh /app/docker-entrypoint.sh
ADD *.py /app/
ENTRYPOINT ["/app/docker-entrypoint.sh"]

