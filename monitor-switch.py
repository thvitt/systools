#!/usr/bin/env python3

from enum import Enum
from os import read
from pathlib import Path
from subprocess import run
from dataclasses import dataclass
import re
from sys import prefix
from threading import current_thread
from typing import Self
import xdg
from copy import copy
from time import sleep

output_re = re.compile(
    r"^(?P<output>\S+) (?P<connected>connected|disconnected) (?P<primary>primary *)?(?:(?P<width>\d+)x(?P<height>\d+)\+(?P<x>\d+)\+(?P<y>\d+))?.*?(?:(?P<physx>\d+)mm x (?P<physy>\d+)mm)?$"
)
mode_re = re.compile(r"^\s+(?P<width>\d+)x(?P<height>\d+)")


class Relation(Enum):
    SAME_AS = "--same-as"
    LEFT_OF = "--left-of"
    RIGHT_OF = "--right-of"
    ABOVE = "--above"
    BELOW = "--below"


@dataclass
class Mode:
    width: int
    height: int
    spec: str
    output: "Output"
    relation: None | tuple[Relation, "Output"] = None

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

    def distance(self, other) -> int:
        try:
            w, h = other.width, other.height
        except AttributeError:
            w, h = other
        return abs(self.width - w) + abs(self.height - h)

    def __eq__(self, __value: object) -> bool:
        try:
            return self.distance(__value) == 0
        except ValueError | TypeError:
            return False

    def with_relation(self, relation: Relation, output: "Output") -> Self:
        result = copy(self)
        result.relation = (relation, output)
        return result

    def cmdline(self) -> list[str]:
        result = ["--output", self.output.name, "--mode", f"{self.width}x{self.height}"]
        if self.relation is not None:
            result.extend([self.relation[0].value, self.relation[1].name])
        return result


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
        self.name = output
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

    @property
    def on(self) -> bool:
        return self.connected and self.x is not None

    @property
    def icon(self) -> str:
        if not self.connected:
            return "󱐤"
        elif self.primary:
            return "󰎤"
        elif self.on:
            return ""
        else:
            return ""

    def __str__(self) -> str:
        result = f"{self.icon}  {self.name}"
        if self.width:
            result += f" ({self.width}x{self.height})"
        return result

    def matching_mode(self, other, *, square=False):
        if square:
            modes = [mode for mode in self.modes if mode.square]
        else:
            modes = self.modes
        return copy(min(modes, key=lambda mode: mode.distance(other)))


class XRandrOption:
    @classmethod
    def suggested(cls, preference=(1920, 1200)):
        outputs = xrandr_config()
        connected = [output for output in outputs if output.connected]
        match connected:
            case [single]:
                return [cls(single.matching_mode(preference))]
            case [primary, secondary]:
                primary_mode = primary.matching_mode(preference)
                secondary_mode = secondary.matching_mode(primary_mode)
                return [
                    cls(
                        primary_mode,
                        secondary_mode.with_relation(
                            Relation.RIGHT_OF, primary_mode.output
                        ),
                    ),
                    cls(
                        primary_mode,
                        secondary_mode.with_relation(
                            Relation.LEFT_OF, primary_mode.output
                        ),
                    ),
                    cls(
                        primary_mode,
                        secondary_mode.with_relation(
                            Relation.SAME_AS, primary_mode.output
                        ),
                        label="Mirror",
                    ),
                ]
            case [primary, secondary, tertiary]:
                primary_mode = primary.matching_mode(preference)
                secondary_mode = secondary.matching_mode(primary_mode)
                tertiary_mode = tertiary.matching_mode(secondary_mode)
                return [
                    cls(
                        primary_mode,
                        secondary_mode.with_relation(
                            Relation.RIGHT_OF, tertiary_mode.output
                        ),
                        tertiary_mode.with_relation(
                            Relation.ABOVE, primary_mode.output
                        ),
                        label="Docking",
                    ),
                    cls(
                        primary_mode,
                        secondary_mode.with_relation(
                            Relation.RIGHT_OF, primary_mode.output
                        ),
                        tertiary_mode.with_relation(
                            Relation.SAME_AS, secondary_mode.output
                        ),
                    ),
                ]
            case _:
                raise ValueError("Only 1-3 connected outputs are supported")

    def __init__(self, *modes: Mode, label: str | None = None) -> None:
        self.modes = list(modes)
        for i in range(1, len(modes)):
            if self.modes[i].relation is None:
                self.modes[i] = self.modes[i].with_relation(
                    Relation.RIGHT_OF, self.modes[i - 1].output
                )
        self.label = label

    def activate(self):
        cmdline = ["xrandr"]
        for mode in self.modes:
            cmdline.extend(mode.cmdline())
        run(cmdline)

    def to_pango(self):
        modes = []
        for mode in self.modes:
            detail = f'<span fgcolor="cyan">{mode.output.name}</span>: {mode.width}x{mode.height}'
            if mode.relation is not None:
                detail += f' <span fgcolor="gray">({mode.relation[0].value.replace("-", " ").strip()} {mode.relation[1].name})</span>'
            modes.append(detail)
        label = self.label or " | ".join(mode.output.name for mode in self.modes)
        return f"🪄 \t<b>{label}</b>\t{', '.join(modes)}"


