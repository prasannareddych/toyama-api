import asyncio
import json
import logging
import socket
from typing import Any, Callable, Dict, List, Optional

import aiohttp

from .device import Device

_LOGGER = logging.Logger(__name__)

SPEED_MAP = {
    0: 0,
    25: 35,
    50: 50,
    75: 55,
    100: 100,
}


class GatewayDevice(Device):
    """
    Represents a device controlled by the Gateway.

    Attributes:
        gateway_handler (Gateway): The gateway handler managing the device.
        callback (Optional[Callable[[int], None]]): A callback for state changes.
    """

    gateway_handler: "GatewayHandler"
    callback: Optional[Callable[[int], None]] = None
    state: int = 0

    def set_gateway_handler(self, gateway_handler: "GatewayHandler") -> None:
        """
        Associate the device with a Gateway instance.

        Args:
            gateway_handler (Gateway): The gateway client.
        """
        self.gateway_handler = gateway_handler

    def set_callback(self, callback: Callable[[int], None]) -> None:
        """
        Set a callback function for device state changes.

        Args:
            callback (Callable[[int], None]): The callback function.
        """
        self.callback = callback

    async def update_state(self, new_state: int) -> bool:
        """
        Update the device's state through the gateway.

        Args:
            new_state (int): The new state to set.

        Returns:
            bool: True if the state was updated successfully, otherwise False.
        """
        if self.state == new_state:
            return True
        return await self.gateway_handler.update_device_state(self, new_state)

    async def on(self) -> None:
        """
        Turn the device on. If the device is a fan, sets speed to maximum.
        """
        await self.update_state(100 if self.is_fan else 1)

    async def off(self) -> None:
        """
        Turn the device off.
        """
        await self.update_state(0)

    async def set_speed(self, value: int) -> None:
        """
        Set the speed of the device, if it's a fan.

        Args:
            value (int): The speed value to set.

        Raises:
            ValueError: If the value is not in SPEED_MAP.
        """
        if self.is_fan:
            if value not in SPEED_MAP.keys():
                raise ValueError(f"Invalid value: {value}")
            await self.update_state(SPEED_MAP[value])


class GatewayHandler:
    """GatewayHandler class"""

    gateway_ip: Optional[str] = None
    async_tasks: List[asyncio.Task[Any]] = []
    connected: bool = False
    singular_request = asyncio.Lock()

    def __init__(self, gateway_ip: str, callback_func: Optional[Callable[[str, int, int], None]] = None) -> None:
        """
        Initialize the Gateway instance.

        Args:
            gateway_id (str): Gateway IP address. 
            callback_func (Optional[Callable[[Dict[str, Any]], Any]]): 
                An optional callback function for handling device updates. 
                The function should accept parameters board_id, button_id, state.
        """
        self.gateway_ip = gateway_ip
        self.callback_func = callback_func

    async def ping_gateway(self, time_interval: float = 10):
        while True:
            try:
                if await self.request_all_devices_status():
                    self.connected = True
            except:
                self.connected = False
            await asyncio.sleep(time_interval)

    async def initialize(self, loop: asyncio.AbstractEventLoop) -> None:
        """
        Initializes the listen task

        Args:

            loop (asyncio.loop): Asyncronous loop for creating listen task
        """
        if self.callback_func:
            self.async_tasks.append(
                loop.create_task(
                    self.listen_device_updates()
                )
            )
            await self.request_all_devices_status()

    async def send_request(self, payload: Dict[str, Any]) -> bool:
        """
        Sends an HTTP POST request to the gateway.

        Args:
            payload (Dict[str, Any]): The payload to be sent.

        Return:
            bool: True if the request succeeds, otherwise False.

        Raises:
            RuntimeError: When gateway_ip is not initialized
            Exception: If the request doesn't return 'ok' status
        """
        if not self.gateway_ip:
            raise RuntimeError("Gateway IP not initialized.")
        async with self.singular_request:
            async with aiohttp.ClientSession() as session:
                try:
                    resp = await session.post(f"http://{self.gateway_ip}:8900/operate", json=payload)
                    result = await resp.text()
                    if result == "ok":
                        return True
                    else:
                        raise Exception(f"Request Error [{resp.status}] - {result}")
                except:
                    raise

    async def update_device_state(self, device: Device, new_state: int) -> bool:
        """
        Updates the state of a given device.
        Args:
            device (Device): The device to update.
            new_state (int): The new state to set.

        Returns:
            bool: True if the update succeeds, otherwise False.
        """

        payload: Dict[str, Any] = {
            "type": "swcmd",
            "data": [
                {
                    "addr": [device.board_id],
                    "nodedata": {
                        "cmdtype": "operate",
                        "subid": device.parsed_button_id,
                        "cmd": new_state
                    }
                }
            ]
        }
        try:
            _LOGGER.debug(f"updating {device.nice_name} -> {new_state}")
            return await self.send_request(payload)
        except Exception as e:
            raise RuntimeError(f"Failed to update the state for {device}: {e}")

    async def request_all_devices_status(self, timeout_seconds: float = 3) -> bool:
        """
        Requests the status of all devices.

        Args:
            timeout_seconds (float): Default 3

        Returns:
            bool: True if the request succeeds, otherwise False.

        Raises:
            TimeOutError when crosses the specified timeout_seconds
        """
        payload: Dict[str, Any] = {
            "type": "swcmd",
            "data": [
                {
                    "addr": [
                        "ffffffffffff"
                    ],
                    "nodedata": {
                        "cmdtype": "getstatus"
                    }
                }
            ]
        }
        try:
            timeout = aiohttp.ClientTimeout(total=timeout_seconds)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                resp = await session.post(f"http://{self.gateway_ip}:8900/operate", json=payload)
                result = await resp.text()
                if result == "ok":
                    return True
        except asyncio.TimeoutError:
            raise
        except Exception as e:
            _LOGGER.error(f"Request status error: {e}")
        return False

    async def listen_device_updates(self) -> None:
        """
        Listens for updates from devices and calls the callback function if provided.
        Rebinds the socket if the network changes.
        """
        def create_socket() -> socket.socket:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind(("0.0.0.0", 56000))
            sock.setblocking(False)
            return sock

        sock = create_socket()
        _LOGGER.info("Listening for device updates on port 56000...")

        try:
            while True:
                try:
                    loop = asyncio.get_event_loop()
                    data, _ = await asyncio.wait_for(loop.sock_recvfrom(sock, 1024), timeout=5)
                    update = json.loads(data.decode('utf-8'))
                    _LOGGER.debug(f"Device update: {update}")
                    self.handle_update(update)
                except asyncio.TimeoutError:
                    pass
                except OSError as e:
                    # Handle potential socket errors due to network changes
                    _LOGGER.warning(f"Socket error detected: {e}. Rebinding the socket.")
                    sock.close()
                    sock = create_socket()
                except Exception as e:
                    _LOGGER.error(f"Unexpected error: {e}")
                await asyncio.sleep(0.1)
        finally:
            sock.close()
            _LOGGER.info("Socket closed.")

    def handle_update(self, update: Dict[str, Any]) -> None:
        """
        Handles updates received from gateway and invokes the callback function if provided.

        Args:
            update (Dict[str, Any]): The update payload received from the device.

        The method processes updates of two types:
            - "single": Represents updates for a single button on the device. Extracts the `board_id`, 
              `button_id`, and `state` from the payload and calls the callback function.
            - "all": Represents updates for all buttons on the device. Iterates through the status list,
              extracting each `button_id` and `state`, and calls the callback function for each.

        Raises:
            KeyError: If required keys are missing in the update payload.
            Exception: For any unexpected errors during the update handling process.
        """
        try:
            board_id = update['addr']
            update_type = update['data']['stype']
            if update_type == 'single':
                button_id = update['data']['subid']
                state = update['data']['status']
                if self.callback_func:
                    try:
                        self.callback_func(board_id, button_id, state)
                    except Exception as e:
                        _LOGGER.error(f"Callback function failed for update type 'single': {e}")

            elif update_type == 'all':
                status: List[int] = update['data']['status']
                for button_id, state in enumerate(status, start=17):  # master button (16) will not have any updates
                    if self.callback_func:
                        try:
                            self.callback_func(board_id, button_id, state)
                        except Exception as e:
                            _LOGGER.error(f"Callback function failed for update type 'all': {e}")
        except KeyError:
            pass
        except Exception as e:
            _LOGGER.error(f"State update failed: {e}, update: {update}")
