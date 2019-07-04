.. currentmodule:: anysocks

Get started
===========

``anysocks`` requires Python 3.5+.

Generally speaking, it is best to use the latest versions
of both, ``anysocks`` and Python. Due to bug-fixes and new
features, ``anysocks`` may run more stable and is more
intuitive for you to use.

Installation
------------

There are multiple ways of installing ``anysocks``:

.. code-block:: sh

    # The latest release from PyPI
    pip install anysocks

    # The cutting edge development version from GitHub:
    pip install git+https://github.com/clamor-py/anysocks@master#egg=anysocks

Basic example
-------------

Here's a simple example on connecting to an echo server:

.. literalinclude:: ../../examples/simple_client.py
    :linenos:

Logging
-------

If you're having issues with your program and don't understand what ``anysocks``
is doing, enable logging for verbose output.

.. code-block:: python3

    import logging

    logger = logging.getLogger('anysocks')
    logger.setLevel(logging.DEBUG)
    logger.addHandler(logging.StreamHandler())

The log contains:

- Sending and receiving frames (``DEBUG``, ``WARNING`` for unknown frame types)
- Event dispatch handling (``DEBUG``)
- Connection openings and closures (``INFO``)
