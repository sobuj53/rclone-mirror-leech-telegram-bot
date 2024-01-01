import traceback
from base64 import b64encode, b64decode
from typing import Any
import requests
from requests import RequestException, JSONDecodeError
from bot.helper.ext_utils.exceptions import ProviderException

# Source: https://github.com/mhdzumair/MediaFusion/blob/main/streaming_providers/realdebrid/client.py
# Modified to add func add_torrent_file, get_user_downloads_list


class RealDebrid:
    BASE_URL = "https://api.real-debrid.com/rest/1.0"
    OAUTH_URL = "https://api.real-debrid.com/oauth/v2"
    OPENSOURCE_CLIENT_ID = "X245A4XAIBGVM"

    def __init__(self, encoded_token=None):
        self.encoded_token = encoded_token
        self.headers = {}
        self.initialize_headers()

    def __del__(self):
        if self.encoded_token:
            self.disable_access_token()

    def _make_request(
        self,
        method: str,
        url: str,
        data=None,
        file=None,
        params=None,
        is_return_none=False,
        is_expected_to_fail=False,
    ) -> dict:
        if method == "GET":
            response = requests.get(url, params=params, headers=self.headers)
        elif method == "POST":
            response = requests.post(url, data=data, headers=self.headers)
        elif method == "DELETE":
            response = requests.delete(url, headers=self.headers)
        elif method == "PUT":
            response = requests.put(url, data=file, headers=self.headers)
        else:
            raise ValueError(f"Unsupported method: {method}")

        try:
            response.raise_for_status()
        except RequestException as error:
            if is_expected_to_fail:
                pass
            elif error.response.status_code == 401:
                raise ProviderException("Invalid token")
            elif (
                error.response.status_code == 403
                and response.json().get("error_code") == 9
            ):
                raise ProviderException(
                    "Real-Debrid Permission denied for free account"
                )
            else:
                formatted_traceback = "".join(traceback.format_exception(error))
                raise ProviderException(
                    f"status code: {error.response.status_code}, data: {error.response.content}, trace log:\n {formatted_traceback}"
                )

        if is_return_none:
            return {}
        try:
            return response.json()
        except JSONDecodeError as error:
            formatted_traceback = "".join(traceback.format_exception(error))
            raise ProviderException(
                f"Failed to parse response. content: {response.text}, trace log:\n {formatted_traceback}"
            )

    def initialize_headers(self):
        if self.encoded_token:
            token_data = self.decode_token_str(self.encoded_token)
            access_token_data = self.get_token(
                token_data["client_id"], token_data["client_secret"], token_data["code"]
            )
            self.headers = {
                "Authorization": f"Bearer {access_token_data['access_token']}"
            }

    @staticmethod
    def encode_token_data(client_id: str, client_secret: str, code: str):
        token = f"{client_id}:{client_secret}:{code}"
        return b64encode(str(token).encode()).decode()

    @staticmethod
    def decode_token_str(token: str) -> dict[str, str]:
        try:
            client_id, client_secret, code = b64decode(token).decode().split(":")
        except ValueError:
            raise ProviderException("Invalid token")
        return {"client_id": client_id, "client_secret": client_secret, "code": code}

    def get_device_code(self):
        return self._make_request(
            "GET",
            f"{self.OAUTH_URL}/device/code",
            params={"client_id": self.OPENSOURCE_CLIENT_ID, "new_credentials": "yes"},
        )

    def get_token(self, client_id, client_secret, device_code):
        return self._make_request(
            "POST",
            f"{self.OAUTH_URL}/token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": device_code,
                "grant_type": "http://oauth.net/grant_type/device/1.0",
            },
        )

    def authorize(self, device_code):
        response_data = self._make_request(
            "GET",
            f"{self.OAUTH_URL}/device/credentials",
            params={"client_id": self.OPENSOURCE_CLIENT_ID, "code": device_code},
            is_expected_to_fail=True,
        )

        if "client_secret" not in response_data:
            return response_data

        token_data = self.get_token(
            response_data["client_id"], response_data["client_secret"], device_code
        )

        if "access_token" in token_data:
            token = self.encode_token_data(
                response_data["client_id"],
                response_data["client_secret"],
                token_data["refresh_token"],
            )
            return {"token": token}
        else:
            return token_data

    def get_hosts(self):
        return self._make_request("GET", f"{self.BASE_URL}/hosts")

    def add_magent_link(self, magnet_link):
        return self._make_request(
            "POST", f"{self.BASE_URL}/torrents/addMagnet", data={"magnet": magnet_link}
        )

    def add_torrent_file(self, file):
        return self._make_request(
            "PUT", f"{self.BASE_URL}/torrents/addTorrent", file=file
        )

    def get_user_torrent_list(self, page, limit):
        return self._make_request(
            "GET", f"{self.BASE_URL}/torrents", params={"page": page, "limit": limit}
        )

    def get_user_downloads_list(self, page, limit):
        return self._make_request(
            "GET", f"{self.BASE_URL}/downloads", params={"page": page, "limit": limit}
        )

    def get_user(self):
        return self._make_request("GET", f"{self.BASE_URL}/user")

    def get_torrent_info(self, torrent_id):
        return self._make_request("GET", f"{self.BASE_URL}/torrents/info/{torrent_id}")

    def get_torrent_instant_availability(self, torrent_hash):
        return self._make_request(
            "GET", f"{self.BASE_URL}/torrents/instantAvailability/{torrent_hash}"
        )

    def disable_access_token(self):
        return self._make_request(
            "GET", f"{self.BASE_URL}/disable_access_token", is_return_none=True
        )

    def select_files(self, torrent_id, file_ids="all"):
        return self._make_request(
            "POST",
            f"{self.BASE_URL}/torrents/selectFiles/{torrent_id}",
            data={"files": file_ids},
            is_return_none=True,
        )

    def get_available_torrent(self, info_hash) -> dict[str, Any] | None:
        available_torrents = self.get_user_torrent_list()
        for torrent in available_torrents:
            if torrent["hash"] == info_hash:
                return torrent

    def create_download_link(self, link):
        response = self._make_request(
            "POST",
            f"{self.BASE_URL}/unrestrict/link",
            data={"link": link},
            is_expected_to_fail=True,
        )
        if "download" in response:
            return response

        if "error_code" in response:
            if response["error_code"] == 23:
                raise ProviderException(
                    "Exceed remote traffic limit"
                )
        raise ProviderException(
            f"Failed to create download link. response: {response}"
        )

    def delete_torrent(self, torrent_id):
        return self._make_request(
            "DELETE",
            f"{self.BASE_URL}/torrents/delete/{torrent_id}",
            is_return_none=True,
        )
