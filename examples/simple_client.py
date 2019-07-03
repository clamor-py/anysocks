import anyio
from anysocks import open_connection
from anysocks.websocket import WebSocketConnection


async def main():
    async with open_connection('ws://echo.websocket.org') as con:
        con: WebSocketConnection
        print('Connection established!')

        # First, let's send some text to the server.
        text = input('What to send? ')
        await con.send(text)

        # Now, we receive and verify the server's response.
        message = await con.get_message()
        assert message == text, "Received {}, expected {}".format(message, text)

    print('Connection closed with code {}'.format(con.close_code.value))

anyio.run(main)
