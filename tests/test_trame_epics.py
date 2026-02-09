"""pytest Fixture for setting up the Selenium driver and the server."""

from multiprocessing import Process
from time import sleep
from typing import Generator

from pytest import fixture
from trame.app import get_server
from trame.ui.vuetify3 import SinglePageLayout
from trame_server.core import Server

from nova.epics.trame import get_epics_instance


def run_server() -> None:
    server = get_server(None, client_type="vue3")
    server.start(open_browser=False)


def _get_layout() -> SinglePageLayout:
    layout = SinglePageLayout(get_server(None, client_type="vue3"))
    return layout


@fixture(autouse=True, scope="module")
def layout() -> Generator[Server, None, None]:
    server_process = Process(target=run_server)
    server_process.start()

    sleep(1)

    yield _get_layout()

    server_process.terminate()


def test_trame_epics(layout: SinglePageLayout) -> None:
    epics = get_epics_instance()
    with (
        layout,
        open("tests/data/test.bob", mode="r") as xml_file,
        open("tests/data/test.macros", mode="r") as macros_file,
    ):
        epics.connect(xml_file.read(), macros_file.read(), 1)
