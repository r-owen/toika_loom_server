__all__ = ["LoomServer"]

import argparse
import pathlib

from base_loom_server.app_runner import AppRunner
from base_loom_server.base_loom_server import BaseLoomServer
from base_loom_server.client_replies import MessageSeverityEnum, ShaftStateEnum

from .mock_loom import MockLoom

AllowedDirectionControlValues = ("loom", "software")


class ToikaAppRunner(AppRunner):
    def create_argument_parser(self) -> argparse.ArgumentParser:
        parser = super().create_argument_parser()
        parser.add_argument(
            "--direction-control",
            help="What controls the direction of weaving? Must be either "
            "loom: the button on dobby head, "
            "or software: the up/down arrow button next to the pattern display",
            choices=AllowedDirectionControlValues,
            default="software",
        )
        return parser


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
    direction_control : str
        Which determines weave direction: must be "loom" or "software".
    name : str
        User-assigned loom name.
    db_path : pathlib.Path | None
        Path to pattern database.
        Intended for unit tests, to avoid stomping on the real database.
    """

    loom_reports_motion = False
    loom_reports_direction = False

    def __init__(
        self,
        serial_port: str,
        translation_dict: dict[str, str],
        reset_db: bool,
        verbose: bool,
        direction_control: str,
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
        if direction_control not in AllowedDirectionControlValues:
            raise ValueError(
                f"{direction_control=} must be one of {AllowedDirectionControlValues}"
            )
        self.shaft_state = ShaftStateEnum.DONE
        self.enable_software_weave_direction = direction_control == "software"

    async def basic_read_loom(self) -> bytes:
        """Read one reply_bytes from the loom.

        Perform no error checking, except that self.loom_reader exists.
        """
        assert self.loom_reader is not None
        return await self.loom_reader.readexactly(1)

    async def write_shafts_to_loom(self, shaft_word: int) -> None:
        """Send a shaft_word to the loom"""
        await self.write_to_loom(shaft_word.to_bytes(length=4, byteorder="big"))
        self.shaft_word = shaft_word

    async def handle_loom_reply(self, reply_bytes: bytes) -> None:
        """Process one reply_bytes from the loom."""
        # The only possible replies from the loom are:
        # b"\x01": request next forward pick
        # b"\x02": request next backward pick
        # TODO: allow the user to choose whether to use the loom's
        # commanded direction (respect the "reverse" button)
        # or the software's commanded direction.
        # For now only the software works.
        if reply_bytes not in {b"\x01", b"\x02"}:
            message = f"unexpected loom reply_bytes {reply_bytes!r}: should be b'\x01' or b'\x02'"
            self.log.warning(f"LoomServer: {message}")
            await self.report_command_problem(
                message=message,
                severity=MessageSeverityEnum.WARNING,
            )
            return

        if not self.enable_software_weave_direction:
            # Loom controls weave direction, and we don't know the state
            # of the loom's direction button until it requests a new pick
            new_weave_forward = reply_bytes == b"\x01"
            if new_weave_forward != self.weave_forward:  # type: ignore
                self.weave_forward = new_weave_forward
                await self.report_weave_direction()

        await self.handle_next_pick_request()
        await self.report_shaft_state()
