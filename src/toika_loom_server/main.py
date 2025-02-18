import importlib.resources

from fastapi import FastAPI

from .loom_server import LoomServer, ToikaAppRunner

PKG_NAME = "toika_loom_server"
PKG_FILES = importlib.resources.files(PKG_NAME)

app = FastAPI()


app_runner = ToikaAppRunner(
    app=app,
    server_class=LoomServer,
    favicon=PKG_FILES.joinpath("favicon-32x32.png").read_bytes(),
    app_package_name=f"{PKG_NAME}.main:app",
)


def run_toika_loom() -> None:
    app_runner.run()
