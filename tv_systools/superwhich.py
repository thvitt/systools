from __future__ import annotations

import json
import os
import shutil
import subprocess
import tomllib
from abc import ABC, abstractmethod
from functools import cached_property
from importlib.metadata import Distribution, PackageMetadata
from os import environ, fspath
from os.path import expanduser
from pathlib import Path
from random import sample
from shutil import which
from stat import S_IXUSR, filemode
from typing import Annotated, Any, ClassVar, Iterable, cast

import magic
from cyclopts import App, Group, Parameter
from cyclopts.types import PositiveInt
from cyclopts.validators import mutually_exclusive
from rich.console import Console
from rich.progress import track
from rich.table import Column, Table

app = App()
app.register_install_completion_command(add_to_startup=False)


console = Console()
print = console.print


class CommandNotFoundError(FileNotFoundError):
    """
    When a command cannot be resolved, there can be various reasons:

    - There is no file of that name in the $PATH
    - The file of that name is not executable
    - Some link in the link chain is broken
    - Recursive loop in the link chain
    """

    def __init__(self, command) -> None:
        non_executable = which(command, mode=0)
        if non_executable:
            return super(Exception, self).__init__(
                f"{non_executable} is not executable"
            )
        else:
            paths = [Path(p) for p in os.getenv("PATH", "").split(os.pathsep)]
            for path in paths:
                file = path.joinpath(command)
                if file.is_symlink():
                    link, target = self.find_broken_symlink(file)
                    if isinstance(target, Path):
                        return super(Exception, self).__init__(
                            f"Broken link: {link} -> {target}"
                        )
                    elif isinstance(target, Iterable):
                        return super(Exception, self).__init__(
                            f"Symlink cycle: {' -> '.join(target)}"
                        )
                elif file.exists(follow_symlinks=False):
                    return super(Exception, self).__init__(
                        f"{file} ({filemode(file.stat().st_mode)}) not a file"
                    )
        return super(Exception, self).__init__(f"Command {command} not found.")

    @staticmethod
    def find_broken_symlink(link: Path, seen: list[Path] | None = None):
        if seen is None:
            seen = list()
        elif link.absolute() in seen:
            return link, seen
        else:
            seen.append(link)

        target = link.readlink()
        if target.is_symlink():
            return CommandNotFoundError.find_broken_symlink(target, seen)
        else:
            return link, target


class SymlinkNotResolvedError(FileNotFoundError):
    def __init__(self, symlink: Path) -> None:
        self.symlink = symlink
        super(Exception, self).__init__(
            f"Broken symlink:{symlink}->{symlink.readlink()}"
        )


def resolve_command(command: str | Path) -> list[Path]:
    result: list[Path] = []
    path_ = which(command)
    if path_ is None:
        raise CommandNotFoundError(command)
    path = Path(path_)
    result.append(path)
    while path.is_symlink():
        try:
            path = path.resolve()
            result.append(path)
        except FileNotFoundError as e:
            raise SymlinkNotResolvedError(path) from e
    return result


class ToolInfo(ABC):
    name: str
    path: Path
    kind: str = "?"

    _subclasses: ClassVar[list[type[ToolInfo]]] = []

    def __init__(self, name: str, resolved_path: Path) -> None:
        """
        Create a new TooolInfo object.

        Args:
            name: Command name
            resolved_path: the fully resolved path tot he command

        """
        self.name = name
        self.path = resolved_path

    @property
    @abstractmethod
    def applicable(self) -> bool:
        """Is this tool info kind applicable to the current path?"""

    @property
    @abstractmethod
    def package(self) -> str:
        """The package name."""

    @property
    def version(self) -> str:
        """The package version, if applicable"""
        return ""

    @property
    @abstractmethod
    def summary(self) -> str:
        """Short (one-line) package description"""

    @property
    def extra_bins(self) -> list[str]:
        """Additional binaries in the package"""
        return []

    @property
    def extra(self) -> dict[str, str]:
        """Additional, kind specific metadata"""
        return {}

    def __init_subclass__(cls) -> None:
        cls._subclasses.append(cls)
        return super().__init_subclass__()

    @classmethod
    def create(cls, command: str, resolved_path: Path | None = None):
        if resolved_path is None:
            resolved_path = resolve_command(command)[-1]
        for subclass in reversed(cls._subclasses):
            info = subclass(command, resolved_path)
            if info.applicable:
                return info

    def __rich__(self):
        table = _md_table(f"{self.kind} Package [bold]{self.package}[/bold]")
        table.add_row("Package", self.package)
        if self.version:
            table.add_row("Version", self.version)
        table.add_row("Summary", self.summary)
        if self.extra_bins:
            table.add_row("Binaries", " ".join(self.extra_bins))
        for key, value in self.extra.items():
            table.add_row(key, str(value), style="dim")
        return table


