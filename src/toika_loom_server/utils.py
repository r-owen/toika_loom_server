def reverse_bits(bitmask: int, num_bits: int) -> int:
    """Reverse the bits in a bitmask.

    For example bitmask=0b1 reverses to:

    * 0b1 (no change) if num_bits = 1
    * 0b10 if num_bits = 2
    * 0b10000 if num_bits = 5

    Parameters
    ----------
    bitmask : int
        The integer bitmask to reverse
    num_bits : int
        The maximum number of bits in bitmask

    Raises ValueError
        If num_bits < 1, bitmask < 1, or bitmask > (1 << num_bits) - 1
    """
    if num_bits < 1:
        raise ValueError(f"{num_bits} < 1")
    max_value = (1 << num_bits) - 1
    if bitmask == 0:
        return 0
    if bitmask < 0:
        raise ValueError(f"{bitmask=} < 0")
    if bitmask > max_value:
        raise ValueError(f"{bitmask=} > {max_value}")

    new_value = 0
    for _ in range(num_bits):
        new_value <<= 1
        if bitmask & 1:
            new_value ^= 1
        bitmask >>= 1
    return new_value


def bytes_from_shaft_word(shaft_word: int, num_bytes: int) -> bytes:
    """Convert a shaft word to the bytes format needed by Toika

    Parameters
    ----------
    shaft_word : int
        Shaft word as a bit mask (bit N high if shaft N should rise)
    num_bytes: int
        The number of bytes in the shaft word = num_shafts / 8

    Returned bytes = the shaft word as a big-endian bytes,
    but with the bits in each byte reversed.
    This is implemented by reversing all bytes and then
    writing out the resulting integer as a little-endian bytes.
    """
    reversed_shaft_word = reverse_bits(bitmask=shaft_word, num_bits=num_bytes * 8)
    return reversed_shaft_word.to_bytes(length=num_bytes, byteorder="little")


def shaft_word_from_bytes(data_bytes: bytes, num_bytes: int) -> int:
    """Convert a bytes in the format needed by Toika to a shaft word.

    Parameters
    ----------
    data_bytes : bytes
        Shaft bytes string in Toika format.
    num_bytes: int
        The number of bytes in the shaft word = num_shafts / 8

    See bytes_from_shaft_word for the data format.
    """
    bitmask = int.from_bytes(data_bytes, byteorder="little")
    return reverse_bits(bitmask=bitmask, num_bits=num_bytes * 8)
