.. currentmodule:: anysocks

Limitations
===========

``anysocks`` currently has a few limitations users have to deal with.

- There may be more than one connection to a given IP address in a ``CONNECTING`` state.

- The client doesn't support connecting through a proxy.

- You cannot fragment outgoing messages. They are always sent in a single frame.

- Currently no support for WebSocket servers.

- ``anysocks`` limits how many bytes can be received (4kB).
  One would have to patch the ``RECEIVE_BYTES`` constant in ``anysocks.websocket``.
