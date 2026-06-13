"""Voice twin entry point.

The voice feature belongs on the existing Digital Twin UI, so this module
keeps the old import path without introducing a separate replacement grid.
"""

from digital_twin import render_digital_twin_page


def render_voice_twin() -> None:
    render_digital_twin_page()
