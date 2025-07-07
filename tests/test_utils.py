import random

import pytest

from toika_loom_server.utils import (
    bytes_from_shaft_word,
    reverse_bits,
    shaft_word_from_bytes,
)

rnd = random.Random(25)


def get_random_word(num_bits: int) -> int:
    return rnd.randrange(1, 1 << num_bits)


async def test_reverse_bits() -> None:
    assert reverse_bits(0, num_bits=1) == 0
    assert reverse_bits(1, num_bits=1) == 1
    for num_bits in (7, 8, 9, 15, 16, 17, 31, 32):
        assert reverse_bits(0, num_bits=num_bits) == 0
        assert 1 << (num_bits - 1) == reverse_bits(1, num_bits=num_bits)
        assert reverse_bits(1 << (num_bits - 1), num_bits=num_bits) == 1
        for _ in range(100):
            value = get_random_word(num_bits=num_bits)
            reversed_value = reverse_bits(value, num_bits=num_bits)
            valuestr = f"{value:0{num_bits}b}"
            reversed_valuestr = f"{reversed_value:0{num_bits}b}"
            assert valuestr[::-1] == reversed_valuestr
        with pytest.raises(ValueError):
            reverse_bits(0, num_bits=0)
        with pytest.raises(ValueError):
            reverse_bits(1 << num_bits, num_bits=num_bits)
        with pytest.raises(ValueError):
            reverse_bits(-1, num_bits=num_bits)


async def test_bytes_from_shaft_word() -> None:
    for num_bytes in (1, 2, 3, 4):
        num_bits = num_bytes * 8
        assert (0).to_bytes(length=num_bytes) == bytes_from_shaft_word(0, num_bytes=num_bytes)
        # bytes_from_shaft_word has the effect of reversing
        # the bits within each byte, so try doing this manually
        # one bit at a time
        for bitnum in range(8):
            for offset_bytes in range(num_bytes):
                value_no_offset = 1 << bitnum
                value = value_no_offset << (offset_bytes * 8)
                reversed_value_no_offset = reverse_bits(value_no_offset, num_bits=8)
                reversed_value = reversed_value_no_offset << (offset_bytes * 8)
                assert value.to_bytes(length=num_bytes) == bytes_from_shaft_word(
                    reversed_value, num_bytes=num_bytes
                )
                assert reversed_value.to_bytes(length=num_bytes) == bytes_from_shaft_word(
                    value, num_bytes=num_bytes
                )
                assert (
                    shaft_word_from_bytes(
                        bytes_from_shaft_word(value, num_bytes=num_bytes),
                        num_bytes=num_bytes,
                    )
                    == value
                )
                assert (
                    shaft_word_from_bytes(
                        bytes_from_shaft_word(reversed_value, num_bytes=num_bytes),
                        num_bytes=num_bytes,
                    )
                    == reversed_value
                )
        for _ in range(100):
            shaft_word = get_random_word(num_bits=num_bits)
            shaft_bytes = bytes_from_shaft_word(shaft_word, num_bytes=num_bytes)

            # Compute the expected value by reversing the bits within each byte
            shaft_word_as_bytes = shaft_word.to_bytes(length=num_bytes, byteorder="big")
            expected_bytes = bytes(bytearray(reverse_bits(elt, num_bits=8) for elt in shaft_word_as_bytes))
            assert expected_bytes == shaft_bytes

            assert shaft_word == shaft_word_from_bytes(shaft_bytes, num_bytes=num_bytes)