def print_detailed_info(command: str | Path) -> None:
    print(command)
    try:
        paths = resolve_command(command)
        for indent, path in enumerate(paths):
            print(" " * indent, "→" if indent else "", path.absolute())
        print(magic.from_file(paths[-1]), style="dim")
        detail = ToolInfo.create(command, paths[-1])
        if detail:
            print(detail)
    except OSError as e:
        print(f"[red]{e}[/red]")


def print_command_table(commands: Iterable[str | Path], quiet: bool = False) -> None:
    table = Table(
        Column("Command", style="bold"),
        Column("Package", style="cyan"),
        Column("Kind", style="dim"),
        "Summary",
        "Path",
        show_edge=False,
        show_header=not quiet,
        box=None,
        highlight=True,
    )

    for command_ in track(commands, transient=True, disable=quiet):
        command = Path(command_).name
        try:
            path = resolve_command(command_)[-1]
            try:
                if path:
                    info = ToolInfo.create(command, path)
                    if info:
                        table.add_row(
                            command, info.package, info.kind, info.summary, str(path)
                        )
                    else:
                        table.add_row(command, "", "", magic.from_file(path), str(path))
                else:
                    table.add_row(command, "", "", "", "command not found", style="red")
            except Exception as e:
                table.add_row(command, "", "", str(e), fspath(path), style="red")
        except Exception as e:
            table.add_row(command, "", "", str(e), style="red")
    print("\r", table, sep="")


@app.default
def main(
    commands: list[str],
    /,
    *,
    detailed: Annotated[
        bool | None, Parameter(alias="-d", negative=["-t", "--table"])
    ] = None,
):
    """
    Find the given command or commands in the $PATH, resolve symlinks and show information about them.

    Args:
        commands: One or more commands. Aliases and shell functions are not recognized.
        detailed: Show a verbose info block for the given command or a summary table with one line per command. By default, a  summary table will be shown if more than one commands are given.
    """
    if detailed is None:
        detailed = len(commands) == 1

    if detailed:
        for command in commands:
            print_detailed_info(command)
    else:
        print_command_table(commands)


def commands_in(paths: list[Path]) -> Iterable[Path]:
    seen = set()
    for path in paths:
        if path.is_dir():
            for cmd in path.iterdir():
                if (
                    cmd.name not in seen
                    and cmd.is_file()
                    and cmd.stat().st_mode & S_IXUSR
                ):
                    seen.add(cmd)
                    yield cmd


def bin_dirs(only_home: bool = False) -> list[Path]:
    paths = [Path(expanduser(p)) for p in environ["PATH"].split(os.pathsep)]
    if only_home:
        return [p for p in paths if p.is_relative_to(Path.home())]
    else:
        return paths


display_mode = Group("Display Mode", validator=mutually_exclusive)


@app.command(name=["-l", "--list"])
def list_commands(
    n: PositiveInt | None = None,
    /,
    *,
    home: Annotated[bool, Parameter(alias="-H")] = False,
    detailed: Annotated[bool, Parameter(alias="-d")] = False,
    bare: Annotated[bool, Parameter(alias="-b")] = False,
    quiet: Annotated[bool, Parameter(alias="-q")] = False,
):
    """
    Lists commands from $PATH.

    By default, a table of all commands on $PATH will be shown.

    Args:
        n: Number of commands to sample. If missing, list all commands.
        home: Only look in directories on the $PATH and below $HOME.
        detailed: Show a detailed info block for each command.
        bare: Only list the command name, nothing else.
        quiet: Do not show progress bar or headers.
    """
    dirs = bin_dirs(home)
    if n:
        cmds = sample(list(commands_in(dirs)), n)
    else:
        cmds = commands_in(dirs)

    if bare:
        print(*(cmd.name for cmd in cmds), sep="\n")
    elif detailed:
        for cmd in cmds:
            print_detailed_info(cmd)
    else:
        print_command_table(list(cmds), quiet=quiet)


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


