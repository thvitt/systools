import plistlib
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from cyclopts import App, Parameter
from cyclopts.types import ExistingPath
from rich.console import Console

app = App(help="Read and write macOS .webloc files (URL shortcuts).")
console = Console()


@app.command
def write(
    url: str,
    path: Path | None = None,
    /,
    *,
    title: Annotated[str | None, Parameter(alias="-t")] = None,
):
    """
    Write a .webloc file that links to the given URL.

    Args:
        url: The URL to store in the .webloc file.
        path: Output file or directory. If omitted or a directory, the
            filename is derived from title or the URL's host.
        title: Filename stem to use when path is omitted or a directory.
    """
    if path is None:
        path = Path.cwd()
    if path.is_dir():
        stem = title or urlsplit(url).netloc or "link"
        path = path / f"{stem}.webloc"
    elif path.suffix != ".webloc":
        path = path.with_suffix(".webloc")

    with path.open("wb") as webloc_file:
        plistlib.dump({"URL": url}, webloc_file)
    console.print(f"Wrote [link={url}]{url}[/link] to {path}")


@app.command
def read(files: list[ExistingPath], /):
    """
    Print the URL stored in one or more .webloc files.

    Args:
        files: The .webloc file(s) to read.
    """
    show_filename = len(files) > 1
    for file in files:
        with file.open("rb") as webloc_file:
            url = plistlib.load(webloc_file)["URL"]
        if show_filename:
            console.print(f"{file}: [link={url}]{url}[/link]")
        else:
            console.print(url)
