import json
import os

import urllib3

import mb8600.modem as modem

urllib3.disable_warnings()


if __name__ == "__main__":
    my_modem = modem.MB8600(
        os.getenv("MODEM_HOST", "192.168.100.1"),
        os.getenv("MODEM_USER", "admin"),
        os.getenv("MODEM_PASSWORD", "INFO"),
    )
    print(my_modem.login())
    print(json.dumps(my_modem.get_data(), indent=2))
