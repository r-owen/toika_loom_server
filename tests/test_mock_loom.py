import asyncio
import contextlib

from base_loom_server.mock_streams import StreamReaderType, StreamWriterType

from toika_loom_server.mock_loom import MockLoom

# No need to reduce MockLoom.motion_duration to speed up tests
# because the Toika loom does not report motion state.


@contextlib.asynccontextmanager
async def create_loom():
    """Create a MockLoom."""
    async with MockLoom(verbose=True) as loom:
        reader, writer = await loom.open_client_connection()
        yield loom, reader, writer


async def read(reader: StreamReaderType, timeout: float = 1) -> bytes:
    async with asyncio.timeout(timeout):
        return await reader.readexactly(1)


async def write(writer: StreamWriterType, command: bytes, timeout: float = 1) -> None:
    writer.write(command + MockLoom.terminator)
    async with asyncio.timeout(timeout):
        await writer.drain()


async def test_raise_shafts() -> None:
    async with create_loom() as (loom, reader, writer):
        for shaftword in (0x0, 0x1, 0x5, 0xFE, 0xFF19, 0xFFFFFFFE, 0xFFFFFFFF):
            # Tell mock loom to request the next pick
            await loom.oob_command("n")
            reply = await read(reader)
            assert reply == b"\x01"
            # Send the requested shaft information
            loom.command_event.clear()
            await write(writer, shaftword.to_bytes(length=4, byteorder="big"))
            await loom.command_event.wait()
            assert loom.shaft_word == shaftword
        assert not loom.done_task.done()


async def test_oob_next_pick_and_toggle_direction() -> None:
    async with create_loom() as (loom, reader, writer):
        for expected_direction in (2, 1, 2, 1, 2, 1):
            await loom.oob_command("d")
            for _ in range(3):
                await loom.oob_command("n")
                reply = await read(reader)
                assert reply == expected_direction.to_bytes(length=1)
        assert not loom.done_task.done()


async def test_oob_close_connection() -> None:
    async with create_loom() as (loom, reader, writer):
        await loom.oob_command("c")
        async with asyncio.timeout(1):
            await loom.done_task
        assert loom.writer.is_closing()
        assert loom.reader.at_eof()
