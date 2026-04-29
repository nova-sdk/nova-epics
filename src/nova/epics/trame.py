"""Trame integration for EPICS instrument status retrieval."""

import json
from html import unescape
from math import ceil
from pathlib import Path
from re import findall
from typing import Any, Dict, Generator, List, Optional
from urllib.parse import unquote_plus

import dpath
import numpy as np
import plotly.graph_objects as go
from trame.app import get_server
from trame.widgets import client, plotly
from trame.widgets import vuetify3 as vuetify
from trame_client.widgets.core import AbstractElement
from xmltodict import parse

from nova.epics.interface import EPICSInterface
from nova.trame.view.components import InputField
from nova.trame.view.layouts import VBoxLayout


class TrameEPICS(EPICSInterface):
    """Singleton class for connecting to an EPICS Tomcat server.

    You should not instantiate this class directly since it is intended to be used as a singleton. Instead, please call
    get_epics_instance().
    """

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

        pv_list = (
            list(self._flatten(dpath.values(bob_dict, "**/pv_name")))
            + list(self._flatten(dpath.values(bob_dict, "**/x_pv")))
            + list(self._flatten(dpath.values(bob_dict, "**/y_pv")))
        )
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
                        }} else if (data.vtype === "VDouble") {{
                            data.value = +data.value.toFixed(3);
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
        """Serves the necessary JavaScript files. This is called by __init__."""
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

    def __init__(
        self, pv_name: str, scaling_pv_name: str = "", data_width: Optional[int] = None, **kwargs: Any
    ) -> None:
        self.server = get_server(None, client_type="vue3")
        self.pv_name = pv_name
        self.scaling_pv_name = scaling_pv_name
        self.data_width = data_width

        self.display_type = "heatmap" if data_width is not None else "line"
        self.instrument_id = pv_name.split(":")[0]

        with VBoxLayout(
            v_if=(
                f"'{self.instrument_id}:Det:Neutrons' in epics.pv_data && "
                f"epics.pv_data['{self.instrument_id}:Det:Neutrons'] > 0 && "
                f"'{pv_name}' in epics.pv_data && "
                f"epics.pv_data['{pv_name}']"
            ),
            classes="border-md position-relative",
            stretch=True,
        ):
            figure = plotly.Figure(**kwargs)
            DisconnectedAlert()

            @self.server.state.change("epics")
            def on_pv_change(*args: Any, **kwargs: Any) -> None:
                figure.update(self.render_figure())

        with VBoxLayout(
            v_else=True, classes="border-md position-relative", halign="center", valign="center", stretch=True
        ):
            vuetify.VListSubheader("No Data")
            DisconnectedAlert()

    def render_figure(self) -> go.Figure:
        match self.display_type:
            case "heatmap":
                trace = self.render_heatmap()
            case "line":
                trace = self.render_linechart()

        figure = go.Figure(trace)
        figure.update_layout(margin={"b": 0, "l": 0, "r": 0, "t": 0}, xaxis_visible=False, yaxis_visible=False)

        return figure

    def render_heatmap(self) -> go.Heatmap:
        if self.data_width is None:
            return

        try:
            state = self.server.state
            data = np.array(state.epics["pv_data"][self.pv_name])
            max_value = state.epics["pv_data"].get(self.scaling_pv_name, max(data))
        except Exception:
            return

        rows = ceil(len(data) / self.data_width)
        cols = self.data_width
        transformed_data = np.resize(data, (rows, cols)).tolist()

        return go.Heatmap(
            x=list(range(rows)),
            y=list(reversed(range(cols))),
            z=transformed_data,
            colorscale="Viridis",
            showscale=False,
            zmin=min(data),
            zmax=max_value,
        )

    def render_linechart(self) -> go.Scatter:
        try:
            state = self.server.state
            data = np.array(state.epics["pv_data"][self.pv_name])
        except Exception:
            return

        return go.Scatter(x=list(range(len(data))), y=data, mode="lines")
