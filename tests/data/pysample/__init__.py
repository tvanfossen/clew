# SPDX-License-Identifier: MIT
"""Package marker so the Python R1 fixture is genuinely importable.

The fixture is PARSED by the tests, not executed, but `spawner.py` uses a
relative import (`from .models import Decoy`) to make the look-alike's origin the
thing that distinguishes it — and a relative import is only valid inside a
package. Without this file the fixture would be a claim the interpreter rejects.
"""
