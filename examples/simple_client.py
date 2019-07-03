import anyio
from anysocks import open_connection


async def main():
    async with open_connection('ws://localhost:5000/') as con:
        print('Connection established!')
        await con.send('Hello there!')
        message = await con.get_message()
        print('Received message: {}'.format(message))

    print('Connection closed!')

anyio.run(main)
