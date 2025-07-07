__all__ = ["MockLoom"]

from base_loom_server.base_mock_loom import BaseMockLoom

from toika_loom_server.utils import shaft_word_from_bytes


class MockLoom(BaseMockLoom):
    """Simulate a Toika ES dobby loom.

    The user controls this loom by:

    * Call command_reader.create_writer() to create a command writer.
    * Call reply_writer.create_reader() to create a reply reader.
    * Read replies from the reply reader.
    * Write commands to the command writer.
    """

    terminator = b""

    def __post_init__(self) -> None:
        if self.num_shafts % 8 != 0:
            raise ValueError(f"num_shafts={self.num_shafts} must be a multiple of 8")

    async def basic_read(self) -> bytes:
        """Read one command to the loom.

        Perform no error checking, except that self.reader exists.
        """
        assert self.reader is not None  # make mypy happy
        return await self.reader.readexactly(self.num_shafts // 8)

    async def handle_read_bytes(self, read_bytes: bytes) -> None:
        """Handle one command from the web server."""
        if len(read_bytes) != self.num_shafts // 8:
            self.log.warning(f"MockLoom: ignoring command {read_bytes!r}; length != {self.num_shafts // 8}")
            return
        # Note: type:ignore is needed when running mypy from pre-commit.
        if not self.pick_wanted:  # type: ignore[has-type]
            self.log.warning(f"MockLoom: ignoring command: {read_bytes!r}; pick not wanted")
            return

        self.shaft_word = shaft_word_from_bytes(read_bytes, num_bytes=self.num_shafts // 8)
        self.pick_wanted = False
        await self.report_pick_wanted()
        await self.report_shafts()

    async def move(self, shaft_word: int) -> None:
        """This loom does not report shafts moving, so skip the usual code."""
        self.moving = False  # paranoia; it should never be set
        self.shaft_word = shaft_word
        await self.report_shafts()

    async def report_direction(self) -> None:
        """Report direction (weave/unweave).

        Toika looms do not report direction when it changes on the dobby head,
        but instead wait until requesting the next pick, which is not
        when this method is called. So just log if verbose.
        """
        if self.verbose:
            self.log.info(f"{self}.direction_forward={self.direction_forward}")

    async def report_motion_state(self) -> None:
        """Report motion state.

        Toika looms do not report motion state, so just log if verbose.
        """
        if self.verbose:
            self.log.info(f"{self}.moving={self.moving}")

    async def report_pick_wanted(self) -> None:
        """Report pick wanted.

        Toika looms specify the direction (as set by the direction button
        on the dobby head).
        """
        if self.pick_wanted:
            reply = b"\x01" if self.direction_forward else b"\x02"
            await self.write(reply)

    async def report_shafts(self) -> None:
        """Report motion state.

        Toika looms do not report shafts, so just log if verbose.
        """
        if self.verbose:
            self.log.info(f"{self}.shaft_word={self.shaft_word}")
