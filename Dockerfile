FROM python:3.9-slim

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

WORKDIR /app

RUN apt update && apt upgrade -y && apt clean && rm -rf /var/lib/apt/lists/* && pip install --no-cache-dir poetry && mkdir -p /logs


COPY pyproject.toml poetry.lock ./
COPY mb8600/ mb8600/

RUN poetry config virtualenvs.create false \
    && poetry config experimental.new-installer false \
    && poetry install --no-root --no-interaction --no-ansi \
    && pip cache purge

COPY data_export.py reboot.py get_data.py ./


CMD ["/usr/local/bin/poetry", "run", "python", "data_export.py"]
