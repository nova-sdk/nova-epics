"""Trame integration for EPICS instrument status retrieval."""

import json
from html import unescape
from pathlib import Path
from re import findall
from typing import Any, Dict, Generator, List
from urllib.parse import unquote_plus

import dpath
from trame.app import get_server
from trame.widgets import client, plotly
from trame.widgets import vuetify3 as vuetify
from trame_client.widgets.core import AbstractElement
from xmltodict import parse

from nova.epics.interface import EPICSInterface
from nova.trame.view.components import InputField
from nova.trame.view.layouts import VBoxLayout


class TrameEPICS(EPICSInterface):
    """Trame integration for EPICS instrument status retrieval."""

    def _flatten(self, entry: Any) -> Generator[Any, None, None]:
        if isinstance(entry, List):
            for item in entry:
                yield from self._flatten(item)
        else:
            yield entry

    def _replace_macros(self, pv_name: str, macro_dict: Dict[str, str]) -> str:
        full_name = pv_name
        for match in findall(r"\$\((\w+)\)", full_name):
            try:
                full_name = full_name.replace(f"$({match})", macro_dict[match])
            except KeyError:
                pass

        return full_name

    def connect(self, xml: str, macros: str, detector_count: int) -> None:
        """Connects to the EPICS Tomcat server and pulls initial PV values.

        Parameters
        ----------
        xml : str
            The contents of the XML config file for the instrument to pull PVs for.
        macros : str
            The macros string for the instrument.
        detector_count : int
            The number of detectors used by this instrument.
        """
        self.server.state["epics"] = {"pv_data": {}}
        bob_dict = parse(xml)

        decoded_macros = unescape(unquote_plus(macros))
        macro_dict = json.loads(decoded_macros)

        pv_list = self._flatten(dpath.values(bob_dict, "**/pv_name"))
        pv_names = {self._replace_macros(pv_name, macro_dict) for pv_name in pv_list}
        if "" in pv_names:
            pv_names.remove("")
        for pv in pv_names.copy():
            if "$(DET)" in pv:
                pv_names.remove(pv)
                for index in range(1, detector_count + 1):
                    pv_names.add(pv.replace("$(DET)", str(index)))

        client.Script(
            """window.dbwr = new DisplayBuilderWebRuntime("wss://status.sns.ornl.gov/pvws/pv");"""
            """window.dbwr.pvws.open();"""
        )

        for pv in pv_names:
            client.Script(f"""
                window.dbwr.pv_infos["{pv}"] = new PVInfo("{pv}");
                window.dbwr.pv_infos["{pv}"].subscriptions.push({{
                    "callback": (data) => {{
                        if (data.vtype === "VEnum") {{
                            if (data.labels.length == 2) {{
                                data.value = Boolean(data.value);
                            }} else {{
                                data.value = data.text;
                            }}
                        }}
                        window.trame.state.state.epics.pv_data["{pv}"] = data.value;
                        window.trame.state.dirty("epics");
                        window.trame.state.flush();
                    }}
                }});

                setTimeout(() => {{
                    window.dbwr.pvws.subscribe("{pv}");
                }}, 1000);
            """)

    def serve_javascript(self) -> None:
        js_path = (Path(__file__).parent / "assets" / "epics").resolve()
        self.server = get_server(None, client_type="vue3")
        self.server.enable_module(
            {
                "scripts": [
                    "assets/epics/jquery-3.7.1.min.js",
                    "assets/epics/base64.js",
                    "assets/epics/pvws.js",
                    "assets/epics/dbwr.js",
                ],
                "serve": {"assets/epics": js_path},
            }
        )

    def __init__(self) -> None:
        """Serves the necessary JavaScript files. This is called by __init__."""
        self.serve_javascript()


instance = TrameEPICS()


def get_epics_instance() -> TrameEPICS:
    """Retrieves an instance of the TrameEPICS singleton class."""
    return instance


class DisconnectedAlert:
    """Shows a spinner and message when the WebSocket is disconnected."""

    def __init__(self) -> None:
        with VBoxLayout(
            v_if=(
                "window?.dbwr?.pvws?.socket === undefined ||"
                "window.dbwr.pvws.socket.readyState !== window.WebSocket.OPEN"
            ),
            classes="position-absolute h-100 w-100",
            halign="center",
            style="z-index: 100",
            valign="center",
        ):
            with VBoxLayout():
                vuetify.VProgressCircular(indeterminate=True, size=16)
                vuetify.VTooltip("Connection to EPICS lost. Reconnecting…", activator="parent")


class PVInput(InputField):
    """Creates a read-only (by default) InputField that connects to the PV data object."""

    def __new__(cls, pv_name: str, append: str = "", **kwargs: Any) -> AbstractElement:
        with VBoxLayout(classes="position-relative", stretch=True):
            DisconnectedAlert()

            readonly = kwargs.pop("readonly", True)
            if append:
                with super().__new__(
                    cls,
                    v_if=f"'{pv_name}' in epics.pv_data",
                    v_model=f"epics.pv_data['{pv_name}']",
                    readonly=readonly,
                    **kwargs,
                ) as element:
                    with vuetify.Template(v_slot_append_inner=True):
                        vuetify.VLabel(append)

                return element

            return super().__new__(cls, v_model=f"epics.pv_data['{pv_name}']", readonly=readonly, **kwargs)


class PVPlot:
    """Creates a plotly-based figure for the PV data object."""

    def __init__(self, pv_name: str, **kwargs: Any) -> None:
        instrument_id = pv_name.split(":")[0]

        with VBoxLayout(
            v_if=(
                f"'{instrument_id}:Det:Neutrons' in epics.pv_data && "
                f"epics.pv_data['{instrument_id}:Det:Neutrons'] > 0 && "
                f"'{pv_name}' in epics.pv_data && "
                f"epics.pv_data['{pv_name}']"
            ),
            classes="border-md position-relative",
            stretch=True,
        ):
            # TODO: need to inject go.Figure here with test data from Zhongcan.
            plotly.Figure(**kwargs)
            DisconnectedAlert()
        with VBoxLayout(
            v_else=True, classes="border-md position-relative", halign="center", valign="center", stretch=True
        ):
            vuetify.VListSubheader("No Data")
            DisconnectedAlert()
