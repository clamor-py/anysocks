# -*- coding: utf-8 -*-

from wsproto.frame_protocol import CloseReason

__all__ = (
    'AnySocksError',
    'HandshakeError',
    'ConnectionRejected',
    'ConnectionClosed',
)


class AnySocksError(Exception):
    """Base exception class for anysocks.

    Ideally speaking, this could be used to catch
    any exception thrown by this library.
    """
    pass


class HandshakeError(AnySocksError):
    """Exception thrown for any networking errors."""
    pass


class ConnectionRejected(HandshakeError):
    """Exception thrown when the server rejected the connection.

    Attributes
    ----------
    status_code : int
        A 3-digit HTTP status code.
    headers : tuple
        A tuple of tuples containing header key/value pairs.
    body : bytes
        An optional response body.
    """

    def __init__(self, status_code, headers, body):
        self.status_code = status_code
        self.headers = headers
        self.body = body

    def __repr__(self):
        return '<{0.__class__.__name__} status_code={0.status_code}>'.format(self)


class ConnectionClosed(AnySocksError):
    """Exception thrown for attempted I/O operations on a closed WebSocket."""

    def __init__(self, code: int, reason: str):
        self._code = code
        self._reason = reason

    def __repr__(self):
        return '<{0.__class__.__name__} name={0.name} code={0.code} reason={0.reason}>'.format(self)

    @property
    def code(self) -> int:
        """The numeric close code."""

        return self._code

    @property
    def reason(self) -> str:
        """The close reason."""

        return self._reason

    @property
    def name(self) -> str:
        """The type of close code."""

        try:
            name = CloseReason(self._code).name
        except ValueError:
            if 1000 <= self._code <= 2999:
                name = 'RFC_RESERVED'
            elif 3000 <= self._code <= 3999:
                name = 'IANA_RESERVED'
            elif 4000 <= self._code <= 4999:
                name = 'PRIVATE_RESERVED'
            else:
                name = 'INVALID_CODE'

        return name
