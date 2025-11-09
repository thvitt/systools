from os import PathLike
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Annotated, Generator, Optional
from zipfile import ZipFile
from cyclopts import App, Parameter, validators
from rich import print

from lxml import html, etree

app = App()


class HtmlSource:
    def __init__(self, *urls: str | Path | PathLike):
        self.paths = [Path(url) for url in urls]

    def find_existing_files(
        self,
    ) -> Generator[tuple[etree.ElementBase, str, Path], None, None]:
        parser = html.HTMLParser(recover=True)
        for path in self.paths:
            try:
                tree = html.parse(path, parser=parser)
                for el in tree.iter():
                    for name, value in el.items():
                        try:
                            if value:
                                p = path.parent / value
                                if p.exists():
                                    yield el, name, p
                        except IOError:
                            pass
            except IOError as e:
                print(f"[yellow]WARNING:[/yellow] Error parsing {path}: {e}", file=sys.stderr)
                pass  # non-html files are just ignored

    def zip(
        self,
        target: Path | None = None,
        stdin: str | None = None,
        ignore_missing: bool = True,
    ):
        if target is None:
            target = self.paths[0].with_suffix(".zip")
        with ZipFile(
            target, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as z:
            if stdin:
                z.writestr(stdin, sys.stdin.read())
            assets = set()
            for path in self.paths:
                if ignore_missing and not path.exists():
                    continue
                z.write(path)
                assets |= {asset for el, attrib, asset in self.find_existing_files()}
            for asset in assets:
                if ignore_missing and not asset.exists():
                    continue
                z.write(asset)

    def copy(self, target: Path):
        for path in self.paths:
            if target.is_dir():
                target = target / path.name
                shutil.copy2(path, target)
            for el, attrib, asset in self.find_existing_files():
                relpath: Path = asset.relative_to(self.paths[0])
                target_path = target / relpath
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(asset, target_path)


@app.command("zip")
def zip_(
    html_files: Annotated[list[Path], Parameter(validator=validators.Path(exists=True, dir_okay=False))],
    output: Annotated[ Optional[Path], Parameter(validator=validators.Path(dir_okay=False)) ] = None,
    stdin: Annotated[ Optional[str], Parameter(alias=["-i"]), ] = None,
    ignore_missing: Annotated[
        bool,
        Parameter(alias=["-m"])
    ] = False,
):
    """
    Creates a ZIP file from the given HTML files and the ressources they need.

    Args:
        html_files: The HTML files to include in the ZIP file.
        output: The output ZIP file. If not provided, the first HTML file's name with a .zip extension will be used.
        stdin: If provided, the contents of stdin will be written to a file with this name.
        ignore_missing: if true, don’t complain about missing files
    """
    source = HtmlSource(*html_files)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
    source.zip(output, stdin=stdin, ignore_missing=ignore_missing)


@app.command()
def copy(html_files: list[Path], target: Path):
    if len(html_files) > 1 and not target.is_dir():
        print(
            f"[red]Error:[/red] When passing multiple input files, the target ({target} must be a directory.",
            file=sys.stderr
        )
        return 1
    for source in html_files:
        HtmlSource(source).copy(target)
