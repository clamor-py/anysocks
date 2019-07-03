# -*- coding: utf-8 -*-

import itertools
import logging
import random
import ssl
import struct
from collections import OrderedDict
from typing import Optional, Union

import anyio.abc
from anyio.exceptions import ClosedResourceError
from async_generator import asynccontextmanager
from wsproto import ConnectionType, WSConnection
from wsproto.connection import ConnectionState
from wsproto.events import (
    AcceptConnection,
    BytesMessage,
    CloseConnection,
    Event,
    Ping,
    Pong,
    RejectConnection,
    RejectData,
    Request,
    TextMessage
)
from wsproto.frame_protocol import CloseReason
from wsproto.utilities import RemoteProtocolError
from yarl import URL

__all__ = (
    'WebSocketConnection',
    'open_websocket',
    'create_websocket',
)

logger = logging.getLogger(__name__)

CON_TIMEOUT = 60.0
MESSAGE_QUEUE_SIZE = 1
MAX_MESSAGE_SIZE = 2 ** 20  # 1 Mb
RECEIVE_BYTES = 4 * 2 ** 10  # 4 Kb


class AnysocksError(Exception):
    """Base exception class for anysocks.

    Ideally speaking, this could be used to catch
    any exception thrown by this library.
    """
    pass


class HandshakeError(AnysocksError):
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


class ConnectionClosed(AnysocksError):
    """Exception thrown for attempted I/O operations on a closed WebSocket."""

    def __init__(self, code: int, reason: str):
        self._code = code
        self._reason = reason

        try:
            self._name = CloseReason(code).name
        except ValueError:
            if 1000 <= code <= 2999:
                self._name = 'RFC_RESERVED'
            elif 3000 <= code <= 3999:
                self._name = 'IANA_RESERVED'
            elif 4000 <= code <= 4999:
                self._name = 'PRIVATE_RESERVED'
            else:
                self._name = 'INVALID_CODE'

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

        return self._name


