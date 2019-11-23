# -*- coding: utf-8 -*-

import unittest.mock

import anyio

from anysocks import open_connection, create_websocket
from anysocks.exceptions import *
from anysocks.websocket import *


class ConnectionTests(unittest.TestCase):
    def test_connection_1(self):
        async def test():
            data = b'test'

            async with open_connection('ws://echo.websocket.org') as con:
                self.assertIsInstance(con, WebSocketConnection)
                assert not con.closed
                assert con.is_client
                assert str(con).startswith('client-')
                self.assertIsNone(con.subprotocol)

                await con.send_message(data)
                message = await con.get_message()

                self.assertEqual(message, data)

            # Has the connection terminated without any issues?
            self.assertEqual(con.close_code.value, 1000)

        anyio.run(test)

    def test_connection_2(self):
        # Equal to test_connection_1, but this time
        # we're sending and expecting a string
        # instead of bytes.
        async def test():
            data = 'test'

            async with open_connection('ws://echo.websocket.org') as con:
                self.assertIsInstance(con, WebSocketConnection)
                assert not con.closed
                assert con.is_client
                assert str(con).startswith('client-')
                self.assertIsNone(con.subprotocol)

                await con.send_message(data)
                message = await con.get_message()

                self.assertEqual(message, data)

            # Has the connection terminated without any issues?
            self.assertEqual(con.close_code.value, 1000)

        anyio.run(test)

    def test_connection_3(self):
        async def test():
            data = b'test'

            async with open_connection('wss://echo.websocket.org') as con:
                self.assertIsInstance(con, WebSocketConnection)
                assert not con.closed
                assert con.is_client
                assert str(con).startswith('client-')
                self.assertIsNone(con.subprotocol)

                await con.send_message(data)
                message = await con.get_message()

                self.assertEqual(message, data)

            # Has the connection terminated without any issues?
            self.assertEqual(con.close_code.value, 1000)

        anyio.run(test)

    def test_connection_4(self):
        # Equal to test_connection_3, but this time
        # we're sending and expecting a string
        # instead of bytes.
        async def test():
            data = 'test'

            async with open_connection('wss://echo.websocket.org') as con:
                self.assertIsInstance(con, WebSocketConnection)
                assert not con.closed
                assert con.is_client
                assert str(con).startswith('client-')
                self.assertIsNone(con.subprotocol)

                await con.send_message(data)
                message = await con.get_message()

                self.assertEqual(message, data)

            # Has the connection terminated without any issues?
            self.assertEqual(con.close_code.value, 1000)

        anyio.run(test)

    def test_connection_5(self):
        async def test():
            try:
                async with open_connection('http://foo.bar/baz') as con:
                    self.assertIsInstance(con, WebSocketConnection)
            except ValueError:
                # ValueError tells us that our WebSocket URI
                # doesn't have a "ws" or "wss" scheme, so
                # everything is fine with this error.
                pass

        anyio.run(test)

    def test_connection_6(self):
        async def test():
            async with open_connection('wss://echo.websocket.org') as con:
                self.assertIsInstance(con, WebSocketConnection)
                assert not con.closed
                assert con.is_client
                assert str(con).startswith('client-')
                self.assertIsNone(con.subprotocol)

                self.assertEqual(con.host, 'echo.websocket.org')
                self.assertEqual(con.path, '/')

            # Has the connection terminated without any issues?
            self.assertEqual(con.close_code.value, 1000)

        anyio.run(test)

    def test_connection_7(self):
        async def test():
            close_string = 'Super important close message.'

            async with anyio.create_task_group() as task_group:
                con = await create_websocket(task_group, 'wss://echo.websocket.org', use_ssl=True)
                self.assertIsInstance(con, WebSocketConnection)
                assert not con.closed
                await con.close(1000, close_string)
                assert con.closed
                self.assertIsNone(con.subprotocol)

                self.assertEqual(con.close_code.value, 1000)
                self.assertEqual(con.close_reason, close_string)

        anyio.run(test)

    def test_connection_8(self):
        async def test():
            async with open_connection('wss://echo.websocket.org') as con:
                self.assertIsInstance(con, WebSocketConnection)
                assert not con.closed
                assert con.is_client
                assert str(con).startswith('client-')
                self.assertIsNone(con.subprotocol)

            try:
                await con.get_message()
            except ConnectionClosed as error:
                self.assertEqual(error.name, 'NORMAL_CLOSURE')
                self.assertEqual(error.code, 1000)
                self.assertEqual(error.reason, '')

        anyio.run(test)
