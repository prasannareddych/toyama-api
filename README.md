
# Toyama API Wrapper

`toyama` is a Python library that provides an API wrapper for controlling Toyama switches. It enables discovering, monitoring, and interacting with Toyama smart devices via Zeroconf and HTTP requests. This library is designed to be used as part of a custom integration for Home Assistant.

## Features

- **Gateway Discovery**: Automatically discovers the gateway using Zeroconf.
- **Device Interaction**: Send commands to control device states and request device statuses.
- **Callback Integration**: Allows handling device updates through user-defined callback functions.
- **Asynchronous**: Built with `asyncio` for efficient, non-blocking operations.

## Installation

To install the library, you can use pip:

```bash
pip install toyama
```

Or you can install it directly from the repository:

```bash
pip install git+https://github.com/prasannareddych/toyama-api.git
```