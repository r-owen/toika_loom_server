__all__ = ["LoomServer"]

import pathlib

from base_loom_server.base_loom_server import BaseLoomServer
from base_loom_server.client_replies import MessageSeverityEnum, ShaftStateEnum
from base_loom_server.reduced_pattern import Pick

from .mock_loom import MockLoom


class LoomServer(BaseLoomServer):
    """Communicate with the client software and the loom.

    The preferred way to create and run a LoomServer is to call
    LoomServer.amain(...).

    Parameters
    ----------
    serial_port : str
        The name of the serial port, e.g. "/dev/tty0".
        If the name is "mock" then use a mock loom.
    translation_dict : dict[str, str]
        Translation dict.
    reset_db : bool
        If True, delete the old database and create a new one.
        A rescue aid, in case the database gets corrupted.
    verbose : bool
        If True, log diagnostic information.
    name : str
        User-assigned loom name.
    db_path : pathlib.Path | None
        Path to pattern database.
        Intended for unit tests, to avoid stomping on the real database.
    """

    def __init__(
        self,
        serial_port: str,
        translation_dict: dict[str, str],
        reset_db: bool,
        verbose: bool,
        name: str = "toika",
        db_path: pathlib.Path | None = None,
    ) -> None:
        super().__init__(
            mock_loom_type=MockLoom,
            serial_port=serial_port,
            translation_dict=translation_dict,
            reset_db=reset_db,
            verbose=verbose,
            name=name,
            db_path=db_path,
        )
        # The loom does not report motion state
        # so the shaft state is always DONE
        self.shaft_state = ShaftStateEnum.DONE

    async def write_shafts_to_loom(self, pick: Pick) -> None:
        """Send a shaft_word to the loom"""
        await self.write_to_loom(pick.shaft_word.to_bytes(length=4, byteorder="big"))
        self.shaft_word = pick.shaft_word

    async def handle_loom_reply(self, reply_bytes: bytes) -> None:
        """Process one reply from the loom."""
        reply = reply_bytes.decode().strip()
        # The only possible replies from the loom are:
        # "1": request next forward pick
        # "2": request next backward pick
        # TODO: allow the user to choose whether to use the loom's
        # commanded direction (respect the "reverse" button)
        # or the software's commanded direction.
        # For now only the software works.
        if reply not in {"1", "2"}:
            message = f"unexpected loom reply {reply!r}: should be '1' or '2'"
            self.log.warning(f"LoomServer: {message}")
            await self.report_command_problem(
                message=message,
                severity=MessageSeverityEnum.WARNING,
            )
            return

        await self.handle_next_pick_request()
        await self.report_shaft_state()
