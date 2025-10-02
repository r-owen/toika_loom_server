__all__ = ["LoomServer"]


from base_loom_server.base_loom_server import BaseLoomServer
from base_loom_server.enums import DirectionControlEnum, MessageSeverityEnum

from toika_loom_server.utils import bytes_from_shaft_word

from .mock_loom import MockLoom


class LoomServer(BaseLoomServer):
    """Communicate with the client software and the loom.

    The preferred way to create and run a LoomServer is to call
    LoomServer.amain(...).

    Args:
        num_shafts: The number of shafts the loom has.
        serial_port: The name of the serial port, e.g. "/dev/tty0".
            If the name is "mock" then use a mock loom.
        reset_db: If True, delete the old database and create a new one.
        verbose: If True, log diagnostic information.
        db_path: Path to the pattern database. Specify None for the
            default path. Unit tests specify a non-None value, to avoid
            stomping on the real database.
    """

    default_name = "toika"
    loom_reports_motion = False
    loom_reports_direction = False
    mock_loom_type = MockLoom
    supports_full_direction_control = False

    def __post_init__(self) -> None:
        if self.loom_info.num_shafts % 8 != 0:
            raise ValueError(f"num_shafts={self.loom_info.num_shafts} must be a multiple of 8")

    async def basic_read_loom(self) -> bytes:
        """Read one reply_bytes from the loom.

        Perform no error checking, except that self.loom_reader exists.
        """
        assert self.loom_reader is not None
        return await self.loom_reader.readexactly(1)

    async def write_shafts_to_loom(self, shaft_word: int) -> None:
        """Send a shaft_word to the loom."""
        shaft_bytes = bytes_from_shaft_word(shaft_word=shaft_word, num_bytes=self.loom_info.num_shafts // 8)
        await self.write_to_loom(shaft_bytes)
        self.shaft_word = shaft_word

    async def handle_loom_reply(self, reply_bytes: bytes) -> None:
        """Process one reply_bytes from the loom."""
        # The only possible replies from the loom are:
        # b"\x01": request next forward pick
        # b"\x02": request next backward pick
        if reply_bytes not in {b"\x01", b"\x02"}:
            message = f"unexpected loom reply_bytes {reply_bytes!r}: should be b'\x01' or b'\x02'"
            self.log.warning(f"LoomServer: {message}")
            await self.report_command_problem(
                message=message,
                severity=MessageSeverityEnum.WARNING,
            )
            return

        if self.settings.direction_control == DirectionControlEnum.LOOM:
            # Loom controls weave direction, and we don't know the state
            # of the loom's direction button until it requests a new pick
            new_direction_forward = reply_bytes == b"\x01"
            # Note: type:ignore is needed when running mypy from pre-commit.
            if new_direction_forward != self.direction_forward:  # type: ignore[has-type]
                self.direction_forward = new_direction_forward
                await self.report_direction()

        await self.handle_next_pick_request()
        await self.report_shaft_state()
