from typing import Annotated, Iterable, Sequence, TypeVar

import apt
from pzp import CustomAction, pzp
from pzp.input import get_char
from rich import get_console, inspect, print
from rich.progress import track
from rich.columns import Columns
from rich.text import Text
from rich.live import Live
from typer import Typer
from typing import Any
from .ui import pzp_table
from .aptutils import Package


app = Typer()
cache = apt.Cache()

T = TypeVar("T")


def key_menu(
    options: dict[str, T] | None = None, /, allow_escape=True, **kwargs: T
) -> T | None:
    if options is None:
        options = {}
    options.update(kwargs)

    prompt_ = []
    for key, option in options.items():
        option_str = str(option)
        if key in option_str:
            option_text = Text(option_str)
            option_text.highlight_regex(key, "bold underline")
        else:
            option_text = Text.from_markup(
                f"[bold underline]{key}[/bold underline]: {option_str}"
            )
        prompt_.append(option_text)

    live = Live(Columns(prompt_), transient=True)
    live.start()
    try:
        while key := get_char():
            if key in options:
                return options[key]
            if key == "\x1b" and allow_escape:
                return None
            else:
                print(key)
    finally:
        live.stop()
    return None


def console_capture(*args, **kwargs) -> str:
    console = get_console()
    with console.capture() as capture:
        console.print(*args, **kwargs)
    result = capture.get()
    if result.endswith("\n") and not args[-1].endswith("\n"):
        result = result[:-1]
    return result


def format_package(pkg: apt.Package):
    if pkg.is_upgradable:
        icon = "↑"
    elif pkg.is_installed:
        icon = "✓"
    else:
        icon = " "
    version = pkg.candidate or pkg.installed or list(pkg.versions)[0]
    return f"{icon} {pkg.name:20}\t{version.summary}"


def select_package(packages: Sequence[Package], input: str = "") -> Package | None:
    console = get_console()
    try:
        # return pzp_table(packages)
        return pzp(
            packages,
            fullscreen=False,
            height=console.height - 10,
            lazy=True,
            input=input,
            layout="reverse",
            prompt_str=console_capture(
                "[bold]⏎[/bold] details • [bold]^i[/bold] install • [bold]^u[/bold] upgrade • [bold]^r[/bold] remove • [bold]Esc[/bold] back [bold green]>[/bold green] ",
                highlight=False,
            ),
            keys_binding={
                "install": ["ctrl-i"],
                "upgrade": ["ctrl-u"],
            },
        )
    except CustomAction as action:
        inspect(action)


@app.command()
def search(package: str = ""):
    console = get_console()
    _packages = track(
        map(Package, cache),
        description="Loading package info",
        transient=True,
        total=len(cache),
    )
    packages = {pkg.name: pkg for pkg in _packages if pkg.simple}
    while selected := select_package(packages.values(), input=package):
        print(selected.describe())
        option = key_menu(i="install", u="upgrade", q="back")
        print(option)
