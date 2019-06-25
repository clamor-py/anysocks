# anysocks

This library implements [the WebSocket protocol](https://tools.ietf.org/html/rfc6455) based on the [Sans-IO library wsproto](https://github.com/python-hyper/wsproto).
I/O is handled by the [anyio project](https://github.com/agronholm/anyio) which makes this library compatible to asyncio, trio and curio.

[![Build Status](https://travis-ci.org/shitcord/anysocks.svg?branch=master)](https://travis-ci.org/shitcord/anysocks)
[![Maintainability](https://api.codeclimate.com/v1/badges/6f883d197ca32802380c/maintainability)](https://codeclimate.com/github/shitcord/anysocks/maintainability)
[![CodeFactor](https://www.codefactor.io/repository/github/shitcord/anysocks/badge)](https://www.codefactor.io/repository/github/shitcord/anysocks)
[![Test Coverage](https://api.codeclimate.com/v1/badges/6f883d197ca32802380c/test_coverage)](https://codeclimate.com/github/shitcord/anysocks/test_coverage)
[![Documentation Status](https://readthedocs.org/projects/anysocks/badge/?version=latest)](https://anysocks.readthedocs.io/en/latest/?badge=latest)

## Installation

This library requires Python 3.5+. You can install it directly from PyPI:

```sh
python3 -m pip install -U anysocks
```

If you want the cutting edge development version instead, install it directly from GitHub:

```sh
python3 -m pip install -U git+https://github.com/shitcord/anysocks@master#egg=anysocks
```

## Documentation

This README only provides a short overview, see the full documentation [here](https://anysocks.readthedocs.io/en/latest).

## Example

_Coming soon..._
