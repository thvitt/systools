#!/usr/bin/env python

from collections.abc import Generator, Iterable
from dataclasses import dataclass
from os import fspath
from pathlib import Path
import subprocess
from rich.console import Console
from rich.table import Table
import typer
import unicodedata

app = typer.Typer()

@dataclass
class Glyph:
    codepoint: int
    glyphno: int
    glyphname: str | None

    @property 
    def char(self):
        return chr(self.codepoint)

    @property
    def name(self):
        try:
            return unicodedata.name(self.char)
        except ValueError:
            return ""

    @property
    def category(self):
        return unicodedata.category(self.char)

    @property
    def code(self):
        return f"U+{self.codepoint:04X}"


def glyph_table(glyphs: Iterable[Glyph]) -> Table:
    table = Table()
    table.add_column("C", style="bold")
    table.add_column("Unicode", justify="right", style="cyan")
    table.add_column("Glyph", style="green")
    table.add_column("Class", style="yellow")
    table.add_column("Name")

    for glyph in glyphs:
        table.add_row(glyph.char, glyph.code, glyph.glyphname, glyph.category, glyph.name)

    return table

@app.command("table")
def print_table(file: Path):
    """
    Prints a table of all glyphs defined in the given font file. 
    The following columns will be available:

        - C: the actual character

        - Unicode: the unicode codepoint of the character

        - Glyph: the glyph name defined in the font 

        - category: the unicode category code (e.g., Lu for upper-case letter)

        - Name: The official unicode name of the character
    """
    table = glyph_table(get_info(file))
    console = Console()
    console.print(table)

@app.command("intervals")
def print_intervals(file: Path):
    """
    Prints a list of all unicode codepoint intervals present in the font.
    """
    glyphs = get_info(file)
    ints = intervals(glyph.codepoint for glyph in glyphs)
    print(",".join(f"U+{start:04X}-U+{end:04X}" if start != end else f"U+{start:04X}"
                   for start, end in ints))




def get_info(file: Path) -> Generator[Glyph, None, None]:
    otfinfo = subprocess.run(['otfinfo', '-u', fspath(file)], capture_output=True, check=True, encoding='utf-8')
    for line in otfinfo.stdout.splitlines():
        parts = line.split()
        yield Glyph(int(parts[0][3:], 16),
                    int(parts[1]),
                    parts[2] if len(parts) > 2 else None)


def intervals(values: Iterable[int]) -> list[tuple[int,int]]:
    """
    Finds continuous intervals of integers in values.

    Returns a sorted list of (start, end) values for each interval. 

    Example:
        >>> intervals([5,1,4,6,10,11,12,20])
        [(1, 1), (4, 6), (10, 12), (20, 20)]
    """
    result = []
    sorted_values = sorted(values)
    start = end = sorted_values[0]
    for value in sorted_values:
        if value > end+1:
            result.append((start, end))
            start = end = value
        end = value
    result.append((start, end))
    return result


if __name__ == "__main__":
    app()
