.. nova-trame documentation master file, created by
   sphinx-quickstart on Mon Sep 30 16:18:03 2024.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

======================
NOVA EPICS Integration
======================

Thank you for your interest in developing interactive applications for `NOVA <https://nova.ornl.gov/>`_. This
documentation describes how you can retrieve unprivileged instrument status information from EPICS for use in
NOVA applications.

This package can be installed with:

.. code-block:: bash

    pip install "nova-epics[your_framework]"

Currently, the only supported option for frameworks is `"trame" <https://www.kitware.com/trame/>__`.

This library works by running JavaScript code that creates a WebSocket connection to an EPICS Tomcat server
and then stores the necessary information in the application state. The steps to use it are to:

1. Retrieve an instance of the interface class via `get_epics_instance()`.
2. Call `connect()` with XML and macro data needed to retrieve the correct PVs from EPICS.
3. (Optional) Use the provided components to use the retrieved PVs in your application.

For step 2, you will need to provide an XML file and a macros string. https://github.com/nova-sdk/nova-epics/blob/main/tests contains examples. You can typically get both of these for a desired instrument via the URL of the DBWR-based status page.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   api
