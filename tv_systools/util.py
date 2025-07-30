import logging
from types import EllipsisType
from typing import Iterable, TypeVar, overload
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


T = TypeVar("T")
S = TypeVar("S")


@overload
def first(iterable: Iterable[T], /, default: EllipsisType = ...) -> T: ...


@overload
def first(iterable: Iterable[T], /, default: S) -> T | S: ...


def first(iterable: Iterable[T], /, default: EllipsisType | S = ...) -> T | S:
    """Return the first item in an iterable, or a default value if the iterable is empty."""
    try:
        return next(iter(iterable))
    except StopIteration:
        if default == ...:
            raise IndexError("first() was called on an empty iterable")
        return default
