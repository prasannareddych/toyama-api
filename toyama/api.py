"""
Toyama API Client

A client to interact with the Toyama platform for managing gateways and devices.
"""

import logging
from typing import Any, Dict, List, Optional

import aiohttp

from .device import Device, DeviceType

_LOGGER = logging.Logger(__name__)

class APIError(Exception):
    """Base class for all API-related errors."""


class HTTPError(APIError):
    """Raised for generic HTTP errors."""


class AuthorizationError(HTTPError):
    """Raised for 401 Unauthorized errors."""


class ForbiddenError(HTTPError):
    """Raised for 403 Forbidden errors."""


class NotFoundError(HTTPError):
    """Raised for 404 Not Found errors."""


class RateLimitExceededError(HTTPError):
    """Raised for 429 Too Many Requests errors."""


class ServerError(HTTPError):
    """Raised for 500+ server errors."""


class Toyama:
    """Toyama Class"""

    BASE_URL = "https://api.toyamaworld.com"
    API_URL = f"{BASE_URL}/api/v1"

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        access_token: Optional[str] = None
    ) -> None:
        """
        Initialize the Toyama client.

        Args:
            username (str, optional): The username for authentication.
            password (str, optional): The password for authentication.
            access_token (str, optional): A valid access token for authentication.
        """
        if not ((username and password) or access_token):
            raise APIError("required 'username and password' or 'access_token'.")
        self.username = username
        self.password = password
        self.access_token = access_token
        self.headers = ({
            "User-Agent": "Dart/3.2 (dart:io)",
            'Authorization': f"Bearer {self.access_token}"
        })

    async def initialize(self) -> None:
        """
        Verify or refresh the access token.
        """

        if not self.access_token or not await self.is_token_valid():
            if self.username and self.password:
                await self.login()

    async def is_token_valid(self) -> bool:
        """
        Check if the access token is valid.

        Returns:
            bool: True if the token is valid, False otherwise.
        """

        try:
            url = f"{self.API_URL}/gateways/list"
            await self.make_request(
                url=url
            )
            return True
        except Exception as e:
            _LOGGER.warning(f"access_token is invalid: {e}")
            return False

    async def make_request(
        self,
        url: str,
        method: str = "GET",
        params: Optional[Dict[str, str]] = None,
        json: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        Make an HTTP request to the API.

        Args:
            url (str): The endpoint URL.
            method (str): The HTTP method (default is "GET").
            params (dict, optional): Query parameters for the request.
            json (dict, optional): JSON body for the request.

        Returns:
            Any: The response data.
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method, url, headers=self.headers, params=params, json=json
                ) as response:
                    _LOGGER.debug(f"[{response.status}]: {response.request_info.url}")
                    if response.status == 401:
                        raise AuthorizationError("Unauthorized access. Check your token.")
                    elif response.status == 403:
                        raise ForbiddenError(f"Forbidden access to {url}.")
                    elif response.status == 404:
                        raise NotFoundError(f"Resource not found: {url}.")
                    elif response.status == 429:
                        retry_after = response.headers.get("Retry-After", "Unknown")
                        raise RateLimitExceededError(
                            f"Rate limit exceeded. Retry after {retry_after} seconds."
                        )
                    elif 500 <= response.status < 600:
                        raise ServerError(
                            f"Server error ({response.status}) while accessing {url}."
                        )
                    elif response.status >= 400:
                        raise HTTPError(
                            f"HTTP error {response.status}: {await response.text()}"
                        )
                    return await response.json(content_type=None)

        except aiohttp.ClientError as e:
            raise APIError(f"Network error while accessing {url}: {e}")

    async def login(self) -> None:
        """
        Authenticate using username and password.
        """

        login_url = f"{self.BASE_URL}/oauth/token"
        boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
        multipart_data = (
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="email"\r\n\r\n{
                self.username}\r\n'
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="password"\r\n\r\n{
                self.password}\r\n'
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="grant_type"\r\n\r\npassword\r\n'
            f'--{boundary}--\r\n'
        )

        headers = {
            "User-Agent": "Dart/3.2 (dart:io)",
            "Accept-Encoding": "gzip",
            "Content-Type": f'multipart/form-data; boundary={boundary}',
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                login_url, headers=headers,
                data=multipart_data
            ) as response:
                if response.status == 200:
                    response_data = await response.json()
                    self.access_token = response_data.get("access_token")
                    self.headers.update({
                        "Authorization": f"Bearer {self.access_token}"
                    })
                else:
                    raise AuthorizationError(
                        "Error connecting to api. Invalid username or password."
                    )

    async def fetch_gateways(self) -> List[Dict[str, Any]]:
        """
        Retrieve the list of gateways.

        Returns:
            list[dict]: A list of gateway details.
        """
        gateways: List[Dict[str, str]] = []

        url = f"{self.API_URL}/gateways/list"
        try:
            data = await self.make_request(url)
            for gateway in data:
                gateways.append({
                    "id": gateway["id"],
                    "serial": gateway["serial_number"],
                })
            return gateways
        except Exception as e:
            _LOGGER.error(f"fetch_gateways: {e}")
            raise

    async def fetch_gateway_info(self, serial_id: str) -> List[Any]:
        """
        Retrieve information about a specific gateway.

        Args:
            serial_id (str): The serial ID of the gateway.

        Returns:
            list: Information about the gateway.
        """

        url = f"{self.API_URL}/gateways/single"
        try:
            json_data = {
                "gateway": {
                    "serial_number": serial_id
                }
            }
            return await self.make_request(url=url, method="POST", json=json_data)
        except Exception as e:
            _LOGGER.error(f"fetch_gateway_info: {e}")
            raise

    async def fetch_device_list(self) -> List[str]:
        """
        Retrieve a list of devices.

        Returns:
            list[str]: A list of device details.
        """
        try:
            gateways = await self.fetch_gateways()
            my_devices: List[Any] = []
            for gateway in gateways:
                data = await self.fetch_gateway_info(gateway['serial'])
                if len(data) > 0:
                    my_devices.extend(self._parse_device_list(data[0]))
            return my_devices
        except Exception as e:
            raise APIError(f"Failed to fetch device info: {e}")

    def _parse_device_list(self, data: Dict[str, Any]) -> List[Any]:
        """
        Parse device details from API data.

        Args:
            data (dict): Raw data from the API.

        Returns:
            list: Parsed device details.
        """

        device_list: List[Any] = []
        zones = data.get("zones", [])
        for zone in zones:
            zone_id = zone.get("id")
            zone_name = zone.get("name")
            rooms = zone.get("rooms", [])
            for room in rooms:
                room_id = room.get('id')
                room_name = room.get('name')
                boards = room.get("legacy_devices", [])
                for board in boards:
                    board_id = board.get("mac_id")
                    board_name = board.get("name")
                    devices = board.get("legacy_device_buttons", [])
                    for device in devices:
                        id = device.get('id')
                        button_id = device.get("button_number")
                        name = device.get('name')
                        type = device.get('variant')
                        state = device.get("percentage")
                        device_list.append([
                            id, button_id, name, type, state,
                            zone_name, zone_id,
                            room_name, room_id,
                            board_name, board_id
                        ])
        return sorted(device_list)

    async def get_devices(self) -> List[Device]:
        """
        Retrieve all devices associated with gateways.

        Returns:
            list[Device]: A list of Device objects.
        """

        mydevices: List[Device] = []
        try:
            gateways = await self.fetch_gateways()
            for gateway in gateways:
                data = await self.fetch_gateway_info(gateway['serial'])
                if len(data) > 0:
                    devices = self._parse_device_list(data[0])
                    for device in devices:
                        mydevices.append(
                            Device(
                                id=device[0],
                                button_id=int(device[1]),
                                name=device[2],
                                type=DeviceType(device[3]),
                                state=device[4],
                                gateway=gateway["serial"],
                                gateway_id=gateway["id"],
                                zone=device[5],
                                zone_id=device[6],
                                room=device[7],
                                room_id=device[8],
                                board=device[9],
                                board_id=device[10]
                            )
                        )
            return mydevices
        except Exception as e:
            raise APIError(f"Failed to get device list: {e}")

    async def rename_device(self, device: Device, new_name: str) -> None:
        """
        Rename a specified device.

        Args:
            device (Device): The device to rename.
            new_name (str): The new name for the device.
        """

        url = f"{self.API_URL}/legacy_devices/rename_button"
        json_body: Dict[str, Any] = {"legacy_device": {"gateway_id": device.gateway_id, "new_name": new_name, "id": device.id}}
        try:
            if device.is_master:
                raise APIError("Cannot rename master.")
            await self.make_request(
                url=url,
                method="POST",
                json=json_body
            )
            _LOGGER.info("Rename success.")
        except Exception as e:
            _LOGGER.error(f"Failed to update the device name: {e}")
