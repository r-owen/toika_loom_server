import io
import pathlib
import random
import tempfile
from typing import Any

from dtx_to_wif import read_dtx, read_wif

from toika_loom_server import mock_loom
from toika_loom_server.reduced_pattern import (
    ReducedPattern,
    reduced_pattern_from_pattern_data,
)
from toika_loom_server.testutils import WebSocketType, create_test_client, receive_dict

# Speed up tests
mock_loom.SHAFT_MOTION_DURATION = 0.1

datadir = pathlib.Path(__file__).parent / "data"

all_pattern_paths = list(datadir.glob("*.wif")) + list(datadir.glob("*.dtx"))


def select_pattern(
    websocket: WebSocketType,
    pattern_name: str,
    pick_number: int = 0,
    repeat_number: int = 1,
) -> ReducedPattern:
    """Select the pattern by name and read both expected replies.

    Check pick_number and repeat_number and return the pattern.
    """
    websocket.send_json(dict(type="select_pattern", name=pattern_name))
    reply = receive_dict(websocket)
    assert reply["type"] == "ReducedPattern"
    pattern = ReducedPattern.from_dict(reply)
    assert pattern.pick_number == pick_number
    assert pattern.repeat_number == repeat_number
    reply = receive_dict(websocket)
    assert reply == dict(
        type="CurrentPickNumber", pick_number=pick_number, repeat_number=repeat_number
    )
    return pattern


