import asyncio
import contextlib

from toika_loom_server import mock_loom
from toika_loom_server.loom_constants import TERMINATOR
from toika_loom_server.mock_loom import MockLoom, StreamReaderType, StreamWriterType

# Speed up tests
mock_loom.SHAFT_MOTION_DURATION = 0.1


@contextlib.asynccontextmanager
async def create_loom():
    """Create a MockLoom."""
    async with MockLoom(verbose=True) as loom:
        reader, writer = await loom.open_client_connection()
        yield loom, reader, writer


async def read_reply(reader: StreamReaderType, timeout: float = 1) -> str:
    async with asyncio.timeout(timeout):
        reply_bytes = await reader.readuntil(TERMINATOR)
        print(f"read mock loom reply {reply_bytes=}")
        assert reply_bytes[-1:] == TERMINATOR
        return reply_bytes[:-1].decode()


async def write_command(
    writer: StreamWriterType, command: bytes, timeout: float = 1
) -> None:
    writer.write(command + TERMINATOR)
    async with asyncio.timeout(timeout):
        await writer.drain()


async def test_raise_shafts() -> None:
    async with create_loom() as (loom, reader, writer):
        for shaftword in (0x0, 0x1, 0x5, 0xFE, 0xFF19, 0xFFFFFFFE, 0xFFFFFFFF):
            # Tell mock loom to request the next pick
            await write_command(writer, b"#n")
            reply = await read_reply(reader)
            assert reply == "1"
            # Send the requested shaft information
            loom.command_event.clear()
            await write_command(writer, shaftword.to_bytes(length=4, byteorder="big"))
            await loom.command_event.wait()
            assert loom.shaft_word == shaftword
        assert not loom.done_task.done()


async def test_oob_next_pick_and_toggle_direction() -> None:
    async with create_loom() as (loom, reader, writer):
        for expected_direction in (2, 1, 2, 1, 2, 1):
            await write_command(writer, b"#d")
            for _ in range(3):
                await write_command(writer, b"#n")
                reply = await read_reply(reader)
                assert reply == str(expected_direction)
        assert not loom.done_task.done()


async def test_oob_close_connection() -> None:
    async with create_loom() as (loom, reader, writer):
        await write_command(writer, b"#c")
        async with asyncio.timeout(1):
            await loom.done_task
        assert loom.reply_writer.is_closing()
        assert loom.command_reader.at_eof()
