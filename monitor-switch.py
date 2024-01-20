#!/usr/bin/env python3

from os import read
from pathlib import Path
from subprocess import run
from dataclasses import dataclass
import re
from sys import prefix
from threading import current_thread
from typing import Self
import xdg

output_re = re.compile(
    r"^(?P<output>\S+) (?P<connected>connected|disconnected) (?P<primary>primary *)?(?:(?P<width>\d+)x(?P<height>\d+)\+(?P<x>\d+)\+(?P<y>\d+))?.*?(?:(?P<physx>\d+)mm x (?P<physy>\d+)mm)?$"
)
mode_re = re.compile(r"^\s+(?P<width>\d+)x(?P<height>\d+)")


@dataclass
class Mode:
    width: int
    height: int
    spec: str
    output: "Output"

    @property
    def dpi(self) -> tuple[float, float]:
        assert self.output.physx and self.output.physy
        return (
            self.width / (self.output.physx / 25.4),
            self.height / (self.output.physy / 25.4),
        )

    @property
    def preferred(self) -> bool:
        return "+" in self.spec

    @property
    def square(self) -> bool:
        dx, dy = self.dpi
        return abs(dx - dy) < 1

    @property
    def current(self) -> bool:
        return self.width == self.output.width and self.height == self.output.height

    def __str__(self) -> str:
        dx, dy = self.dpi
        square = "■" if self.square else " "
        current = "*" if self.current else " "
        preferred = "!" if self.preferred else " "
        return f"{current}{preferred} {self.width:>4d}x{self.height:<4d} {square} ({dx:2.0f}x{dy:2.0f} dpi)"


class Output:
    modes: list[Mode]

    def __init__(
        self,
        output: str,
        connected: bool | str,
        primary: str | None = None,
        width: str | int | None = None,
        height: str | int | None = None,
        x: str | int | None = None,
        y: str | int | None = None,
        physx: str | int | None = None,
        physy: str | int | None = None,
    ):
        self.output = output
        self.connected = (
            connected == "connected" if isinstance(connected, str) else bool(connected)
        )
        self.primary = bool(primary)
        self.width = int(width) if width else None
        self.height = int(height) if height else None
        self.x = int(x) if x or x == 0 else None
        self.y = int(y) if y or y == 0 else None
        self.physx = int(physx) if physx else None
        self.physy = int(physy) if physy else None
        self.modes = []


class AutorandrOption:
    virtual_configs = {
        "common": "Mirror using largest common resolution",
        "clone-largest": "Mirror using largest resolution",
        "horizontal": "Extend desktop horizontally",
        "vertical": "Extend desktop vertically",
        "off": "switch all displays off",
    }

    @classmethod
    def detected(cls, virtual=True) -> list[Self]:
        autorandr_proc = run(
            ["autorandr", "--detected"], capture_output=True, text=True, check=True
        )
        autorandr_options = autorandr_proc.stdout.splitlines()
        if virtual:
            autorandr_options.extend(cls.virtual_configs)
        return [cls(name) for name in autorandr_options]

    @staticmethod
    def read_config(name: str):
        filename = xdg.BaseDirectory.load_first_config(f"autorandr/{name}/config")
        if filename:
            return Path(filename).read_text()
        else:
            raise ValueError(f'No autorandr config for "{name}"')

    def __init__(self, name: str):
        self.name = name
        outputs = {}
        output = {}
        try:
            self.virtual = False
            for line in self.read_config(name).splitlines():
                try:
                    key, value = line.split(maxsplit=2)
                except ValueError:
                    key, value = line, True
                if key == "output":
                    output = {}
                    outputs[value] = output
                output[key] = value
        except ValueError:
            self.virtual = True
        self.outputs = outputs

    def activate(self):
        run(["autorandr", self.name])

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, AutorandrOption):
            return self.name == other.name
        elif isinstance(other, str):
            return self.name == other
        else:
            return False

    def __str__(self) -> str:
        return self.name

    def to_pango(self):
        if self.virtual:
            return f'<i>{self.name}</i>\t<span color="gray">{self.virtual_configs[self.name]}</span>'

        primary = [
            name
            for name, props in self.outputs.items()
            if props.get("primary") and not props.get("off")
        ]
        others = [
            name
            for name, props in self.outputs.items()
            if name not in primary and not props.get("off")
        ]
        output_str = ", ".join(
            '<span fgcolor="blue">{output}</span>: {mode} <span fgcolor="gray">({pos})</span>'.format_map(
                self.outputs[name]
            )
            for name in primary + others
        )
        return f"<b>{self.name}</b>\t{output_str}"


def list_():
    proc = run("xrandr --query", capture_output=True, text=True, shell=True, check=True)
    output = None
    outputs = []
    for line in proc.stdout.splitlines():
        if output_match := output_re.match(line):
            groups = output_match.groupdict()
            output = Output(**groups)
            outputs.append(output)
        elif (mode_match := mode_re.match(line)) and output is not None:
            mode = Mode(
                int(mode_match.group("width")),
                int(mode_match.group("height")),
                line,
                output,
            )
            output.modes.append(mode)

    for output in outputs:
        print(output.output)
        for mode in output.modes:
            print("   ", mode)


def main():
    """
    Die folgenden Optionen sollen angeboten werden:

    - Ausgabe von autorandr --detect
    - autorandr common
    - zwei Monitore:
        - 1920 rechts
        - 1920 links
        - 1920 mirror
    - drei Monitore:
        - docking-setup
        - extern klon rechts
        - extern klon links
    """
    autorandr_options = AutorandrOption.detected()
    formatted_options = "\n".join(option.to_pango() for option in autorandr_options)
    print(formatted_options)
    rofi_proc = run(
        [
            "rofi",
            "-dmenu",
            "-p",
            "AutoRandR mode",
            "-no-custom",
            "-format",
            "i",
            "-markup-rows",
        ],
        input=formatted_options,
        capture_output=True,
        text=True,
    )
    if rofi_proc.returncode == 0:
        mode_index = int(rofi_proc.stdout.strip())
        autorandr_options[mode_index].activate()


if __name__ == "__main__":
    main()