def test_jump_to_pick() -> None:
    pattern_name = all_pattern_paths[3].name

    with create_test_client(upload_patterns=all_pattern_paths[2:5]) as (
        client,
        websocket,
    ):
        pattern = select_pattern(websocket=websocket, pattern_name=pattern_name)
        num_picks_in_pattern = len(pattern.picks)

        for pick_number in (0, 1, num_picks_in_pattern // 3, num_picks_in_pattern):
            for repeat_number in (-1, 0, 1):
                websocket.send_json(
                    dict(
                        type="jump_to_pick",
                        pick_number=pick_number,
                        repeat_number=repeat_number,
                    )
                )
                reply = receive_dict(websocket)
                assert reply == dict(
                    type="JumpPickNumber",
                    pick_number=pick_number,
                    repeat_number=repeat_number,
                )


def test_oobcommand() -> None:
    pattern_name = all_pattern_paths[2].name

    with create_test_client(upload_patterns=all_pattern_paths[0:3]) as (
        client,
        websocket,
    ):
        pattern = select_pattern(websocket=websocket, pattern_name=pattern_name)
        num_picks_in_pattern = len(pattern.picks)

        # Make enough forward picks to get into the 3rd repeat
        expected_pick_number = 0
        expected_repeat_number = 1
        i = 0
        while not (expected_repeat_number == 3 and expected_pick_number > 2):
            i += 1
            expected_pick_number += 1
            if expected_pick_number > num_picks_in_pattern:
                expected_pick_number -= num_picks_in_pattern + 1
                expected_repeat_number += 1
            command_next_pick(
                websocket=websocket,
                jump_pending=False,
                expected_pick_number=expected_pick_number,
                expected_repeat_number=expected_repeat_number,
            )

        websocket.send_json(dict(type="weave_direction", forward=False))
        reply = receive_dict(websocket)
        assert reply == dict(type="WeaveDirection", forward=False)

        # Now go backwards at least two picks past the beginning
        end_pick_number = num_picks_in_pattern - 2
        while not (
            expected_pick_number == end_pick_number and expected_repeat_number == 0
        ):
            expected_pick_number -= 1
            if expected_pick_number < 0:
                expected_pick_number += num_picks_in_pattern + 1
                expected_repeat_number -= 1
            command_next_pick(
                websocket=websocket,
                jump_pending=False,
                expected_pick_number=expected_pick_number,
                expected_repeat_number=expected_repeat_number,
            )
        assert expected_pick_number == end_pick_number
        assert expected_repeat_number == 0

        # Change direction to forward
        websocket.send_json(dict(type="weave_direction", forward=True))
        expected_pick_number += 1
        reply = receive_dict(websocket)
        assert reply == dict(type="WeaveDirection", forward=True)

        command_next_pick(
            websocket=websocket,
            jump_pending=False,
            expected_pick_number=expected_pick_number,
            expected_repeat_number=expected_repeat_number,
        )


def command_next_pick(
    websocket: WebSocketType,
    jump_pending: bool,
    expected_pick_number: int,
    expected_repeat_number: int,
) -> None:
    """Command the next pick and test the replies.

    Parameters
    ----------
    websocket : WebSocketType
        websocket connection
    jump_pending : bool
        Is a jump pending?
    expected_pick_number : int
        Expected pick number of the next pick
    expected_repeat_number : int
        Expected repeat number of the next pick
    """
    websocket.send_json(dict(type="oobcommand", command="n"))
    expected_replies: list[dict[str, Any]] = []
    if jump_pending:
        expected_replies += [
            dict(
                type="JumpPickNumber",
                pick_number=None,
                repeat_number=None,
            ),
        ]
    expected_replies += [
        dict(
            type="CurrentPickNumber",
            pick_number=expected_pick_number,
            repeat_number=expected_repeat_number,
        ),
    ]
    for expected_reply in expected_replies:
        reply = receive_dict(websocket)
        assert reply == expected_reply


def test_pattern_persistence() -> None:
    rnd = random.Random(47)
    pattern_list = []
    with tempfile.NamedTemporaryFile() as f:
        with create_test_client(upload_patterns=all_pattern_paths, db_path=f.name) as (
            client,
            websocket,
        ):
            # Select a few patterns; for each one jump to some random
            # pick (including actually going to that pick).
            assert len(all_pattern_paths) > 3
            for path in (all_pattern_paths[0], all_pattern_paths[3]):
                pattern = select_pattern(websocket=websocket, pattern_name=path.name)
                pattern_list.append(pattern)
                pattern.pick_number = rnd.randrange(2, len(pattern.picks))
                pattern.repeat_number = rnd.randrange(-10, 10)
                websocket.send_json(
                    dict(
                        type="jump_to_pick",
                        pick_number=pattern.pick_number,
                        repeat_number=pattern.repeat_number,
                    )
                )
                reply = receive_dict(websocket)
                assert reply == dict(
                    type="JumpPickNumber",
                    pick_number=pattern.pick_number,
                    repeat_number=pattern.repeat_number,
                )
                command_next_pick(
                    websocket=websocket,
                    jump_pending=True,
                    expected_pick_number=pattern.pick_number,
                    expected_repeat_number=pattern.repeat_number,
                )

        # This expects that first pattern 0 and then pattern 3
        # was selected from all_pattern_paths:
        all_pattern_names = [path.name for path in all_pattern_paths]
        expected_pattern_names = (
            all_pattern_names[1:3]
            + all_pattern_names[4:]
            + [all_pattern_names[0], all_pattern_names[3]]
        )
        expected_current_pattern = pattern_list[1]

        with create_test_client(
            reset_db=False,
            expected_pattern_names=expected_pattern_names,
            expected_current_pattern=expected_current_pattern,
            db_path=f.name,
        ) as (
            client,
            websocket,
        ):
            for pattern in pattern_list:
                pattern = select_pattern(
                    websocket=websocket,
                    pattern_name=pattern.name,
                    pick_number=pattern.pick_number,
                    repeat_number=pattern.repeat_number,
                )

        # Now try again, but this time reset the database
        with create_test_client(
            reset_db=True,
        ) as (
            client,
            websocket,
        ):
            pass


def test_select_pattern() -> None:
    # Read a pattern file in and convert the data to a ReducedPattern
    pattern_path = all_pattern_paths[1]
    pattern_name = all_pattern_paths[1].name
    with open(pattern_path, "r") as f:
        raw_pattern_data = f.read()
    if pattern_name.endswith(".dtx"):
        with io.StringIO(raw_pattern_data) as dtx_file:
            pattern_data = read_dtx(dtx_file)
    elif pattern_name.endswith(".wif"):
        with io.StringIO(raw_pattern_data) as wif_file:
            pattern_data = read_wif(wif_file)
    else:
        raise AssertionError("Unexpected unsupported file type: {pattern_path!s}")
    reduced_pattern = reduced_pattern_from_pattern_data(
        name=pattern_name, data=pattern_data
    )

    with create_test_client(upload_patterns=all_pattern_paths[0:3]) as (
        client,
        websocket,
    ):
        returned_pattern = select_pattern(
            websocket=websocket, pattern_name=pattern_name
        )
        assert returned_pattern == reduced_pattern


def test_upload() -> None:
    with create_test_client(upload_patterns=all_pattern_paths) as (
        client,
        websocket,
    ):
        pass


def test_weave_direction() -> None:
    # TO DO: expand this test to test commanding the same direction
    # multiple times in a row, once I know what mock loom ought to do.
    pattern_name = all_pattern_paths[1].name

    with create_test_client(upload_patterns=all_pattern_paths[0:4]) as (
        client,
        websocket,
    ):
        select_pattern(websocket=websocket, pattern_name=pattern_name)

        for forward in (False, True):
            websocket.send_json(dict(type="weave_direction", forward=forward))
            reply = receive_dict(websocket)
            assert reply == dict(type="WeaveDirection", forward=forward)
