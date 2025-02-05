from base_loom_server.testutils import BaseTestLoomServer

from toika_loom_server.main import app

# No need to reduce MockLoom.motion_duration to speed up tests
# because the Toika loom does not report motion state.


class TestLoomServer(BaseTestLoomServer):
    app = app
    motion_reported = False
