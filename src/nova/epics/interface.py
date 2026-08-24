"""Abstract class for defining EPICS interface."""

from abc import abstractmethod


class EPICSInterface:
    """Singleton class for connecting to an EPICS Tomcat server.

    You should not instantiate this class directly since it is intended to be used as a singleton. Instead, please call
    get_epics_instance().
    """

    test_mode: bool = False

    @abstractmethod
    def connect(self, xml: str, macros: str, detector_count: int, throttle: int = 2500) -> None:
        """Connects to the EPICS Tomcat server and pulls initial PV values.

        Parameters
        ----------
        xml : str
            The contents of the XML config file for the instrument to pull PVs for.
        macros : str
            The macros string for the instrument.
        detector_count : int
            The number of detectors used by this instrument.
        throttle : int
            The number of milliseconds to throttle UI updates to.
        """
        raise NotImplementedError("connect() must be implemented in a subclass")

    @abstractmethod
    def serve_javascript(self) -> None:
        """Serves the necessary JavaScript files. This is called by __init__."""
        raise NotImplementedError("serve_javascript() must be implemented in a subclass")


def enable_test_stream() -> None:
    """Turns on a test data stream for user interface testing when the EPICS server is not providing data."""
    raise NotImplementedError("enable_test_stream() must be implemented per-framework")


def get_epics_instance() -> EPICSInterface:
    """Retrieves an instance of the singleton class."""
    raise NotImplementedError("get_epics_instance() must be implemented per-framework")
