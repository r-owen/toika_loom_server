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

    async def handle_read_bytes(self, read_bytes: bytes) -> None:
        """Handle one command from the web server."""

        if len(read_bytes) == 5:
            # read_bytes should be a 32 bit int
            # specifying which shafts to raise
            if not self.pick_wanted:  # type: ignore
                # Ignore the command unless a pick is wanted
                return

            self.shaft_word = int.from_bytes(read_bytes[0:4], byteorder="big")
            self.pick_wanted = False
            await self.report_pick_wanted()
            await self.report_shafts()
        elif len(read_bytes) == 3 and read_bytes[0:1] == b"#":
            # Out of band command specific to the mock loom.
            cmdstr = read_bytes.decode()
            await self.oob_command(cmdstr[1:])

        else:
            self.log.warning(f"MockLoom: unrecognized command: {read_bytes!r}")

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
            reply = "1" if self.weave_forward else "2"
            await self.write(reply)

    async def report_shafts(self) -> None:
        self.log.info(f"{self}.shaft_word={self.shaft_word}")
