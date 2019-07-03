.. currentmodule:: anysocks

API Reference
=============

A comprehensive documentation of anysocks' public API.

Meta information
----------------

``anysocks`` has some variables containing meta information about
the project itself.

.. data:: __author__

    The author of the library.

.. data:: __copyright__

    A string holding copyright information.

.. data:: __docformat__

    The format of the documentation style.

.. data:: __license__

    The license of this project.

.. data:: __title__

    The actual project name.

.. data:: __version__

    The version of the library, e.g. ``0.1.2-alpha0``.

.. _client:

Client
------

The heart of this library. It provides convenience functions to
quickly establish a new WebSocket client connection without
having to worry about deep logic.

.. literalinclude:: ../../examples/simple_client.py
    :linenos:

open_connection
~~~~~~~~~~~~~~~

.. autofunction:: anysocks.client.open_connection

create_websocket
~~~~~~~~~~~~~~~~

.. autofunction:: anysocks.client.create_websocket

.. _websocket:

WebSocket
---------

``anysocks.websocket`` wraps around WebSocket connections
and provides a comfortable abstractions of the protocol
to easily send and receive messages.
*It however becomes uncomfortable if you want to use this module manually.*

WebSocketConnection
~~~~~~~~~~~~~~~~~~~

.. autoclass:: anysocks.websocket.WebSocketConnection
    :members:

.. _exceptions:

Exceptions
----------

Keeping a WebSocket connection alive may lead to issues.
These can have various reasons, like network errors or server
issues. Fortunately, ``anysocks.exceptions`` provides a few
useful exception classes that give you information about
what is going on.

AnySocksError
~~~~~~~~~~~~~

.. autoexception:: anysocks.exceptions.AnySocksError

HandshakeError
~~~~~~~~~~~~~~

.. autoexception:: anysocks.exceptions.HandshakeError

ConnectionRejected
~~~~~~~~~~~~~~~~~~

.. autoexception:: anysocks.exceptions.ConnectionRejected

ConnectionClosed
~~~~~~~~~~~~~~~~

.. autoexception:: anysocks.exceptions.ConnectionClosed
    :members:
