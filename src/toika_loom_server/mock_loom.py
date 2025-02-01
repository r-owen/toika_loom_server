from __future__ import annotations

__all__ = ["MockLoom"]

import asyncio
import logging
from types import TracebackType
from typing import Type

from .loom_constants import LOG_NAME, TERMINATOR
from .mock_streams import (
    MockStreamReader,
    MockStreamWriter,
    StreamReaderType,
    StreamWriterType,
    open_mock_connection,
)

SHAFT_MOTION_DURATION: float = 1  # seconds for shafts to move
DIRECTION_NAMES = {True: "weave", False: "unweave"}


class MockLoom:
    """Simulate a Toika ES dobby loom.

    Parameters
    ----------
    verbose : bool
        If True, log diagnostic information.

    The user controls this loom by:

    * Call command_reader.create_writer() to create a command writer.
    * Call reply_writer.create_reader() to create a reply reader.
    * Read replies from the reply reader.
    * Write commands to the command writer.
    """

    def __init__(self, verbose: bool = True) -> None:
        self.log = logging.getLogger(LOG_NAME)
        self.verbose = verbose
        self.weave_forward = True
        self.reply_writer: StreamWriterType | None = None
        self.command_reader: StreamReaderType | None = None
        self.done_task: asyncio.Future = asyncio.Future()
        self.shaft_word = 0
        self.pick_wanted = False
        self.start_task = asyncio.create_task(self.start())
        self.command_event = asyncio.Event()

    async def start(self) -> None:
        self.command_reader, self.reply_writer = open_mock_connection(
            terminator=TERMINATOR
        )
        self.read_commands_task = asyncio.create_task(self.handle_commands_loop())

    async def close(self, cancel_read_commands_task=True) -> None:
        self.read_commands_task.cancel()
        if self.reply_writer is not None:
            self.reply_writer.close()
            await self.reply_writer.wait_closed()
        if not self.done_task.done():
            self.done_task.set_result(None)

    async def open_client_connection(self) -> tuple[StreamReaderType, StreamWriterType]:
        await self.start_task
        assert self.reply_writer is not None
        assert self.command_reader is not None
        # The isinstance tests make mypy happy, and might catch
        # a future bug if I figure out how to use virtual serial ports.
        if isinstance(self.reply_writer, MockStreamWriter) and isinstance(
            self.command_reader, MockStreamReader
        ):
            return (
                self.reply_writer.create_reader(),
                self.command_reader.create_writer(),
            )
        else:
            raise RuntimeError(
                f"Bug: {self.command_reader=} and {self.reply_writer=} must both be mock streams"
            )

    @classmethod
    async def amain(cls, verbose: bool = True) -> None:
        loom = cls(verbose=verbose)
        await loom.done_task

    def connected(self) -> bool:
        return (
            self.command_reader is not None
            and self.reply_writer is not None
            and not self.command_reader.at_eof()
            and not self.reply_writer.is_closing()
        )

    async def handle_commands_loop(self) -> None:
        try:
            while self.connected():
                assert self.command_reader is not None  # make mypy happy
                cmdbytes = await self.command_reader.readuntil(TERMINATOR)
                if not cmdbytes:
                    # Connection has closed
                    asyncio.create_task(self.close())
                self.command_event.set()
                if len(cmdbytes) == 5:
                    # cmdbytes should be a 32 bit int
                    # specifying which shafts to raise
                    if not self.pick_wanted:
                        # Ignore the command unless a pick is wanted
                        continue

                    self.shaft_word = int.from_bytes(cmdbytes[0:4], byteorder="big")
                    self.pick_wanted = False
                    if self.verbose:
                        self.log.info(f"MockLoom: raise shafts {self.shaft_word:08x}")
                elif len(cmdbytes) == 3 and cmdbytes[0:1] == b"#":
                    # Out of band command specific to the mock loom.
                    cmdstr = cmdbytes.decode()
                    match cmdstr[1].lower():
                        case "c":
                            if self.verbose:
                                self.log.info("MockLoom: oob close command")
                            asyncio.create_task(self.close())
                            return
                        case "d":
                            self.weave_forward = not self.weave_forward
                            if self.verbose:
                                self.log.info(
                                    "MockLoom: oob toggle weave direction: "
                                    f"{DIRECTION_NAMES[self.weave_forward]}"
                                )
                        case "n":
                            if self.verbose:
                                self.log.info("MockLoom: oob request next pick")
                            self.pick_wanted = True
                            await self.request_next_pick()
                        case _:
                            self.log.warning(
                                f"MockLoom: unrecognized oob command: {cmdstr!r}"
                            )
                else:
                    self.log.warning(f"MockLoom: unrecognized command: {cmdbytes!r}")
        except Exception:
            self.log.exception("MockLoom: handle_command_loop failed; giving up")
            await self.close(cancel_read_commands_task=False)

    async def reply(self, reply: str) -> None:
        """Issue the specified reply, which should not be terminated"""
        if self.verbose:
            self.log.info(f"MockLoom: send reply {reply!r}")
        if self.connected():
            assert self.reply_writer is not None
            self.reply_writer.write(reply.encode() + TERMINATOR)
            await self.reply_writer.drain()

    async def request_next_pick(self) -> None:
        reply = "1" if self.weave_forward else "2"
        await self.reply(reply)

    async def __aenter__(self) -> MockLoom:
        await self.start()
        return self

    async def __aexit__(
        self,
        type: Type[BaseException] | None,
        value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()
