# -*- coding: utf-8 -*-

import logging
import ssl
from typing import Optional, Union

import anyio.abc
from async_generator import async_generator, asynccontextmanager, yield_
from wsproto import ConnectionType, WSConnection
from yarl import URL

from .exceptions import HandshakeError
from .websocket import *

__all__ = (
    'open_connection',
    'create_websocket',
)

logger = logging.getLogger(__name__)


@asynccontextmanager
@async_generator
async def open_connection(url: str,
                          *,
                          use_ssl: Union[bool, ssl.SSLContext] = None,
                          subprotocols: Optional[list] = None,
                          headers: Optional[list] = None,
                          message_queue_size: Optional[int] = MESSAGE_QUEUE_SIZE,
                          max_message_size: Optional[int] = MAX_MESSAGE_SIZE,
                          connect_timeout: Optional[float] = CON_TIMEOUT,
                          disconnect_timeout: Optional[float] = CON_TIMEOUT):
    """Opens a WebSocket client connection.

    .. note::

        This is an asynchronous contextmanager. It connects to the host
        on entering and disconnects on exiting. It yields a
        :class:`~anysocks.websocket.WebSocketConnection` instance.

    Parameters
    ----------
    url : str
        The URL to connect to.
    use_ssl : Union[bool, ssl.SSLContext]
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
    :exc:`anysocks.exceptions.HandshakeError`
        Raised for any networking errors.
    """

    async with anyio.create_task_group() as task_group:
        try:
            async with anyio.fail_after(connect_timeout):
                websocket = await create_websocket(
                    task_group, url, use_ssl=use_ssl, subprotocols=subprotocols, headers=headers,
                    message_queue_size=message_queue_size, max_message_size=max_message_size
                )
        except TimeoutError:
            raise TimeoutError from None
        except OSError as exception:
            raise HandshakeError from exception

        try:
            await yield_(websocket)
        finally:
            try:
                async with anyio.fail_after(disconnect_timeout):
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
    """A more low-level version of :func:`open_connection`.

    .. warning::

        Use :func:`open_connection` if you don't need a
        custom task group.
        Also, you are responsible for closing the connection.

    Parameters
    ----------
    task_group : :class:`TaskGroup<anyio:anyio.abc.TaskGroup>`
        The task group to run background tasks in.
    url : str
        The URL to connect to.
    use_ssl : Union[bool, ssl.SSLContext]
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
    :class:`~anysocks.websocket.WebSocketConnection`
        The newly created WebSocket client connection.

    Raises
    ------
    :exc:`TypeError`
        Raised for unsupported arguments to ``use_ssl``.
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

    logger.info('Connecting to %s...', url)

    tls = True if ssl_context else False
    stream = await anyio.connect_tcp(
        host, int(port), ssl_context=ssl_context, autostart_tls=tls, tls_standard_compatible=False)
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
