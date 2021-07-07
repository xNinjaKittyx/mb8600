import argparse
import json
import logging
import os
import time
import urllib3
from logging.handlers import RotatingFileHandler

from influxdb import InfluxDBClient

from mb8600.modem import MB8600


urllib3.disable_warnings()

logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s::%(levelname)s:%(module)s:%(lineno)d - %(message)s")
fh = RotatingFileHandler(filename=os.path.join(os.getenv("LOG_LOCATION", "./logs"), "data_export.log"), maxBytes=10 * 1024 * 1024, backupCount=10)
fh.setFormatter(formatter)
logger.addHandler(fh)
sh = logging.StreamHandler()
sh.setFormatter(formatter)
logger.addHandler(sh)


parser = argparse.ArgumentParser()
parser.add_argument('--host', default=os.getenv('INFLUX_HOST'), type=str, help="Host where influxdb is located.")
parser.add_argument('--port', default=os.getenv('INFLUX_PORT', 8086), type=int, help="Port Number (default 8086)")
parser.add_argument('--user', default=os.getenv('INFLUX_USER'), help="InfluxDB Username")
parser.add_argument('--pw', default=os.getenv('INFLUX_PASS'), help="InfluxDB Password")
parser.add_argument('--db', default=os.getenv('INFLUX_DB', 'modem-test'), help="InfluxDB Database Name")
parser.add_argument('--fresh', action="store_true", default=False, help="Recreate the influx database.")
parser.add_argument('--sleep', default=os.getenv('SLEEP_TIMER', 30), type=int, help="Time to sleep between data fetching. Recommended to be 30 or higher. (Most likely can't do less than 15)")

# Modem Arguments
parser.add_argument('--mhost', default=os.getenv('MODEM_HOST', "192.168.100.1"), type=str, help="Modem IP.")
parser.add_argument('--muser', default=os.getenv('MODEM_USER', 'admin'), help="InfluxDB Username")
parser.add_argument('--mpw', default=os.getenv('MODEM_PASS', 'password'), help="InfluxDB Password")
parser.add_argument('--loglevel', default=os.getenv('LOG_LEVEL', 'INFO').upper(), help="InfluxDB Password")

args = parser.parse_args()


if __name__ == "__main__":
    my_modem = MB8600(args.mhost, args.muser, args.mpw)
    client = InfluxDBClient(args.host, args.port, args.user, args.pw, args.db)

    try:
        logger.setLevel(logging.getLevelName(args.loglevel))
    except ValueError:
        # Invalid log level
        logger.error(f"Invalid loglevel {args.loglevel}")

    if args.fresh:
        client.drop_database(args.db)
    client.create_database(args.db)

    while True:
        logger.info("Starting Import")
        start_time = time.time()

        try:
            my_modem.login()
            influx_data, data = my_modem.get_influx_data()
            logger.debug(f"Influx Data: {influx_data}")
            logger.debug(f"Data: {data}")
            client.write_points(influx_data)
            # Write to file
            with open ('data.json', 'w') as f:
                f.write(json.dumps(data, indent=2))
            logger.info("Imported data")
        except Exception as e:
            logger.exception(f"Exception raised: {e}")

        sleep = args.sleep - (time.time() - start_time)
        logger.info(f"sleeping for {sleep} seconds")
        if sleep > 0:
            time.sleep(sleep)