class ManualOption:
    def __init__(self, cmd=["arandr"], label="ARandr") -> None:
        self.cmd = cmd
        self.label = label

    def activate(self):
        run(self.cmd)

    def to_pango(self):
        return f'🔧 \t<b>{self.label}</b>\t<span fgcolor="gray">Manual configuration</span>'


class ResetOption:
    def activate(self):
        run(["pkill", "picom"])
        relevant_outputs = [
            output
            for output in xrandr_config()
            if output.connected and not output.name.startswith("eDP")
        ]
        if not relevant_outputs:
            message = "No external monitors found, cannot reset.\n\n" + "\n".join(
                str(output) for output in xrandr_config()
            )
            run(["rofi", "-e", message])
        else:
            off_cmd = ["xrandr"]
            for output in relevant_outputs:
                off_cmd.extend(["--output", output.name, "--off"])
            run(off_cmd)
            sleep(5)
            XRandrOption.suggested()[0].activate()
            sleep(5)
            run(["qtile", "cmd-obj", "-o", "root", "-f", "reload_config"])
        run(["picom", "-b"])
        run(["qtile", "cmd-obj", "-o", "root", "-f", "reconfigure_screens"])

    def to_pango(self):
        return '💊 \t<b><span fgcolor="red">reset display setup</span></b>\t<span fgcolor="gray">Try to re-initialize the configuration</span>'


class AutorandrOption:
    virtual_configs = {
        "common": "Mirror using largest common resolution",
        "clone-largest": "Mirror using largest resolution",
        "horizontal": "Extend desktop horizontally",
        "vertical": "Extend desktop vertically",
        "off": "switch all displays off",
    }

    @classmethod
    def detected(cls, virtual=False) -> list[Self]:
        autorandr_proc = run(
            ["autorandr", "--detected"], capture_output=True, text=True, check=True
        )
        autorandr_options = autorandr_proc.stdout.splitlines()
        if virtual:
            autorandr_options.extend(cls.virtual_configs)
        return [cls(name) for name in autorandr_options]

    @classmethod
    def virtual_options(cls):
        return [cls(name) for name in cls.virtual_configs]

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
        if self.name == "off":
            run(["xset", "dpms", "force", "off"])
        else:
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
            return f'  \t<i>{self.name}</i>\t<span color="gray">{self.virtual_configs[self.name]}</span>'

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
            '<span fgcolor="cyan">{output}</span>: {mode} <span fgcolor="gray">({pos})</span>'.format_map(
                self.outputs[name]
            )
            for name in primary + others
        )
        return f"💾 \t<b>{self.name}</b>\t{output_str}"


def xrandr_config() -> list[Output]:
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

    return outputs


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
    options = [
        *AutorandrOption.detected(),
        *XRandrOption.suggested(),
        *AutorandrOption.virtual_options(),
        ManualOption(),
        ResetOption(),
    ]

    formatted_options = "\n".join(option.to_pango() for option in options)
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
            "-l",
            "25",
        ],
        input=formatted_options,
        capture_output=True,
        text=True,
    )
    if rofi_proc.returncode == 0:
        mode_index = int(rofi_proc.stdout.strip())
        options[mode_index].activate()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        run(["rofi", "-e", str(e)])
