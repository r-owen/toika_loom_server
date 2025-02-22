__all__ = ["MockLoom"]

from base_loom_server.base_mock_loom import BaseMockLoom


class MockLoom(BaseMockLoom):
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

    terminator = b""

    async def basic_read(self) -> bytes:
        """Read one command to the loom.

        Perform no error checking, except that self.reader exists.
        """
        assert self.reader is not None  # make mypy happy
        return await self.reader.readexactly(4)

    async def handle_read_bytes(self, read_bytes: bytes) -> None:
        """Handle one command from the web server."""

        if len(read_bytes) != 4:
            self.log.warning(f"MockLoom: ignoring command {read_bytes!r}; length != 4")
            return

        if not self.pick_wanted:  # type: ignore
            self.log.warning(
                f"MockLoom: ignoring command: {read_bytes!r}; pick not wanted"
            )
            return

        self.shaft_word = int.from_bytes(read_bytes, byteorder="big")
        self.pick_wanted = False
        await self.report_pick_wanted()
        await self.report_shafts()

    async def move(self, shaft_word: int) -> None:
        """This loom does not report shafts moving, so skip the usual code."""
        self.moving = False  # paranoia; it should never be set
        self.shaft_word = shaft_word
        await self.report_shafts()

    async def report_direction(self) -> None:
        self.log.info(f"{self}.weave_forward={self.weave_forward}")

    async def report_motion_state(self) -> None:
        self.log.info(f"{self}.moving={self.moving}")

    async def report_pick_wanted(self) -> None:
        if self.pick_wanted:
            reply = b"\x01" if self.weave_forward else b"\x02"
            await self.write(reply)

    async def report_shafts(self) -> None:
        self.log.info(f"{self}.shaft_word={self.shaft_word}")
