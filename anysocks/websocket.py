# -*- coding: utf-8 -*-

import itertools
import logging
import random
import struct
from collections import OrderedDict
from typing import Optional, Union

import anyio.abc
from anyio.exceptions import ClosedResourceError
from wsproto import WSConnection
from wsproto.connection import ConnectionState
from wsproto.events import (
    AcceptConnection,
    BytesMessage,
    CloseConnection,
    Event,
    Message,
    Ping,
    Pong,
    RejectConnection,
    RejectData,
    Request,
    TextMessage
)
from wsproto.frame_protocol import CloseReason
from wsproto.utilities import RemoteProtocolError

from .exceptions import *

__all__ = (
    'CON_TIMEOUT',
    'MESSAGE_QUEUE_SIZE',
    'MAX_MESSAGE_SIZE',
    'RECEIVE_BYTES',
    'WebSocketConnection',
)

logger = logging.getLogger(__name__)

CON_TIMEOUT = 60.0
MESSAGE_QUEUE_SIZE = 1
MAX_MESSAGE_SIZE = 2 ** 20  # 1 Mb
RECEIVE_BYTES = 4 * 2 ** 10  # 4 Kb

# To prevent a race condition where WebSocketConnection.get_message
# would try to poll data from an empty _event_queue when the
# connection is already closed, we inject this into the queue and
# use the isinstance check to determine whether the connection is
# closed or not, because _event_queue only holds str or byte types
# for actual data polled from the WebSocket.
_CLOSE_MESSAGE = object()


