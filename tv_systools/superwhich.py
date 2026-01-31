from __future__ import annotations
from abc import abstractmethod, ABC
from functools import cached_property
from importlib.metadata import Distribution, PackageMetadata
import shlex
import shutil
from textwrap import dedent
from os import fspath
from shutil import which
from pathlib import Path
import sys
from tkinter import Pack
from typing import Any, ClassVar, Mapping, cast
from rich import print
import magic
import json
from rich.table import Table
from rich.text import Text
import subprocess

from .util import first


def resolve_command(command: str) -> list[Path]:
    result: list[Path] = []
    path_ = which(command)
    if path_ is None:
        raise FileNotFoundError(command)
    path = Path(path_)
    result.append(path)
    while path.is_symlink():
        path = path.resolve()
        result.append(path)
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
        detail = ToolInfo.create(command, path) or getrel_info(path) or apt_info(path)
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
        paths = [fspath(p) for p in self.venv.glob("lib/*/site-packages")]
        for dist in Distribution.discover(path=paths):
            for _ in dist.entry_points.select(group="console_scripts", name=self.name):
                return dist
        raise ValueError(
            f"No distribution with script {self.name} found in {self.venv}"
        )

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


class Getrel1Info(ToolInfo):
    kind = "getrel"

    @property
    def applicable(self) -> bool:
        return "getrel" in self.path.parts

    @cached_property
    def _pd(self) -> Path:
        pd = self.path
        while not (pd.joinpath(".getrel")).exists():
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
