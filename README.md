# anysocks

This library implements [the WebSocket protocol](https://tools.ietf.org/html/rfc6455) based on the [Sans-IO library wsproto](https://github.com/python-hyper/wsproto).
I/O is handled by the [anyio project](https://github.com/agronholm/anyio) which makes this library compatible to asyncio, trio and curio.

[![Build Status](https://img.shields.io/endpoint.svg?url=https%3A%2F%2Factions-badge.atrox.dev%2Fclamor-py%2Fanysocks%2Fbadge%3Fref%3Dmaster&style=flat)](https://actions-badge.atrox.dev/clamor-py/anysocks/goto?ref=master)
[![Maintainability](https://api.codeclimate.com/v1/badges/9346c58f1ff2ab188c9a/maintainability)](https://codeclimate.com/github/clamor-py/anysocks/maintainability)
[![CodeFactor](https://www.codefactor.io/repository/github/clamor-py/anysocks/badge)](https://www.codefactor.io/repository/github/clamor-py/anysocks)
[![Documentation Status](https://readthedocs.org/projects/anysocks/badge/?version=latest)](https://anysocks.readthedocs.io/en/latest/?badge=latest)
[![PyPI version](https://badge.fury.io/py/anysocks.svg)](https://badge.fury.io/py/anysocks)

## Installation

This library requires Python 3.5+. You can install it directly from PyPI:

```sh
python3 -m pip install -U anysocks
```

If you want the cutting edge development version instead, install it directly from GitHub:

```sh
python3 -m pip install -U git+https://github.com/clamor-py/anysocks@master#egg=anysocks
```

## Documentation

This README only provides a short overview, see the full documentation [here](https://anysocks.readthedocs.io/en/latest).

## Example

```python
import anyio
from anysocks import open_connection


async def main():
    async with open_connection('wss://echo.websocket.org') as con:
        print('Connection established!')

        # First, let's send some text to the server.
        text = input('What to send? ')
        await con.send_message(text)

        # Now, we receive and verify the server's response.
        message = await con.get_message()
        assert message == text, "Received {}, expected {}".format(message, text)

    print('Connection closed with code {}', con.close_code.value)

anyio.run(main)
```
