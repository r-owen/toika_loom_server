__all__ = ["BAUD_RATE", "LOG_NAME", "TERMINATOR"]

# baud rate of loom's FTDI serial port
BAUD_RATE = 9600

# Name of the primary log used by uvicorn.
# This value is from https://stackoverflow.com/a/77007723
LOG_NAME = "uvicorn.error"

# terminator bytes for commands and replies
TERMINATOR = b"\r"