class CargoInfo(ToolInfo):
    kind = "Cargo"

    @property
    def applicable(self) -> bool:
        return ".cargo" in self.path.parts

    @property
    def package(self) -> str:
        return self._crate2_info["crate"]

    @property
    def version(self) -> str:
        return self._cargo_info["version"]

    @property
    def summary(self) -> str:
        return self._cargo_info["summary"]

    @property
    def extra_bins(self) -> list[str]:
        bins = cast(list[str], self._cargo_info.get("bins", []))
        try:
            bins.remove(self.name)
        except ValueError:
            pass
        return bins

    @property
    def extra(self) -> dict[str, str]:
        return {
            k: v
            for k, v in (self._crate2_info | self._cargo_info).items()
            if v and k not in {"bins", "crate", "summary", "version"}
        }

    @cached_property
    def _crate2_info(self) -> dict[str, str]:
        crates2_path = self.path.parent.parent / ".crates2.json"
        crates2 = load_json(crates2_path)
        if crates2 and isinstance(crates2, dict):
            for label, data in crates2.get("installs", {}).items():
                if self.path.name in data.get("bins", []):
                    data["label"] = label
                    data["crate"] = label.split()[0]
                    return data
            raise ValueError(f"Entry for {self.path.name} not found in {crates2_path}")
        else:
            raise OSError(f"Failed to load {crates2_path}")

    @cached_property
    def _cargo_info(self):
        answer = subprocess.run(
            ["cargo", "info", "--color=never", self.package],
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        result = {
            "package": answer[0],
            "summary": answer[1],
        }
        for line in answer[2:]:
            if line and line[0].isalnum():
                key, value = line.split(":", maxsplit=1)
                if key and value:
                    result[key.strip()] = value.strip()
        return result


class VEnvInfo(ToolInfo):
    kind = "Python VEnv"

    @property
    def venv(self):
        for cand in self.path.parent, self.path.parent.parent:
            if cand.joinpath("pyvenv.cfg").exists():
                return cand
        raise ValueError(f"{self.path} is not in a VEnv")

    @property
    def applicable(self) -> bool:
        try:
            return bool(self.venv)
        except ValueError:
            return False

    @cached_property
    def _distribution(self) -> Distribution:
        cmd = self.path.name
        paths = self.venv.glob("lib/*/site-packages")
        for distpath in paths:
            for dist in Distribution.discover(path=[fspath(distpath)]):
                for _ in dist.entry_points.select(group="console_scripts", name=cmd):
                    return dist
                # if it’s not a script entry point, it might be a file directly, e.g., from the scripts.
                for file in dist.files or []:
                    if distpath.joinpath(file).resolve().samefile(self.path):
                        return dist
        raise ValueError(f"No distribution with script {cmd} found in {self.venv}")

    @cached_property
    def package_metadata(self) -> PackageMetadata:
        return self._distribution.metadata

    @property
    def summary(self) -> str:
        return self.package_metadata.get("summary") or ""

    @property
    def package(self) -> str:
        return self.package_metadata.get("name") or ""

    @property
    def version(self) -> str:
        return self.package_metadata.get("version") or ""

    @property
    def extra_bins(self) -> list[str]:
        return [
            ep.name
            for ep in self._distribution.entry_points.select(group="console_scripts")
        ]

    @property
    def extra(self) -> dict[str, str]:
        return {"VEnv": fspath(self.venv)}


class PipxInfo(VEnvInfo):
    kind = "pipx"

    @property
    def applicable(self) -> bool:
        return "pipx" in self.path.parts

    @property
    def venv(self):
        return self.path.parent.parent

    @cached_property
    def _pipx_metadata(self):
        pipx_metadata = self.venv / "pipx_metadata.json"
        metadata = load_json(pipx_metadata)
        assert isinstance(metadata, dict)
        return metadata

    @property
    def package(self) -> str:
        return self._pipx_metadata["main_package"]["package"]

    @property
    def extra_bins(self) -> list[str]:
        return self._pipx_metadata["main_package"]["apps"]

    @property
    def extra(self) -> dict[str, str]:
        metadata = {
            "VEnv": fspath(self.venv),
            "Source": self._pipx_metadata["main_package"]["package_or_url"],
        }
        if self._pipx_metadata["injected_packages"]:
            metadata["Injected Packages"] = " · ".join(
                f"{d.get('package_or_url')} ({d.get('package_version')})"
                for d in metadata["injected_packages"].values()
            )
        return metadata


class UvToolInfo(VEnvInfo):
    kind = "uv tool"

    @property
    def applicable(self) -> bool:
        if "uv" in self.path.parts:
            try:
                return bool(self.receipt)
            except OSError:
                return False
        return False

    @cached_property
    def receipt(self) -> dict[str, Any]:
        path = self.path
        while path and path != path.parent:
            tomlpath = path.joinpath("uv-receipt.toml")
            if tomlpath.exists():
                with tomlpath.open("rb") as t:
                    return tomllib.load(t)
            path = path.parent
        raise FileNotFoundError(
            f"uv-receipt.toml not found in a parent dir of {self.path}"
        )

    @property
    def extra_bins(self) -> list[str]:
        return [
            ep["name"]
            for ep in self.receipt.get("tool", {}).get("entrypoints", [])
            if "name" in ep
        ]

    @property
    def extra(self) -> dict[str, str]:
        data = super().extra

        def fmt_entry(entry: Any) -> str:
            parts = []
            if isinstance(entry, dict):
                if "name" in entry:
                    parts.append(str(entry["name"]))
                for k, v in entry.items():
                    if k != "name":
                        parts.append(f"{k}={v}")
            elif isinstance(entry, list):
                parts = [fmt_entry(part) for part in entry]
            else:
                return str(entry)

            if any(", " in part for part in parts):
                return "\n".join(parts)
            else:
                return ", ".join(parts)

        for key, value in self.receipt.get("tool", {}).items():
            if key == "entrypoints":
                continue
            if value:
                data[key] = fmt_entry(value)

        return data


class Getrel1Info(ToolInfo):
    kind = "getrel"

    @property
    def applicable(self) -> bool:
        return "getrel" in self.path.parts

    @cached_property
    def _pd(self) -> Path:
        pd = self.path
        while not (pd.joinpath(".getrel")).exists():
            if pd == pd.parent:
                raise FileNotFoundError(f"{self.path} has no getrel info")
            pd = pd.parent
        return pd

    @cached_property
    def _getrel_state(self) -> dict[str, Any]:
        return cast(dict[str, Any], load_json(self._pd / ".getrel/state.json"))

    @property
    def version(self) -> str:
        return self._getrel_state["installed"]["version"]

    @property
    def package(self) -> str:
        return self._pd.name

    @property
    def summary(self) -> str:
        return ""

    @property
    def extra_bins(self) -> list[str]:
        local_bin = Path.home().joinpath(".local", "bin")
        return [
            path.name
            for path in map(Path, self._getrel_state["installed_files"])
            if path.is_relative_to(local_bin)
        ]


class AptInfo(ToolInfo):
    kind = "Debian"

    @property
    def applicable(self):
        if self.path.is_relative_to(Path.home()):
            return False
        try:
            return bool(self.package)
        except Exception:
            return False

    @cached_property
    def _package_name(self):
        if dlocate := shutil.which("dlocate"):
            proc = subprocess.run(
                [dlocate, "-F", fspath(self.path)],
                capture_output=True,
                text=True,
            )
        else:
            proc = subprocess.run(
                [shutil.which("dpkg-query") or "dpkg", "-S", fspath(self.path)],
                capture_output=True,
                text=True,
            )

        if proc.returncode != 0:
            raise FileNotFoundError(f"Package not found for {self.path}")

        for line in proc.stdout.splitlines():
            package, file = line.split(": ", 2)
            if self.path.samefile(file):
                return package

        raise FileNotFoundError(f"Package not found for {self.path} in {proc.stdout}")

    @property
    def package(self) -> str:
        return self._package_name

    @cached_property
    def _package(self):
        import apt

        from .aptutils import Package

        cache = apt.Cache()
        return Package(cache[self.package])

    @property
    def version(self) -> str:
        return str(self._package.version.version)

    @property
    def summary(self) -> str:
        return self._package.summary or ""

    @property
    def extra(self) -> dict[str, str]:
        fields = {k: str(v) for k, v in self._package.extradata.items()}
        fields["Description"] = self._package.version.description
        return fields
