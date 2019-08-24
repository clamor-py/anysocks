# -*- coding: utf-8 -*-

"""
anysocks
~~~~~~~~

WebSocket protocol implementation for anyio

:copyright: (c) 2019 Valentin B.
:license: MIT, see LICENSE for more details.
"""

from . import websocket
from .client import *
from .exceptions import *
from .meta import *

import logging

fmt = '[%(levelname)s] %(asctime)s - %(name)s:%(lineno)d - %(message)s'
logging.basicConfig(format=fmt, level=logging.INFO)
logging.getLogger(__name__).addHandler(logging.NullHandler())

try:
    import curio.meta

    curio.meta.safe_generator(open_connection.__wrapped__)
except ImportError:
    pass
