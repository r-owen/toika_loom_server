from __future__ import annotations

__all__ = ["LoomServer", "DEFAULT_DATABASE_PATH"]

import asyncio
import dataclasses
import enum
import io
import json
import logging
import pathlib
import tempfile
from types import SimpleNamespace, TracebackType
from typing import Any, Type

from dtx_to_wif import read_dtx, read_wif
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState
from serial_asyncio import open_serial_connection  # type: ignore

from . import client_replies
from .client_replies import MessageSeverityEnum
from .loom_constants import BAUD_RATE, LOG_NAME, TERMINATOR
from .mock_loom import MockLoom
from .mock_streams import StreamReaderType, StreamWriterType
from .pattern_database import PatternDatabase
from .reduced_pattern import Pick, ReducedPattern, reduced_pattern_from_pattern_data

# The maximum number of patterns that can be in the history
MAX_PATTERNS = 25

DEFAULT_DATABASE_PATH = pathlib.Path(tempfile.gettempdir()) / "pattern_database.sqlite"

MOCK_PORT_NAME = "mock"


class CloseCode(enum.IntEnum):
    """WebSocket close codes

    A small subset of
    https://www.rfc-editor.org/rfc/rfc6455.html#section-7.4
    """

    NORMAL = 1000
    GOING_AWAY = 1001
    ERROR = 1011


class CommandError(Exception):
    pass


