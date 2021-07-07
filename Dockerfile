FROM python:3.9

ENV INFLUX_HOST="localhost" \
    INFLUX_PORT=8086 \
    INFLUX_USER="" \
    INFLUX_PASS="" \
    INFLUX_DB="modem-test" \
    SLEEP_TIMER=30 \
    MODEM_HOST=192.168.100.1 \
    MODEM_USER=admin \
    MODEM_PASS=password \
    LOG_LOCATION="/logs" \
    LOG_LEVEL=INFO

RUN mkdir -p /logs

WORKDIR /app

RUN apt update && apt upgrade -y && apt clean

RUN pip install poetry

COPY pyproject.toml .
COPY poetry.lock .
COPY mb8600/ mb8600/

RUN poetry install

COPY data_export.py .
COPY reboot.py .


CMD ["/usr/local/bin/poetry", "run", "python", "data_export.py"]
