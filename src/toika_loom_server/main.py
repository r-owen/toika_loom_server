import argparse
import importlib.resources
import json
import locale
import logging
import pathlib
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse, Response

from .loom_constants import LOG_NAME
from .loom_server import DEFAULT_DATABASE_PATH, LoomServer

PKG_FILES = importlib.resources.files("toika_loom_server")
LOCALE_FILES = PKG_FILES.joinpath("locales")

# Avoid warnings about no event loop in unit tests
# by constructing when the server starts
loom_server: LoomServer | None = None

translation_dict: dict[str, str] = {}


def create_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "serial_port",
        help="Serial port connected to the loom, "
        "typically of the form /dev/tty... "
        "Specify 'mock' to run a mock (simulated) loom",
    )
    parser.add_argument(
        "-r",
        "--reset-db",
        action="store_true",
        help="reset pattern database?",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="print diagnostic information to stdout",
    )
    parser.add_argument(
        "--db-path",
        default=DEFAULT_DATABASE_PATH,
        type=pathlib.Path,
        help="Path for pattern database. "
        "Settable so unit tests can avoid changing the real database.",
    )
    return parser


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, FastAPI]:
    global loom_server
    global translation_dict
    translation_dict = get_translation_dict()
    parser = create_argument_parser()
    args = parser.parse_args()

    async with LoomServer(
        **vars(args), translation_dict=translation_dict
    ) as loom_server:
        yield


app = FastAPI(lifespan=lifespan)

log = logging.getLogger(LOG_NAME)


def get_translation_dict() -> dict[str, str]:
    """Get the translation dict for the current locale"""
    # Read a dict of key: None and turn into a dict of key: key
    default_dict = json.loads(LOCALE_FILES.joinpath("default.json").read_text())
    translation_dict = {key: key for key in default_dict}

    language_code = locale.getlocale(locale.LC_CTYPE)[0]
    log.info(f"Locale: {language_code!r}")
    if language_code is not None:
        short_language_code = language_code.split("_")[0]
        for lc in (short_language_code, language_code):
            translation_name = lc + ".json"
            translation_file = LOCALE_FILES.joinpath(translation_name)
            if translation_file.is_file():
                log.info(f"Loading translation file {translation_name!r}")
                locale_dict = json.loads(translation_file.read_text())
                purged_locale_dict = {
                    key: value
                    for key, value in locale_dict.items()
                    if value is not None
                }
                if purged_locale_dict != locale_dict:
                    log.warning(
                        f"Some entries in translation file {translation_name!r} "
                        "have null entries"
                    )
                translation_dict.update(purged_locale_dict)
    return translation_dict


@app.get("/")
async def get() -> HTMLResponse:
    global translation_dict

    display_html_template = PKG_FILES.joinpath("display.html_template").read_text()

    display_css = PKG_FILES.joinpath("display.css").read_text()

    display_js = PKG_FILES.joinpath("display.js").read_text()
    js_translation_str = "const TranslationDict = " + json.dumps(
        translation_dict, indent=4
    )
    display_js = display_js.replace("const TranslationDict = {}", js_translation_str)

    assert loom_server is not None
    is_mock = loom_server.mock_loom is not None
    display_debug_controls = "block" if is_mock else "none"

    display_html = display_html_template.format(
        display_css=display_css,
        display_js=display_js,
        display_debug_controls=display_debug_controls,
        **translation_dict,
    )

    return HTMLResponse(display_html)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    bindata = PKG_FILES.joinpath("favicon-32x32.png").read_bytes()
    return Response(content=bindata, media_type="image/x-icon")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    global loom_server
    assert loom_server is not None
    await loom_server.run_client(websocket=websocket)


def run_toika_loom() -> None:
    # Handle the help argument and also catch parsing errors right away
    parser = create_argument_parser()
    parser.parse_args()

    uvicorn.run(
        "toika_loom_server.main:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
        reload=True,
    )
