import logging
from rich.logging import RichHandler

from rich.console import Console


def configure_logging(
    console: Console | None = None,
    level: int = logging.WARNING,
    verbosity: int = 0,
    **kwargs,
) -> None:
    final_level = level - verbosity * 10
    logging.basicConfig(
        level=final_level,
        format="%(message)s",
        datefmt="%X",
        handlers=[
            RichHandler(console=console, **kwargs),
        ],
    )
