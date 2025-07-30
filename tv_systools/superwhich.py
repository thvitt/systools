import shlex
import shutil
from textwrap import dedent
from os import fspath
from shutil import which
from pathlib import Path
import sys
from typing import Mapping
from rich import print
import magic
import json
from rich.table import Table
from rich.text import Text
import subprocess

from .util import first
from .aptutils import Package


def main():
    if len(sys.argv) < 2:
        print("Usage: superwhich <command>")
        sys.exit(1)
    command = sys.argv[1]
    path_ = which(command)
    if path_:
        path = Path(path_)
        print(path.absolute())
        indent = 1
        while path.is_symlink():
            path = path.resolve()
            print(
                "  " * indent,
                "→",
                path.absolute(),
                "[red]✘[/red]" if not path.exists() else "",
            )
            indent += 1
        print("  " * indent, magic.from_file(path))
        detail = (
            pipx_info(path)
            or venv_info(path)
            or cargo_info(path)
            or getrel_info(path)
            or apt_info(path)
        )
        if detail:
            print(" " * indent, detail)

    else:
        print(f"Command '{command}' not found in PATH")


def load_json(json_file: Path) -> None | str | int | float | bool | dict | list:
    if json_file.exists():
        with json_file.open() as f:
            metadata = json.load(f)
        return metadata
    else:
        return None


def _md_table(title=None):
    return Table(
        show_edge=False,
        show_header=False,
        highlight=True,
        title=title,
    )


def cargo_info(path: Path):
    if ".cargo" not in path.parts:
        return None
    crates2 = load_json(path.parent.parent / ".crates2.json")
    if crates2 and isinstance(crates2, Mapping):
        for label, data in crates2.get("installs", {}).items():
            if path.name in data.get("bins", []):
                t = _md_table("Cargo Package")
                t.add_row("Commands", " ".join(data.get("bins", [])))
                t.add_row("Package", label)
                if version_req := data.get("version_req"):
                    t.add_row("Version Constraint", version_req)
                crate = label.split()[0]
                info = subprocess.run(
                    ["cargo", "info", "--color=always", crate],
                    capture_output=True,
                    text=True,
                    env={"FORCE_COLOR": "1"},
                ).stdout
                t.add_row("cargo info", Text.from_ansi(info))
                return t
    return f"[red]info for {path.name} not found in {path.parent.parent / '.crates2.json'}[/red]"


def pipx_info(path: Path):
    if "pipx" not in path.parts:
        return None
    venv = path.parent.parent
    pipx_metadata = venv / "pipx_metadata.json"
    metadata = load_json(pipx_metadata)
    if metadata:
        assert isinstance(metadata, Mapping)
        t = _md_table("pipx installed package")
        t.add_row("Command", path.name)
        t.add_row(
            "Package",
            f'{metadata["main_package"]["package"]} {metadata["main_package"]["package_version"]} ({metadata["python_version"]}), installed using pipx',
        )
        t.add_row("Virtual Environment", fspath(venv))
        t.add_row("Source", metadata["main_package"]["package_or_url"])
        t.add_row("Apps in Package", " ".join(metadata["main_package"]["apps"]))
        if metadata["injected_packages"]:
            t.add_row(
                "Injected Packages",
                " · ".join(
                    f"{d.get('package_or_url')} ({d.get("package_version")})"
                    for d in metadata["injected_packages"].values()
                ),
            )
        return t
    else:
        return f"[bold]{path.name}[/bold] ({path.parent.parent.name})"


def venv_info(path: Path):
    if not (
        path.parent.joinpath("pyvenv.cfg").exists()
        or path.parent.parent.joinpath("pyvenv.cfg").exists()
    ):
        return None

    with path.open() as f:
        shebang = f.readline()
    if shebang.startswith("#!"):
        python = shlex.split(shebang[2:])[0]
        cmd = dedent(f"""\
            from importlib.metadata import entry_points
            from json import dump
            from sys import stdout
            ep, = entry_points(group='console_scripts', name={path.name!r})
            scripts = [ep.name for ep in ep.dist.entry_points if ep.group == 'console_scripts']
            dump(dict(**ep.dist.metadata.json, scripts=scripts), stdout)""")
        proc = subprocess.run([python, "-c", cmd], capture_output=True, text=True)
        if proc.returncode == 0:
            metadata = json.loads(proc.stdout)
            t = _md_table("Python package in virtual environment")
            t.add_row("Package", metadata["name"])
            t.add_row("Version", metadata["version"])
            t.add_row("Summary", metadata["summary"])
            t.add_row("Other Binaries", " ".join(metadata["scripts"]))
            return t
    return None


def getrel_info(path: Path):
    getrel = shutil.which("getrel")
    if getrel is None:
        return None
    try:
        getrel_pd = first(
            parent for parent in path.parents if parent.joinpath(".getrel").exists()
        )
    except IndexError:
        return None

    proc = subprocess.run(
        [getrel, "status", "-cf", getrel_pd.name],
        capture_output=True,
        text=True,
        env={"FORCE_COLOR": "1"},
    )
    if proc.returncode == 0:
        return Text.from_ansi(proc.stdout)
    else:
        return None


def apt_info(path: Path):
    try:
        if path.relative_to(Path.home()):
            return None
    except ValueError:
        pass

    import apt

    package_name = _get_package_for(path)
    cache = apt.Cache()
    return Package(cache[package_name]).describe()


def _get_package_for(path: Path):
    if dlocate := shutil.which("dlocate"):
        proc = subprocess.run(
            [dlocate, "-F", fspath(path)],
            capture_output=True,
            text=True,
        )
    else:
        proc = subprocess.run(
            [shutil.which("dpkg-query") or "dpkg", "-S", fspath(path)],
            capture_output=True,
            text=True,
        )

    if proc.returncode != 0:
        raise FileNotFoundError(f"Package not found for {path}")

    for line in proc.stdout.splitlines():
        package, file = line.split(": ", 2)
        if path.samefile(file):
            return package

    raise FileNotFoundError(f"Package not found for {path} in {proc.stdout}")