class WebSocketConnection:
    """A wrapper around WebSocket connections.

    .. note::

        This class has some tricky internal logic.
        That's why it is strongly discouraged to directly
        instantiate objects.
        Use the convenience functions, such as
        :func:`~anysocks.client.open_connection`, instead.

    .. warning::

        This only supports client connections at the moment!

    Parameters
    ----------
    stream : :class:`SocketStream<anyio:anyio.abc.SocketStream>`
        The socket stream.
    wsproto : :class:`WSConnection<wsproto:wsproto.WSConnection>`
        The connection type abstraction. This should always be
        ``WSConnection(ConnectionType.CLIENT)``.
    host : str
        The hostname to connect to.
    path : str
        The URL path for this connection.
    subprotocols : Optional[list]
        An optional list of strings that represent the subprotocols to use.
    headers: Optional[list]
        A list of tuples containing optional HTTP header key/value pairs to send
        with the handshake request. Please note that headers directly
        used by the protocol, e.g. ``Sec-WebSocket-Accept`` will be overwritten.
    message_queue_size : int
        The total amount of messages that will be stored in the internal buffer.
        Defaults to 1.
    max_message_size : int
        The maximum message size as measured by ``len(message)``. If a received
        message exceeds this limit, the connections gets terminated with status code
        1009 - Message Too Big. Defaults to 1 Mb (2 ** 20).

    Attributes
    ----------
    id : int
        A unique ID to identify every active WebSocket connection.
    message_queue_size : int
        The total amount of messages that will be stored in the internal buffer.
    max_message_size : int
        The maximum message size as measured by ``len(message)``. If a received
        message exceeds this limit, the connection gets terminated.
    """

    CONNECTION_ID = itertools.count()

    def __init__(self,
                 stream: anyio.abc.SocketStream,
                 wsproto: WSConnection,
                 *,
                 host: str = None,
                 path: str = None,
                 subprotocols: Optional[list] = None,
                 headers: Optional[list] = None,
                 message_queue_size: int = MESSAGE_QUEUE_SIZE,
                 max_message_size: int = MAX_MESSAGE_SIZE):
        self.id = next(self.__class__.CONNECTION_ID)
        self._closed = False
        self._reader_running = True

        self._close_code = None
        self._close_reason = None

        self._stream = stream
        self._wsproto = wsproto
        self._host = host
        self._path = path
        self._subprotocols = subprotocols
        self._connection_subprotocol = None
        self._handshake_headers = None
        self._headers = headers
        self.message_queue_size = message_queue_size
        self.max_message_size = max_message_size

        self._reject_status = None
        self._reject_headers = None
        self._reject_body = b''

        self._stream_lock = anyio.create_lock()
        self._message_size = 0
        self._message_parts = []
        self._event_queue = anyio.create_queue(self.message_queue_size)
        self._pings = OrderedDict()
        self._open_handshake = anyio.create_event()
        self._close_handshake = anyio.create_event()

    def __str__(self):
        return '{}-{}'.format(
            'client' if self._wsproto.client else 'server',
            self.id
        )

    @property
    def closed(self) -> bool:
        """Whether the connection is closed or not."""

        return self._closed

    @property
    def close_code(self) -> Optional[CloseReason]:
        """Returns the close code of the connection.

        ``None`` if the connection isn't closed.

        Returns
        -------
        Optional[:class:`CloseReason<wsproto:wsproto.frame_protocol.CloseReason>`]
            The close code.
        """

        return self._close_code

    @property
    def close_reason(self) -> Optional[str]:
        """Returns the close reason of the connection.

        ``None`` if the connection isn't closed.
        """

        return self._close_reason

    @property
    def is_client(self) -> bool:
        """Whether this instance is a client WebSocket or not."""

        is_client = self._wsproto.client
        if not is_client:
            raise RuntimeError('Server WebSockets are unsupported')

        return is_client

    @property
    def state(self) -> ConnectionState:
        """The current connection state.

        Returns
        -------
        :class:`ConnectionState<wsproto:wsproto.connection.ConnectionState>`
            The connection state.
        """

        return self._wsproto.state

    @property
    def host(self) -> str:
        """The host this instance is connected to."""

        return self._host

    @property
    def path(self) -> str:
        """The requested URL path."""

        return self._path

    @property
    def subprotocol(self) -> Optional[str]:
        """The underlying subprotocol of the connection."""

        return self._connection_subprotocol

    async def get_message(self) -> Union[bytes, str]:
        """Polls for the next message and returns its data."""

        if self._closed:
            raise ConnectionClosed(self._close_code, self._close_reason)

        message = await self._event_queue.get()
        if self._closed:
            # In case of a connection closure, the polled message
            # is just the _CLOSE_MESSAGE object.
            raise ConnectionClosed(self._close_code, self._close_reason)

        return message

    async def ping(self, payload: bytes = None):
        """Sends a WebSocket ping frame to the peer and waits for a pong.

        As each ping must be unique, the client internally keeps
        track of them.

        .. note::

            A server is allowed to respond with a single pong to
            multiple pings. Therefore, a pong will wake up its
            corresponding ping as well as all previous in-flight
            pings.

        Parameters
        ----------
        payload : Optional[bytes]
            The payload to send. If ``None``, a random 32-bit payload
            will be generated.

        Raises
        ------
        :exc:`anysocks.exceptions.ConnectionClosed`
            If the connection is already closed.
        :exc:`ValueError`
            If ``payload`` is identical to another in-flight ping.
        """

        if self._closed:
            raise ConnectionClosed(self._close_code, self._close_reason)

        if payload in self._pings:
            raise ValueError('Payload value {} is already in flight'.format(payload))

        if payload is None:
            payload = struct.pack('!I', random.getrandbits(32))

        event = anyio.Event()
        self._pings[payload] = event
        await self._send(Ping(payload=payload))
        await event.wait()

    async def send_message(self, message: Union[bytes, str]):
        """Sends a WebSocket message to the peer.

        Parameters
        ----------
        message : Union[bytes, str]
            The message to send.

        Raises
        ------
        :exc:`anysocks.exceptions.ConnectionClosed`
            If the connection is already closed.
        :exc:`ValueError`
            If the type of ``message`` isn't ``str`` or ``bytes``.
        """

        if self._closed:
            raise ConnectionClosed(self._close_code, self._close_reason)

        if isinstance(message, str):
            event = TextMessage(data=message)
        elif isinstance(message, bytes):
            event = BytesMessage(data=message)
        else:
            raise ValueError('Message must be bytes or string')

        await self._send(event)

    async def close(self, code: int = 1000, reason: str = ''):
        """Terminates the open WebSocket connection.

        This sends a closing frame and suspends until the connection is closed.
        After calling this method, any further I/O on this WebSocket, e.g.
        :meth:`~WebSocketConnection.get_message` will raise
        :exc:`~anysocks.exceptions.ConnectionClosed`.

        Parameters
        ----------
        code : int
            A 4-digit WebSocket close code.
        reason : str
            An optional string indicating why the connection was closed.
        """

        logger.info('Closing connection to %s...', self.host)

        if self._closed:
            return

        self._closed = True

        await self._close_websocket(code, reason)

        try:
            if self.state is ConnectionState.OPEN:
                await self._send(CloseConnection(code=code, reason=reason))
            elif self.state in (ConnectionState.CONNECTING, ConnectionState.REJECTING):
                await self._close_handshake.set()

            await self._close_handshake.wait()
        except ConnectionClosed:
            # If _send() raised ConnectionClosed, we can opt out.
            pass
        finally:
            await self._close_stream()

    async def _abort_websocket(self):
        close_code = CloseReason.ABNORMAL_CLOSURE
        if self.state is ConnectionState.OPEN:
            self._wsproto.send(CloseConnection(code=close_code.value))

        if self._close_code is None:
            await self._close_websocket(close_code)

        self._reader_running = False
        await self._close_handshake.set()

    async def _close_stream(self):
        self._reader_running = False
        await self._stream.close()

    async def _close_websocket(self, code: Union[CloseReason, int], reason: str = ''):
        if isinstance(code, int):
            code = CloseReason(code)

        await self._event_queue.put(_CLOSE_MESSAGE)

        self._close_code = code
        self._close_reason = reason
        logger.debug('%s closed by %r', self, ConnectionClosed(code, reason))

    async def _send(self, event: Event):
        data = self._wsproto.send(event)
        async with self._stream_lock:
            logger.debug('%s sending %d bytes', self, len(data))
            try:
                await self._stream.send_all(data)
            except ClosedResourceError:
                await self._abort_websocket()
                raise ConnectionClosed(self._close_code, self._close_reason) from None

    async def _handle_accept_connection_event(self, event: AcceptConnection):
        self._connection_subprotocol = event.subprotocol
        self._handshake_headers = tuple(event.extra_headers)
        await self._open_handshake.set()

    async def _handle_reject_connection_event(self, event: RejectConnection):
        self._reject_status = event.status_code
        self._reject_headers = tuple(event.headers)
        if not event.has_body:
            raise ConnectionRejected(self._reject_status, self._reject_headers, self._reject_body)

    async def _handle_reject_data_event(self, event: RejectData):
        self._reject_body += event.data
        if event.body_finished:
            raise ConnectionRejected(self._reject_status, self._reject_headers, self._reject_body)

    async def _handle_close_connection_event(self, event: CloseConnection):
        await anyio.sleep(0)
        if self.state is ConnectionState.REMOTE_CLOSING:
            await self._send(event.response())
        await self._close_handshake.set()

    async def _handle_message_event(self, event: Message):
        self._message_size += len(event.data)
        self._message_parts.append(event.data)

        if self._message_size > self.max_message_size:
            error = 'Exceeded maximum message size: {} bytes'.format(self.max_message_size)

            self._message_size = 0
            self._message_parts = []

            self._close_code = 1009
            self._close_reason = error

            await self._send(CloseConnection(code=1009, reason=error))
            self._reader_running = False

        elif event.message_finished:
            message = (b'' if isinstance(event, BytesMessage) else '').join(self._message_parts)

            self._message_size = 0
            self._message_parts = []

            await self._event_queue.put(message)

    async def _handle_ping_event(self, event: Ping):
        logger.debug('%s pings with %r', self, event.payload)
        await self._send(event.response())

    async def _handle_pong_event(self, event: Pong):
        payload = bytes(event.payload)
        try:
            self._pings[payload]
        except KeyError:
            # pong doesn't match any pings. Nothing we can do with it.
            return

        while self._pings:
            key, event = self._pings.popitem(False)
            skipped = ' [skipped] ' if payload != key else ' '
            logger.debug('%s received pong %s%r', self, skipped, key)
            event.set()
            if payload == key:
                break

    async def _do_handshake(self):
        try:
            handshake = Request(
                host=self.host,
                target=self.path,
                subprotocols=self._subprotocols or [],
                extra_headers=self._headers or []
            )
            await self._send(handshake)
        except ConnectionClosed:
            self._reader_running = False

    async def _get_network_data(self):
        # Get network data.
        try:
            data = await self._stream.receive_some(RECEIVE_BYTES)
        except ClosedResourceError:
            await self._abort_websocket()
            raise AnySocksError()

        if len(data) == 0:
            logger.debug('%s received zero bytes, connection closed', self)
            # If TCP closed before WebSocket, it is abnormal closure.
            if self.state is not ConnectionState.CLOSED:
                await self._abort_websocket()
            raise AnySocksError()

        else:
            logger.debug('%s received %d bytes', self, len(data))
            if self.state is not ConnectionState.CLOSED:
                try:
                    self._wsproto.receive_data(data)
                except RemoteProtocolError as exception:
                    logger.debug('%s remote protocol error: %s', self, exception)
                    if exception.event_hint:
                        await self._send(exception.event_hint)

                    await self._close_stream()

    async def _reader_task(self):
        handlers = {
            AcceptConnection: self._handle_accept_connection_event,
            BytesMessage: self._handle_message_event,
            CloseConnection: self._handle_close_connection_event,
            Ping: self._handle_ping_event,
            Pong: self._handle_pong_event,
            RejectConnection: self._handle_reject_connection_event,
            RejectData: self._handle_reject_data_event,
            # Request: lambda event: None,  # We won't handle server-side events.
            TextMessage: self._handle_message_event,
        }

        # We need to initiate the opening handshake.
        await self._do_handshake()

        while self._reader_running:
            for event in self._wsproto.events():
                event_type = type(event)
                try:
                    handler = handlers[event_type]
                    logger.debug('%s received event: %s', self, event_type)
                    await handler(event)
                except KeyError:
                    logger.warning('%s received unknown event type: "%s"', self, event_type)
                except ConnectionClosed:
                    self._reader_running = False
                    break

            try:
                await self._get_network_data()
            except AnySocksError:
                break

        logger.debug('Reader task of %s finished', self)
