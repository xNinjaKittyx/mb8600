
import hashlib
import hmac
import json
import logging
import re
import time
from datetime import datetime, timedelta
from typing import Optional, Tuple

import requests


log = logging.getLogger(__name__)


SOAP_NAMESPACE = "http://purenetworks.com/HNAP1/"

GET_ACTIONS = [
    "GetHomeConnection",
    "GetHomeAddress",
    "GetMotoStatusSoftware",
    "GetMotoStatusLog",
    "GetMotoLagStatus",
    "GetMotoStatusConnectionInfo",
    "GetMotoStatusDownstreamChannelInfo",
    "GetMotoStatusStartupSequence",
    "GetMotoStatusUpstreamChannelInfo",
]


class MB8600:

    def __init__(self, host: str, username: Optional[str] = None, password: Optional[str] = None, secure: bool = True, verify: bool = False):

        self.host = host
        self.username = username
        self.password = password
        self.hnap_url = f"http{'s' if secure else ''}://{host}/HNAP/"
        self.session = requests.session()
        self.session.verify = verify
        self._cred_regex = re.compile("^[A-Za-z0-9]+$")

    def _millis(self) -> int:
        return int(round(time.time() * 1000)) % 2000000000000

    def _md5sum(self, key: str, data: str) -> str:
        hmc = hmac.new(key.encode("utf-8"), digestmod=hashlib.md5)
        hmc.update(data.encode("utf-8"))
        return hmc.hexdigest().upper()

    def _hnap_auth(self, key: str, data: str) -> str:
        return f"{self._md5sum(key, data)} {self._millis()}"

    def _run_hnap_command(self, action: str, params: dict) -> dict:
        action_uri = f'"{SOAP_NAMESPACE}{action}"'
        private_key = self.session.cookies.get("PrivateKey", path="/", default="withoutloginkey")

        response = self.session.post(
            self.hnap_url,
            data=json.dumps({action: params}),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "SOAPAction": action_uri,
                "HNAP_AUTH": self._hnap_auth(private_key, f"{self._millis()}{action_uri}"),
            },
        )

        try:
            result = response.json()
        except json.JSONDecodeError:
            log.exception(response.content)
            raise

        return result[f"{action}Response"]

    def login(self, username: Optional[str] = None, password: Optional[str] = None) -> bool:
        username = username or self.username
        password = password or self.password

        # Have to do a fake login first
        response = self._run_hnap_command(
            "Login",
            {
                "Action": "request",
                "Captcha": "",
                "LoginPassword": "",
                "PrivateLogin": "LoginPassword",
                "Username": username,
            },
        )

        private_key = self._md5sum(
            f"{response['PublicKey']}{password}", response["Challenge"]
        )

        self.session.cookies.set("uid", response["Cookie"], path="/")
        self.session.cookies.set("PrivateKey", private_key, path="/")

        # Now do the real login.
        response = self._run_hnap_command(
            "Login",
            {
                "Action": "login",
                "Captcha": "",
                "LoginPassword": self._md5sum(private_key, response["Challenge"]),
                "PrivateLogin": "LoginPassword",
                "Username": username,
            },
        )

        return response['LoginResult'] == 'OK'

    def get_influx_data(self) -> Tuple[dict, dict]:
        # Cleaned up to work with influxdb
        data = self.get_data()

        influxdb_data = []

        tags = ['Channel', 'ChannelID']

        for value in data['GetMotoStatusDownstreamChannelInfoResponse']['MotoConnDownstreamChannel']:
            influxdb_data.append({
                "measurement": "downstream_channel",
                "tags": {
                    "host": self.host,
                    "Channel": value["Channel"],
                    "ChannelID": value["ChannelID"],

                },
                "time": datetime.utcnow().isoformat(),
                "fields": {
                    field_key: value[field_key] for field_key in value if field_key not in tags
                }
            })

        for value in data['GetMotoStatusUpstreamChannelInfoResponse']['MotoConnUpstreamChannel']:
            influxdb_data.append({
                "measurement": "upstream_channel",
                "tags": {
                    "host": self.host,
                    "Channel": value["Channel"],
                    "ChannelID": value["ChannelID"],
                },
                "time": datetime.utcnow().isoformat(),
                "fields": {
                    field_key: value[field_key] for field_key in value if field_key not in tags
                }
            })


        # Just get all the modem info. Deal with it later.

        influxdb_data.append({
                "measurement": "modem_info",
                "tags": {
                    "host": self.host,
                },
                "time": datetime.utcnow().isoformat(),
                "fields": {
                    **data['GetMotoStatusSoftwareResponse'],
                    **data['GetHomeConnectionResponse'],
                    **data['GetHomeAddressResponse'],
                    **data['GetMotoLagStatusResponse'],
                    **data['GetMotoStatusConnectionInfoResponse'],
                    **data['GetMotoStatusStartupSequenceResponse'],
                }
        })

        # Calculate uptime in seconds

        days, hours, minutes, seconds = [int(val) for val in re.findall(r'\d+', data['GetMotoStatusConnectionInfoResponse']['MotoConnSystemUpTime'])]


        influxdb_data.append({
                "measurement": "uptime",
                "tags": {
                    "host": self.host,
                },
                "time": datetime.utcnow().isoformat(),
                "fields": {
                    "uptime": timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds).total_seconds()
                }
        })

        return influxdb_data, data

    def get_data(self) -> dict:
        data = self._run_hnap_command("GetMultipleHNAPs", {action: "" for action in GET_ACTIONS})
        # Clean up the data a bit
        data['GetMotoStatusLogResponse']['MotoStatusLogList'] = data['GetMotoStatusLogResponse']['MotoStatusLogList'].split('}-{')
        for i, value in enumerate(data['GetMotoStatusLogResponse']['MotoStatusLogList']):
            new_value = value.split('^')
            data['GetMotoStatusLogResponse']['MotoStatusLogList'][i] = {
                "Date": f"{new_value[0].strip()} {new_value[1].strip()}",
                "Priority": new_value[2],
                "Description": new_value[3],
            }

        data['GetMotoStatusDownstreamChannelInfoResponse']['MotoConnDownstreamChannel'] = data['GetMotoStatusDownstreamChannelInfoResponse']['MotoConnDownstreamChannel'].split('|+|')
        data['GetMotoStatusUpstreamChannelInfoResponse']['MotoConnUpstreamChannel'] = data['GetMotoStatusUpstreamChannelInfoResponse']['MotoConnUpstreamChannel'].split('|+|')

        for i, value in enumerate(data['GetMotoStatusDownstreamChannelInfoResponse']['MotoConnDownstreamChannel']):
            new_value = value.split('^')
            data['GetMotoStatusDownstreamChannelInfoResponse']['MotoConnDownstreamChannel'][i] = {
                "Channel": int(new_value[0].strip()),
                "LockStatus": new_value[1].strip(),
                "Modulation": new_value[2].strip(),
                "ChannelID": int(new_value[3].strip()),
                "FreqMHZ": float(new_value[4].strip()),
                "PowerdBmV": float(new_value[5].strip()),
                "SNR": float(new_value[6].strip()),
                "Corrected": int(new_value[7].strip()),
                "Uncorrected": int(new_value[8].strip()),
            }

        for i, value in enumerate(data['GetMotoStatusUpstreamChannelInfoResponse']['MotoConnUpstreamChannel']):
            new_value = value.split('^')
            data['GetMotoStatusUpstreamChannelInfoResponse']['MotoConnUpstreamChannel'][i] = {
                "Channel": int(new_value[0].strip()),
                "LockStatus": new_value[1].strip(),
                "ChannelType": new_value[2].strip(),
                "ChannelID": int(new_value[3].strip()),
                "SymbRate": int(new_value[4].strip()),
                "FreqMHZ": float(new_value[5].strip()),
                "PowerdBmV": float(new_value[6].strip()),
            }
        return data

    def reboot(self) -> dict:

        response = self._run_hnap_command(
            "SetStatusSecuritySettings",
            {
                "MotoStatusSecurityAction": "1",
                "MotoStatusSecXXX": "XXX",
            },
        )

        return response

    def _check_username_and_password(self, value: str) -> bool:
        """
function CheckUsernameAndPassword(value)
{
    var temp = new RegExp("^[A-Za-z0-9]+$");

    if (((value.length!=0) && (!temp.test(value))) || (value.length==0))
    {
        return false;
    }
    return true;
}
        """
        if len(value):
            return bool(self._cred_regex.fullmatch(value))
        else:
            # If Empty, continue as true (modem code does this)
            return True

    def _aes_encrypt128(self, value: str):
        # Honestly seems like too much work, adn I d
        raise NotImplementedError

    def change_credentials(self, username: str, password: str, new_username: str, new_password: str) -> dict:
        # Please be careful using this command - Can only be used after Login

        response = self._run_hnap_command(
            "SetStatusSecuritySettings",
            {
                "MotoStatusSecurityAction": "3",
                "MotoUsername": self._aes_encrypt128(username),
                "MotoPassword": self._aes_encrypt128(password),
                "MotoNewUsername": self._aes_encrypt128(new_username),
                "MotoNewPassword": self._aes_encrypt128(new_password),
                "MotoRepPassword": self._aes_encrypt128(new_password),
            },
        )
