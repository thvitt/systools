import shlex
from subprocess import run
from typing import Literal, Self, Sequence, TypeVar

import apt
from cyclopts import App
from pzp import CustomAction
from pzp.exceptions import AbortAction, AcceptAction
from pzp.finder import Finder
from pzp.input import get_char
from rich import get_console, print
from rich.columns import Columns
from rich.console import Console
from rich.live import Live
from rich.progress import track
from rich.syntax import Syntax
from rich.text import Text

from .aptutils import Package

app = App()
app.register_install_completion_command(add_to_startup=False)
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


class AptSearch:
    console: Console
    packages: Sequence[Package]
    input: str
    install: set[Package]
    remove: set[Package]

    def __init__(
        self,
        packages: Sequence[Package],
        input: str = "",
        parent: Self | None = None,
    ):
        self.packages = packages
        self.input = input
        self.console = get_console()
        if parent is None:
            self.install = set()
            self.remove = set()
        else:
            self.install = parent.install
            self.remove = parent.remove

    def mark(self, package: Package, action: Literal["install", "remove"]):
        if action == "install":
            mark, unmark = self.install, self.remove
        else:
            mark, unmark = self.remove, self.install
        mark.add(package)
        if package in unmark:
            unmark.remove(package)

    def select(self, lines_before=10):
        finder = Finder(
            self.packages,
            fullscreen=False,
            height=self.console.height - lines_before,
            lazy=False,
            layout="reverse",
            prompt_str=console_capture(
                "[bold]⏎[/bold] details • [bold]^i[/bold] install • [bold]^r[/bold] remove • [bold]Esc[/bold] back [bold green]>[/bold green] ",
                highlight=False,
            ),
            keys_binding={
                "install": ["ctrl-i"],
                "remove": ["ctrl-r"],
            },
        )
        while True:
            try:
                finder.show(
                    self.input
                )  # TODO: do we get the selection number from somewhere?
            except CustomAction as action:
                self.input = action.line or ""
                self.mark(action.selected_item, action.action)  # pyright: ignore[reportArgumentType]
            except AcceptAction as action:
                self.input = action.line or ""
                self.showpkg(action.selected_item)
            except AbortAction:
                break

    def showpkg(self, package: Package):
        description = package.describe()
        print(description)
        related = package.related()
        if related:
            AptSearch(related, parent=self).select(
                lines_before=len(self.console.render_lines(description)) + 2
            )  # TODO: Add install/remove option
        else:
            option = key_menu(i="install", r="remove", q="back")
            if option == "install" or option == "remove":
                self.mark(package, option)

    def commit(self):
        cmd = ["sudo", "apt"]
        if self.install:
            cmd.append("install")
            cmd.extend(pkg.name for pkg in self.install)
            cmd.extend(pkg.name + "-" for pkg in self.remove)
        elif self.remove:
            cmd.append("remove")
            cmd.extend(pkg.name for pkg in self.remove)
        else:
            return  # nothing to do
        self.console.print(Syntax(shlex.join(cmd), "shell"))
        proc = run(cmd)
        if proc.returncode == 0:
            self.install.clear()
            self.remove.clear()


@app.default
def search(package: str = ""):
    _packages = track(
        map(Package, cache),
        description="Loading package info",
        transient=True,
        total=len(cache),
    )
    packages = [pkg for pkg in _packages if pkg.simple]
    aps = AptSearch(packages, package)
    aps.select()
    aps.commit()
