import logging
import os
from pathlib import Path
from subprocess import CalledProcessError, Popen
import subprocess
import sys
from types import EllipsisType
from typing import Iterable, Literal, TypeVar, overload
from rich import get_console
from rich.logging import RichHandler

from rich.console import Console


def logging_to_journald() -> bool:
    journal_stream = os.getenv("JOURNAL_STREAM", "")
    if journal_stream:
        dev, inode = map(int, journal_stream.split(":", 1))
        stat = os.stat(sys.stderr.fileno())
        return stat.st_ino == inode and stat.st_dev == dev
    else:
        return False


def configure_logging2(
    *,
    console: Console | None = None,
    default_level: int = logging.WARNING,
    verbosity: int = 0,
    quietness: int = 0,
    loud_core_loggers: list[str] | None = None,
    **kwargs,
) -> None:
    """
    Configure logging with sensible defaults.

    If running as systemd service, we simply log to the journal. If we
    are running on the console, we log to a RichHandler.

    console: The console to use. By default, a stderr console.
    default_level: the logging level to use as base for calculation with the following options.
    verbosity: levels to increase verbosity, i.e., number of '-v' options on command line
    quietness: levels to decrease verbosity, i.e., number of '-q' options on command line.
    loud_core_loggers: If present, use a different calculation method for the given loggers
        and all others: -v means core loggers are INFO and others WARNING, -vv both INFO, -vvv core DEBUG and others INFO etc.
    """
    handlers = []
    if logging_to_journald():
        try:
            from systemd.journal import JournalHandler

            handlers.append(JournalHandler(SYSLOG_IDENTIFIER=Path(sys.argv[0]).stem))
        except ImportError:
            handlers.append(logging.StreamHandler())
    else:
        if console is None:
            console = Console(stderr=True)
        handler = RichHandler(console=console, **kwargs)
        handler.setFormatter(logging.Formatter("%(message)s", datefmt="%X"))
        handlers.append(handler)

    verbosity -= quietness
    if loud_core_loggers:
        log_level = default_level - (verbosity // 2) * 10
        loud_level = default_level - ((verbosity + 1) // 2 * 10)
    else:
        log_level = loud_level = default_level - verbosity * 10
    root_logger = logging.getLogger()
    root_logger.handlers.extend(handlers)
    root_logger.setLevel(log_level)
    for loud in loud_core_loggers or []:
        logger = logging.getLogger(loud)
        logger.setLevel(loud_level)


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


class CWD:
    """
    Context manager for changing the current working directory.

    Attributes:
        old_cwd: original working directory while creating the CWD object
        cwd: Working directory while context manager is active
    """

    old_cwd: Path
    cwd: Path

    def __init__(
        self, path: Path | str, /, *, resolve: bool = False, create: bool = True
    ) -> None:
        path_ = Path(path)
        self.cwd = path_.resolve() if resolve else path_
        self.old_cwd = Path.cwd()
        if create and not self.cwd.exists():
            self.cwd.mkdir(parents=True, exist_ok=True)
        if not self.cwd.is_dir():
            raise NotADirectoryError(f"{self.cwd} is not a directory")

    def __enter__(self) -> Path:
        os.chdir(self.cwd)
        return self.cwd

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        os.chdir(self.old_cwd)


def run_pipe(
    *cmd, cwd=None, strip: bool | Literal["auto"] = "auto", input=None, text=True
) -> str:
    """
    Conveniance function to run a command and capture its output as a string.

    Args:
        *cmd: executable and its arguments, either as multiple arguments or a single list/tuple

        cwd: optional working directory for the command
        input: if present, a string to send to the command's standard input
        text: if False, return bytes instead of str
        strip: if True, remove a trailing newline from the output;
            if "auto", remove trailing newline only if the output contains no other newlines

    Returns:
        the command output as a string

    Raises:
        CalledProcessError: if the command exits with a non-zero status
        OSError: if the command cannot be executed
    """
    if len(cmd) == 1 and isinstance(cmd[0], (list, tuple)):
        cmd = list(cmd[0])
    else:
        cmd = list(cmd)

    logging.getLogger(__name__).debug("Running command: %s", cmd)
    proc = subprocess.run(
        cmd, input=input, capture_output=True, text=text, cwd=cwd, check=True
    )
    result = proc.stdout
    if strip == "auto":
        strip = "\n" not in result[:-1]
    if strip and result and result[-1] == "\n":
        result = result[:-1]
    logging.getLogger(__name__).debug("Command output: %s", result)
    return result


def display_path(path: Path | str) -> str:
    """
    converts the given path to the shortest string representation, be it absolute, relative to the current working directory, or relative to ~.
    """

    if isinstance(path, str):
        path = Path(path)
    cand = [path]
    try:
        cand.append(path.relative_to(Path.cwd(), walk_up=True))
    except ValueError:
        pass

    try:
        cand.append("~" / path.relative_to(Path.home(), walk_up=True))
    except ValueError:
        pass
    return min(map(str, cand), key=len)