class WebSocketConnection:
    """A wrapper around WebSocket connections.

    .. warning::

        This class has some tricky internal logic.
        That's why it is strongly discouraged to directly
        instantiate objects.
        Use the convenience functions, such as :func:`open_websocket`,
        instead.

    .. warning::

        This only supports client connections!

    Parameters
    ----------
    stream : :class:`SocketStream<anyio:anyio.abc.SocketStream>`
        The socket stream.
    wsproto : :class:`wsproto.WSConnection`
        The connection type abstraction. This should always be
        ``wsproto.WSConnection(wsproto.ConnectionType.CLIENT)``.
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

        self._stream_lock = anyio.Lock()
        self._message_size = 0
        self._message_parts = []
        self._event_queue = anyio.Queue()
        self._pings = OrderedDict()
        self._open_handshake = anyio.Event()
        self._close_handshake = anyio.Event()

    def __str__(self):
        return '{0._wsproto.client}-{0.id}'.format(self)

    @property
    def closed(self) -> bool:
        """Whether the connection is closed or not."""

        return self._closed

    @property
    def is_client(self) -> bool:
        """Whether this instance is a client WebSocket or not."""

        is_client = self._wsproto.client
        if not is_client:
            raise RuntimeError('Server WebSockets are unsupported')

        return is_client

    @property
    def state(self) -> ConnectionState:
        """The current connection state."""

        return self._wsproto.state

    @property
    def host(self) -> str:
        """The host this instance is connected to."""

        return self._host

    @property
    def path(self) -> str:
        """The requested URL path."""

        return self._path

    async def poll_event(self) -> Event:
        """Polls for the next event and returns the received data."""

        if self._closed:
            raise ConnectionClosed(self._close_code, self._close_reason)

        event = await self._event_queue.get()
        if event is CloseConnection:
            raise ConnectionClosed(event.code, event.reason)

        return event

    async def get_message(self) -> Union[bytes, str]:
        """Polls for the next message and returns its data."""

        event = await self.poll_event()
        if isinstance(event, TextMessage):
            return event.data

        elif isinstance(event, BytesMessage):
            return bytes(event.data)

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
        :exc:`ConnectionClosed`
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
        :exc:`ConnectionClosed`
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
        :exc:`ConnectionClosed`.

        Parameters
        ----------
        code : int
            A 4-digit WebSocket close code.
        reason : str
            An optional string indicating why the connection was closed.
        """

        if self._closed:
            return

        self._closed = True

        self._close_code = code
        self._close_reason = reason

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

    async def _close_websocket(self, code: int, reason: str = None):
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

    async def _handle_accept_connection_event(self, event: Event):
        self._connection_subprotocol = event.subprotocol
        self._handshake_headers = tuple(event.extra_headers)
        await self._open_handshake.set()

    async def _handle_reject_connection_event(self, event: Event):
        self._reject_status = event.status_code
        self._reject_headers = tuple(event.headers)
        if not event.has_body:
            raise ConnectionRejected(self._reject_status, self._reject_headers, self._reject_body)

    async def _handle_reject_data_event(self, event: Event):
        self._reject_body += event.data
        if event.body_finished:
            raise ConnectionRejected(self._reject_status, self._reject_headers, self._reject_body)

    async def _handle_close_connection_event(self, event: Event):
        await anyio.sleep(0)
        if self.state is ConnectionState.REMOTE_CLOSING:
            await self._send(event.response())
        await self._close_websocket(event.code, event.reason or None)
        await self._close_handshake.set()

    async def _handle_message_event(self, event: Event):
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

    async def _handle_ping_event(self, event: Event):
        logger.debug('%s pings with %r', self, event.payload)
        await self._send(event.response())

    async def _handle_pong_event(self, event: Event):
        payload = bytes(event.payload)
        try:
            self._pings[payload]
        except KeyError:
            # pong doesn't match any pings. Nothing we can do with it.
            return

        while self._pings:
            key, event = self._pings.popitem(0)
            skipped = ' [skipped] ' if payload != key else ' '
            logger.debug('%s received pong %s%r', self, skipped, key)
            event.set()
            if payload == key:
                break

    async def _do_handshake(self):
        try:
            handshake = Request(
                host=self._host,
                target=self._path,
                subprotocols=self._subprotocols,
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
            raise AnysocksError()

        if len(data) == 0:
            logger.debug('%s received zero bytes, connection closed', self)
            # If TCP closed before WebSocket, it is abnormal closure.
            if self.state is not ConnectionState.CLOSED:
                await self._abort_websocket()
                raise AnysocksError()

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
            except AnysocksError:
                break

        logger.debug('Reader task of %s finished', self)


@asynccontextmanager
async def open_websocket(url: str,
                         *,
                         use_ssl: Union[bool, ssl.SSLContext],
                         subprotocols: Optional[list] = None,
                         headers: Optional[list] = None,
                         message_queue_size: Optional[int] = MESSAGE_QUEUE_SIZE,
                         max_message_size: Optional[int] = MAX_MESSAGE_SIZE,
                         connect_timeout: Optional[float] = CON_TIMEOUT,
                         disconnect_timeout: Optional[float] = CON_TIMEOUT):
    """Opens a WebSocket client connection.

    .. note::

        This is an asynchronous contextmanager. It connects to the host
        on entering and disconnects on exiting. It yields a :class:`WebSocketConnection`
        instance.

    Parameters
    ----------
    url : str
        The URL to connect to.
    use_ssl : bool, ssl.SSLContext
        If you want to specify your own context, pass it as an argument.
        If you want to use the default context, set this to ``True``.
        ``False`` disables SSL.
    subprotocols : Optional[list]
        An optional list of strings that represent the subprotocols to use.
    headers: Optional[list]
        A list of tuples containing optional HTTP header key/value pairs to send
        with the handshake request. Please note that headers directly
        used by the protocol, e.g. ``Sec-WebSocket-Accept`` will be overwritten.
    message_queue_size : Optional[int]
        The total amount of messages that will be stored in the lib's internal buffer.
        Defaults to 1.
    max_message_size : Optional[int]
        The maximum message size as measured by ``len(message)``. If a received
        message exceeds this limit, the connections gets terminated with status code
        1009 - Message Too Big. Defaults to 1 Mb (2 ** 20).
    connect_timeout : Optional[float]
        The number of seconds to wait for the connection before timing out.
        Defaults to 60 seconds.
    disconnect_timeout : Optional[float]
        The number of seconds to wait for the connection to wait before timing out
        when closing the connection. Defaults to 60 seconds.

    Raises
    ------
    :exc:`TimeoutError`
        Raised for a connection timeout. See ``connect_timeout`` and ``disconnect_timeout``.
    :exc:`HandshakeError`
        Raised for any networking errors.
    """

    async with anyio.create_task_group() as task_group:
        try:
            with anyio.fail_after(connect_timeout):
                websocket = await create_websocket(
                    task_group, url, use_ssl=use_ssl, subprotocols=subprotocols, headers=headers,
                    message_queue_size=message_queue_size, max_message_size=max_message_size
                )
        except TimeoutError:
            raise TimeoutError from None
        except OSError as e:
            raise HandshakeError from e

        try:
            yield websocket
        finally:
            try:
                with anyio.fail_after(disconnect_timeout):
                    await websocket.close()
            except TimeoutError:
                raise TimeoutError from None


async def create_websocket(task_group: anyio.TaskGroup,
                           url: str,
                           *,
                           use_ssl: Union[bool, ssl.SSLContext],
                           subprotocols: Optional[list] = None,
                           headers: Optional[list] = None,
                           message_queue_size: int = MESSAGE_QUEUE_SIZE,
                           max_message_size: int = MAX_MESSAGE_SIZE) -> WebSocketConnection:
    """A more low-level version of :func:`open_websocket`.

    .. warning::

        Use :func:`open_websocket` if you don't need a
        custom task group.
        Also, you are responsible for closing the connection.

    Parameters
    ----------
    task_group : :class:`TaskGroup<anyio:anyio.TaskGroup>`
        The task group to run background tasks in.
    url : str
        The URL to connect to.
    use_ssl : bool, ssl.SSLContext
        If you want to specify your own context, pass it as an argument.
        If you want to use the default context, set this to ``True``.
        ``False`` disables SSL.
    subprotocols : Optional[list]
        An optional list of strings that represent the subprotocols to use.
    headers: Optional[list]
        A list of tuples containing optional HTTP header key/value pairs to send
        with the handshake request. Please note that headers directly
        used by the protocol, e.g. ``Sec-WebSocket-Accept`` will be overwritten.
    message_queue_size : int
        The total amount of messages that will be stored in the lib's internal buffer.
        Defaults to 1.
    max_message_size : int
        The maximum message size as measured by ``len(message)``. If a received
        message exceeds this limit, the connections gets terminated with status code
        1009 - Message Too Big. Defaults to 1 Mb (2 ** 20).

    Returns
    -------
    :class:`WebSocketConnection`
        The newly created WebSocket client connection.
    """

    host, port, resource, use_ssl = _url_to_host(url, use_ssl)

    if use_ssl is True:
        ssl_context = ssl.create_default_context()
    elif use_ssl is False:
        ssl_context = None
    elif isinstance(use_ssl, ssl.SSLContext):
        ssl_context = use_ssl
    else:
        raise TypeError('use_ssl argument must be bool or ssl.SSLContext')

    logger.debug('Connecting to %s...', url)

    tls = True if ssl_context else False
    stream = await anyio.connect_tcp(
        host, port, ssl_context=ssl_context, autostart_tls=tls, tls_standard_compatible=tls)
    if port in (80, 443):
        host_header = host
    else:
        host_header = '{}:{}'.format(host, port)

    wsproto = WSConnection(ConnectionType.CLIENT)
    connection = WebSocketConnection(
        stream, wsproto, host=host_header, path=resource, subprotocols=subprotocols,
        headers=headers, message_queue_size=message_queue_size, max_message_size=max_message_size
    )
    await task_group.spawn(connection._reader_task)
    await connection._open_handshake.wait()

    return connection


def _url_to_host(url, ssl_context):
    url = URL(url)
    if url.scheme not in ('ws', 'wss'):
        raise ValueError('WebSocket URL scheme must be "ws:" or "wss:"')

    if ssl_context is None:
        ssl_context = url.scheme == 'wss'
    elif url.scheme == 'ws':
        raise ValueError('SSL context must be None for "ws:" URL scheme')

    return url.host, url.port, url.path_qs, ssl_context