class LoomServer:
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
    db_path : pathlib.Path
        Path to pattern database.
        Intended for unit tests, to avoid stomping on the real database.
    """

    def __init__(
        self,
        serial_port: str,
        translation_dict: dict[str, str],
        reset_db: bool,
        verbose: bool,
        db_path: pathlib.Path = DEFAULT_DATABASE_PATH,
    ) -> None:
        self.log = logging.getLogger(LOG_NAME)
        if verbose:
            self.log.info(
                f"LoomServer({serial_port=!r}, {reset_db=!r}, {verbose=!r}, {db_path=!r})"
            )
        self.serial_port = serial_port
        self.translation_dict = translation_dict
        self.websocket: WebSocket | None = None
        self.pattern_db = PatternDatabase(db_path)
        self.verbose = verbose
        self.db_path = db_path
        if reset_db:
            db_path.unlink(missing_ok=True)
        self.loom_connecting = False
        self.loom_disconnecting = False
        self.client_connected = False
        self.mock_loom: MockLoom | None = None
        self.loom_reader: StreamReaderType | None = None
        self.loom_writer: StreamWriterType | None = None
        self.read_client_task: asyncio.Future = asyncio.Future()
        self.read_loom_task: asyncio.Future = asyncio.Future()
        self.done_task: asyncio.Future = asyncio.Future()
        self.current_pattern: ReducedPattern | None = None
        self.jump_pick = client_replies.JumpPickNumber(
            pick_number=None, repeat_number=None
        )
        self.weave_forward = True
        self.loom_error_flag = False
        self.command_dispatch_table = dict(
            clear_pattern_names=self.cmd_clear_pattern_names,
            file=self.cmd_file,
            jump_to_pick=self.cmd_jump_to_pick,
            select_pattern=self.cmd_select_pattern,
            weave_direction=self.cmd_weave_direction,
            oobcommand=self.cmd_oobcommand,
        )

    async def start(self) -> None:
        await self.pattern_db.init()
        await self.clear_jump_pick()
        # Restore current pattern, if any
        names = await self.pattern_db.get_pattern_names()
        if len(names) > 0:
            await self.select_pattern(names[-1])
        await self.connect_to_loom()

    async def close(
        self, stop_read_loom: bool = True, stop_read_client: bool = True
    ) -> None:
        """Disconnect from client and loom and stop all tasks."""
        if self.loom_writer is not None:
            if stop_read_loom:
                self.read_loom_task.cancel()
            if stop_read_client:
                self.read_client_task.cancel()
            self.loom_writer.close()
        if self.mock_loom is not None:
            await self.mock_loom.close()
        if not self.done_task.done():
            self.done_task.set_result(None)

    async def add_pattern(self, pattern: ReducedPattern) -> None:
        """Add a pattern to pattern database.

        Also purge the MAX_PATTERNS oldest entries (excluding
        the current pattern, if any) and report the new list
        of pattern names to the client.
        """
        await self.pattern_db.add_pattern(pattern=pattern, max_entries=MAX_PATTERNS)
        await self.report_pattern_names()

    @property
    def loom_connected(self) -> bool:
        """Return True if connected to the loom."""
        return not (
            self.loom_writer is None
            or self.loom_reader is None
            or self.loom_writer.is_closing()
            or self.loom_reader.at_eof()
        )

    async def close_websocket(
        self, ws: WebSocket, code: CloseCode = CloseCode.NORMAL, reason: str = ""
    ) -> None:
        """Close a websocket using best effort and a short timeout."""
        if ws.client_state == WebSocketState.DISCONNECTED:
            return
        try:
            async with asyncio.timeout(0.1):
                await ws.close(code, reason)
        except Exception as e:
            self.log.warning(f"LoomServer: failed to close websocket: {e!r}")

    async def connect_to_loom(self) -> None:
        """Connect to the loom.

        If already connected to loom, disconnect first, since
        connecting again may indicate that something is wrong.
        """
        if self.loom_connected:
            await self.disconnect_from_loom()
        try:
            self.loom_connecting = True
            await self.report_loom_connection_state()
            if self.serial_port == MOCK_PORT_NAME:
                self.mock_loom = MockLoom(verbose=self.verbose)
                self.loom_reader, self.loom_writer = (
                    await self.mock_loom.open_client_connection()
                )
            else:
                self.loom_reader, self.loom_writer = await open_serial_connection(
                    url=self.serial_port, baudrate=BAUD_RATE
                )
            self.loom_connecting = False
            await self.report_loom_connection_state()
        except Exception as e:
            self.loom_connecting = False
            await self.report_loom_connection_state(reason=str(e))
            raise
        finally:
            self.loom_connecting = False

        self.read_loom_task = asyncio.create_task(self.read_loom_loop())

    async def run_client(self, websocket: WebSocket) -> None:
        """Run a client connection, closing any existing connection.

        Also open a connection to the loom, if that was closed.

        Parameters
        ----------
        websocket : WebSocket
            Connection to the client.
        """
        if self.client_connected:
            self.log.info(
                "LoomServer: a client was already connected; closing that connection"
            )
            await self.disconnect_client()
        await websocket.accept()
        self.websocket = websocket
        self.read_client_task = asyncio.create_task(self.read_client_loop())
        if not self.loom_connected:
            try:
                await self.connect_to_loom()
            except Exception as e:
                # Note: connect_to_loom already reported the
                # (lack of) connection state, including the reason.
                # But log it here.
                self.log.exception(
                    f"LoomServer: failed to reconnect to the loom: {e!r}"
                )
        await self.done_task

    async def disconnect_client(self, cancel_read_client_loop: bool = True) -> None:
        self.read_client_task.cancel()
        websocket = self.websocket
        self.websocket = None
        if websocket is not None:
            await self.close_websocket(
                websocket,
                code=CloseCode.GOING_AWAY,
                reason=self.t("another client took control"),
            )

    async def disconnect_from_loom(self) -> None:
        """Disconnect from the loom. A no-op if already disconnected."""

        if not self.loom_connected:
            return
        self.loom_disconnecting = True
        await self.report_loom_connection_state()
        try:
            if self.loom_writer is not None:
                self.loom_writer.close()
                self.loom_reader = None
                self.loom_writer = None
            self.mock_loom = None
        finally:
            self.loom_disconnecting = False
            await self.report_loom_connection_state()

    async def command_pick(self, pick: Pick) -> None:
        """Send an =C<shaft_word> pick command to the loom"""
        shaft_word = sum(1 << i for i, isup in enumerate(pick.are_shafts_up) if isup)
        await self.command_loom(f"=C{shaft_word:08x}")

    async def clear_jump_pick(self, force_output=False):
        """Clear self.jump_pick and report value if changed or force_output

        Parameters
        ----------
        force_output : bool
            If True then report JumpPickNumber, even if it has not changed.
        """
        null_jump_pick = client_replies.JumpPickNumber(
            pick_number=None, repeat_number=None
        )
        do_report = force_output or self.jump_pick != null_jump_pick
        self.jump_pick = null_jump_pick
        if do_report:
            await self.report_jump_pick_number()

    async def command_loom(self, cmd: str) -> None:
        """Send a command to the loom.

        Parameters
        ----------
        cmd : str
            The command to send, without a terminator.
            (This method will append the terminator).
        """
        if self.loom_writer is None or self.loom_writer.is_closing():
            raise RuntimeError("Cannot write to the loom: no connection.")
        cmd_bytes = cmd.encode() + TERMINATOR
        if self.verbose:
            self.log.info(f"LoomServer: sending command to loom: {cmd_bytes!r}")
        self.loom_writer.write(cmd_bytes)
        await self.loom_writer.drain()

    def increment_pick_number(self) -> int:
        """Increment pick_number in the specified direction.

        Increment repeat_number as well, if appropriate.

        Return the new pick number. This will be 0 if repeat_number changed,
        or if unweaving and repeat_number would be decremented to 0.
        """
        if self.current_pattern is None:
            return 0
        return self.current_pattern.increment_pick_number(
            weave_forward=self.weave_forward
        )

    async def cmd_clear_pattern_names(self, command: SimpleNamespace) -> None:
        # Clear the pattern database
        # Then add the current pattern (if any)
        await self.pattern_db.clear_database()
        if self.current_pattern is not None:
            await self.add_pattern(self.current_pattern)
        else:
            await self.report_pattern_names()

    async def cmd_file(self, command: SimpleNamespace) -> None:
        filename = command.name
        try:
            if self.verbose:
                self.log.info(
                    f"LoomServer: read weaving pattern {filename!r}: data={command.data[0:40]!r}...",
                )
            if filename.lower().endswith(".dtx"):
                with io.StringIO(command.data) as dtx_file:
                    pattern_data = read_dtx(dtx_file)
            elif filename.lower().endswith(".wif"):
                with io.StringIO(command.data) as wif_file:
                    pattern_data = read_wif(wif_file)
            else:
                raise CommandError(
                    f"Cannot load pattern {filename!r}: unsupported file type"
                )
            pattern = reduced_pattern_from_pattern_data(
                name=command.name, data=pattern_data
            )
            await self.add_pattern(pattern)

        except Exception as e:
            await self.report_command_problem(
                message=f"Failed to read pattern {filename!r}: {e!r}",
                severity=MessageSeverityEnum.WARNING,
            )

    async def cmd_jump_to_pick(self, command: SimpleNamespace) -> None:
        if self.current_pattern is None:
            raise CommandError(
                self.t("cannot jump to a pick") + ": " + self.t("no pattern")
            )
        if command.pick_number is not None:
            if command.pick_number < 0:
                raise CommandError(
                    self.t("invalid pick number") + f" {command.pick_number} < 0"
                )
            max_pick_number = len(self.current_pattern.picks)
            if command.pick_number > max_pick_number:
                raise CommandError(
                    self.t("invalid pick number")
                    + f" {command.pick_number} > {max_pick_number}"
                )

        self.jump_pick = client_replies.JumpPickNumber(
            pick_number=command.pick_number,
            repeat_number=command.repeat_number,
        )
        await self.report_jump_pick_number()

    async def cmd_select_pattern(self, command: SimpleNamespace) -> None:
        name = command.name
        if self.current_pattern is not None and self.current_pattern.name == name:
            return
        await self.select_pattern(name)
        await self.clear_jump_pick()

    async def cmd_weave_direction(self, command: SimpleNamespace) -> None:
        # Warning: this code assumes that the loom server sends "=u"
        # after it receives "=U". It is not clear from the manual
        # if that is actually the case.
        loom_command = f"=U{int(not command.forward)}"
        await self.command_loom(loom_command)

    async def cmd_oobcommand(self, command: SimpleNamespace) -> None:
        await self.command_loom(f"=#{command.command}")

    async def read_client_loop(self) -> None:
        """Read and process commands from the client."""
        # report loom connection state
        # and (if connected) request loom status
        try:
            self.client_connected = True
            await self.report_loom_connection_state()
            await self.report_pattern_names()
            await self.report_weave_direction()
            await self.clear_jump_pick(force_output=True)
            await self.report_current_pattern()
            await self.report_current_pick_number()
            if self.loom_connected:
                # request loom status
                await self.command_loom("=Q")
            else:
                await self.connect_to_loom()
            while self.client_connected:
                assert self.websocket is not None
                try:
                    data = await self.websocket.receive_json()
                except json.JSONDecodeError:
                    self.log.info(
                        "LoomServer: ignoring invalid command: not json-encoded"
                    )

                # Parse the command
                try:
                    cmd_type = data.get("type")
                    if cmd_type is None:
                        await self.report_command_problem(
                            message=f"Invalid command; no 'type' field: {data!r}",
                            severity=MessageSeverityEnum.WARNING,
                        )
                        continue
                    command = SimpleNamespace(**data)
                    if self.verbose:
                        msg_summary = str(command)
                        if len(msg_summary) > 80:
                            msg_summary = msg_summary[0:80] + "..."
                        self.log.info(f"LoomServer: read command {msg_summary}")
                    cmd_handler = self.command_dispatch_table.get(cmd_type)
                except Exception as e:
                    message = f"command {data} failed: {e!r}"
                    self.log.exception(f"Loom Server: {message}")
                    await self.report_command_problem(
                        message=message,
                        severity=MessageSeverityEnum.ERROR,
                    )

                # Execute the command
                try:
                    if cmd_handler is None:
                        await self.report_command_problem(
                            message=f"Invalid command; unknown type {command.type!r}",
                            severity=MessageSeverityEnum.ERROR,
                        )
                        continue
                    await cmd_handler(command)
                except CommandError as e:
                    await self.report_command_problem(
                        message=str(e),
                        severity=MessageSeverityEnum.ERROR,
                    )
                except Exception as e:
                    message = f"command {command} unexpectedly failed: {e!r}"
                    self.log.exception(f"LoomServer: {message}")
                    await self.report_command_problem(
                        message=message,
                        severity=MessageSeverityEnum.ERROR,
                    )

        except asyncio.CancelledError:
            return
        except WebSocketDisconnect:
            self.log.info("LoomServer: client disconnected")
            return
        except Exception as e:
            self.log.exception(f"LoomServer: bug: client read looop failed: {e!r}")
            await self.report_command_problem(
                message="Client read loop failed; try refreshing",
                severity=MessageSeverityEnum.ERROR,
            )
            self.client_connected = False
            if self.websocket is not None:
                await self.close_websocket(
                    self.websocket, code=CloseCode.ERROR, reason=repr(e)
                )

    async def read_loom_loop(self) -> None:
        """Read and process replies from the loom."""
        try:
            if self.loom_reader is None:
                raise RuntimeError("No loom reader")
            while True:
                reply_bytes = await self.loom_reader.readuntil(TERMINATOR)
                if self.verbose:
                    self.log.info(f"LoomServer: read loom reply: {reply_bytes!r}")
                if not reply_bytes:
                    print("WARNING: no bytes; quit read_loom_loop")
                    return
                reply = reply_bytes.decode().strip()
                if len(reply) < 2:
                    message = f"invalid loom reply {reply!r}: less than 2 chars"
                    self.log.warning(f"LoomServer: {message}")
                    await self.report_command_problem(
                        message=message,
                        severity=MessageSeverityEnum.WARNING,
                    )
                    continue
                if reply[0] != "=":
                    message = f"invalid loom reply {reply!r}: no leading '='"
                    self.log.warning(f"LoomServer: {message}")
                    await self.report_command_problem(
                        message=message,
                        severity=MessageSeverityEnum.WARNING,
                    )
                    continue
                reply_char = reply[1]
                reply_data = reply[2:]
                match reply_char:
                    case "c":
                        # Shafts that are up
                        pass
                    case "u":
                        # Weave direction
                        # The loom expects a new pick, as a result
                        if reply_data == "0":
                            self.weave_forward = True
                        elif reply_data == "1":
                            self.weave_forward = False
                        else:
                            message = (
                                f"invalid loom reply {reply!r}: "
                                "direction must be 0 or 1"
                            )
                            self.log.warning(f"LoomServer: {message}")
                            await self.report_command_problem(
                                message=message, severity=MessageSeverityEnum.WARNING
                            )
                            continue
                        await self.report_weave_direction()
                    case "s":
                        # Loom status (may include a request for the next pick)
                        state_word = int(reply_data, base=16)
                        await self.report_loom_state(state_word)

                        # Check for error flag
                        error_flag = bool(state_word & 0x8)
                        if error_flag != self.loom_error_flag:
                            self.loom_error_flag = error_flag
                            if self.verbose:
                                self.log.info(
                                    f"LoomServer: loom error flag changed to {error_flag}"
                                )

                        pick_wanted = bool(state_word & 0x4)
                        if pick_wanted and self.current_pattern is not None:
                            # Command a new pick, if there is one.
                            if self.jump_pick.pick_number is not None:
                                new_pick_number = self.jump_pick.pick_number
                                self.current_pattern.set_current_pick_number(
                                    new_pick_number
                                )
                            else:
                                new_pick_number = self.increment_pick_number()
                            if self.jump_pick.repeat_number is not None:
                                self.current_pattern.repeat_number = (
                                    self.jump_pick.repeat_number
                                )
                            pick = self.current_pattern.get_current_pick()
                            await self.command_pick(pick)
                            await self.clear_jump_pick()
                            await self.report_current_pick_number()

        except asyncio.CancelledError:
            pass
        except Exception as e:
            message = f"Server stopped listening to the loom: {e!r}"
            self.log.exception(f"LoomServer: {message}")
            await self.report_command_problem(
                message=message,
                severity=MessageSeverityEnum.ERROR,
            )
            await self.disconnect_from_loom()

    async def reply_to_client(self, reply: Any) -> None:
        """Send a reply to the client.

        Parameters
        ----------
        reply : dataclasses.dataclass
            The reply as a dataclass. It should have a "type" field
            whose value is a string.
        """
        if self.client_connected:
            assert self.websocket is not None
            reply_dict = dataclasses.asdict(reply)
            if self.verbose:
                reply_str = str(reply_dict)
                if len(reply_str) > 120:
                    reply_str = reply_str[0:120] + "..."
                self.log.info(f"LoomServer: reply to client: {reply_str}")
            await self.websocket.send_json(reply_dict)
        else:
            if self.verbose:
                reply_str = str(reply)
                if len(reply_str) > 120:
                    reply_str = reply_str[0:120] + "..."
                self.log.info(
                    f"LoomServer: do not send reply {reply_str}; not connected"
                )

    async def report_command_problem(self, message: str, severity: MessageSeverityEnum):
        """Report a CommandProblem to the client."""
        reply = client_replies.CommandProblem(message=message, severity=severity)
        await self.reply_to_client(reply)

    async def report_current_pattern(self) -> None:
        """Report pattern to the client"""
        if self.current_pattern is not None:
            await self.reply_to_client(self.current_pattern)

    async def report_loom_connection_state(self, reason: str = "") -> None:
        """Report LoomConnectionState to the client."""
        if self.loom_connecting:
            state = client_replies.ConnectionStateEnum.CONNECTING
        elif self.loom_disconnecting:
            state = client_replies.ConnectionStateEnum.DISCONNECTING
        elif self.loom_connected:
            state = client_replies.ConnectionStateEnum.CONNECTED
        else:
            state = client_replies.ConnectionStateEnum.DISCONNECTED
        reply = client_replies.LoomConnectionState(state=state, reason=reason)
        await self.reply_to_client(reply)

    async def report_loom_state(
        self,
        state_word: int,
    ) -> None:
        """Report LoomState to the client."""
        reply = client_replies.LoomState.from_state_word(state_word)
        await self.reply_to_client(reply)

    async def report_pattern_names(self) -> None:
        """Report PatternNames to the client."""
        names = await self.pattern_db.get_pattern_names()
        reply = client_replies.PatternNames(names=names)
        await self.reply_to_client(reply)

    async def report_current_pick_number(self) -> None:
        """Report CurrentPickNumber to the client."""
        if self.current_pattern is None:
            return
        await self.pattern_db.update_pick_number(
            pattern_name=self.current_pattern.name,
            pick_number=self.current_pattern.pick_number,
            repeat_number=self.current_pattern.repeat_number,
        )
        reply = client_replies.CurrentPickNumber(
            pick_number=self.current_pattern.pick_number,
            repeat_number=self.current_pattern.repeat_number,
        )
        await self.reply_to_client(reply)

    async def report_jump_pick_number(self) -> None:
        """Report JumpPickNumber to the client."""
        await self.reply_to_client(self.jump_pick)

    async def report_weave_direction(self) -> None:
        """Report WeaveDirection"""
        client_reply = client_replies.WeaveDirection(forward=self.weave_forward)
        await self.reply_to_client(client_reply)

    async def select_pattern(self, name: str) -> None:
        try:
            pattern = await self.pattern_db.get_pattern(name)
        except LookupError:
            raise CommandError(f"select_pattern failed: no such pattern: {name}")
        self.current_pattern = pattern
        await self.report_current_pattern()
        await self.report_current_pick_number()

    def t(self, phrase: str) -> str:
        """Translate a phrase, if possible."""
        if phrase not in self.translation_dict:
            self.log.warning(f"{phrase!r} not in translation dict")
        return self.translation_dict.get(phrase, phrase)

    async def __aenter__(self) -> LoomServer:
        await self.start()
        return self

    async def __aexit__(
        self,
        type: Type[BaseException] | None,
        value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()
