from shutil import which
from typing import Literal
import logging
from dataclasses import dataclass
from functools import partial
from os import PathLike, fspath, process_cpu_count
from pathlib import Path
from shlex import join
from tempfile import NamedTemporaryFile
from typing import Annotated, Optional

from aioshutil import copy2

from cyclopts import App, Parameter
from cyclopts.types import PositiveInt
from humanize import naturalsize
from logproc import aexecute, map_unordered
from rich import print
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    ProgressColumn,
    Task,
    TextColumn,
)
from rich.table import Column
from rich.text import Text
import rich.traceback

from tv_systools.ui import SubtasksColumn

from .util import configure_logging

logger = logging.getLogger(__name__)
rich.traceback.install()

app = App(help_on_error=True)
app.register_install_completion_command(add_to_startup=False)


async def move(what: Path, where: Path):
    """Tries to move what to where, either directly or by copying and removing"""
    try:
        what.replace(where)
    except OSError as e:
        logging.debug("Failed to move %s to %s, trying copy+delete: %s", what, where, e)
        await copy2(what, where)
        what.unlink()


@Parameter("*", group="Output Parameters")
@dataclass(frozen=True)
class OutputOptions:
    output: Annotated[Path | None, Parameter(alias="-o")] = None
    """Output path for the files that have been shrunk. If missing, overwrite source file."""

    copy_unchanged: Annotated[bool, Parameter(negative="-U")] = True
    """Copy unchanged files to the output name or directory"""

    backup: bool = False
    """Create a backup instead of replacing files."""

    backup_suffix: str = "~"
    """Appended to the file name to create a backup file. If it contains a `{}`, we assume a pattern and replace {} with the original filename."""

    def validate(self, input: list[Path]):
        """Checks whether the input is compatible with the output settings."""
        if self.output is None:
            return True
        if self.output.is_file():
            if len(input) > 1:
                raise ValueError(
                    f"Multiple input files ({len(input)}) are present, the output ({self.output}) must be a directory (or missing, meaning in-place optimization)"
                )
        if not self.output.exists() and len(input) > 1:
            logger.debug("Creating output directory %s", self.output)
            self.output.mkdir(parents=True)
        return True

    async def do_backup(self, what: Path):
        if self.backup:
            if "{}" in self.backup_suffix:
                target = what.parent / self.backup_suffix.format(what.name)
            else:
                target = what.with_name(what.name + self.backup_suffix)
        else:
            target = what.with_name(what.name + "~")
        await move(what, target)

    async def finalize(self, result: "ShrinkResult") -> None:
        if result.improved and self.output is None:  # overwrite original
            await self.do_backup(result.original)
            await move(result.compressed, result.original)
        elif result.improved or self.copy_unchanged and self.output is not None:
            assert self.output is not None
            if self.output.is_dir():
                result.output = self.output / result.original.name
            else:
                result.output = self.output
            if result.improved:
                await copy2(result.compressed, result.output)
            else:
                await copy2(result.original, result.output)
        # else nothing to do


class ShrinkResult:
    def __init__(
        self,
        success: bool,
        original: Path,
        compressed: Path,
        output: Path | None = None,
        tolerance: float = 0.01,
    ):
        self.success = success
        self.original = original
        self.compressed = compressed
        self.output = output
        self.tolerance = tolerance

        self.original_size = original.stat().st_size
        self.output_size = compressed.stat().st_size
        self.max_tolerable_size = (
            int(self.original_size * (1 - self.tolerance))
            if self.tolerance < 1
            else self.original_size - int(self.tolerance)
        )

    @property
    def improved(self) -> bool:
        return self.success and self.output_size < self.max_tolerable_size

    def improvement_desc(self) -> str:
        return f"{naturalsize(self.original_size)} -> {naturalsize(self.output_size)} ({self.output_size / self.original_size:2.1%})"

    @property
    def improvement(self):
        return self.original_size - self.output_size if self.improved else 0

    def __rich__(self) -> str:
        if self.success:
            if self.improved:
                if self.output:
                    return f"{self.original.name:20}: [green]reduced[/green] to {self.output}: {self.improvement_desc()}"
                else:
                    return f"{self.original.name:20}: [green]reduced[/green]: {self.improvement_desc()}"
            else:
                return f"{self.original.name:20}: [yellow]no improvement[/yellow]: {naturalsize(self.original_size)}"
        else:
            return f"[red]failed[/red] to compress {self.original}"

    def __str__(self) -> str:
        return str(Text.from_markup(self.__rich__()))


@Parameter("*", group="PDF Options")
@dataclass(frozen=True)
class GhostscriptOptions:
    preset: Literal["screen", "ebook", "printer", "prepress"] | None = None
    """Use a GhostScript preset.
    `screen` will probably generate the smallest files, with really ugly images.
    """

    compatibility: Annotated[str, Parameter(alias=["-c"])] = "1.7"
    """PDF compatibility level"""

    resolution: Annotated[PositiveInt | None, Parameter(alias=["-r"])] = None
    """downsample color and grayscale images to this resolution (dpi)"""

    def cmdline(
        self, src: PathLike | None = None, dst: PathLike | None = None
    ) -> list[str]:
        """
        Builds a command line for Ghostscript, including the executable file.

        Args:
            src: the file to convert. If missing, this option will not be included.
            dst: the file to create. If missing, this option (-o) will not be included.

        Returns:
            a command line as list of arguments
        """
        cmd = which("gs")
        if cmd is None:
            raise FileNotFoundError(
                "The ghostscript executable (gs) could not be found."
            )
        result = [
            cmd,
            "-sDEVICE=pdfwrite",
        ]

        if self.preset is not None:
            result.append(f"-dPDFSETTINGS=/{self.preset}")

        if self.compatibility:
            result.append(f"-dCompatibilityLevel={self.compatibility}")

        if self.resolution:
            result.extend(
                [
                    f"-r{self.resolution}",
                    "-dDownsampleColorImages=true",
                    "-dColorImageDownsampleType=/Bicubic",
                    f"-dColorImageResolution={self.resolution}",
                    "-dDownsampleGrayImages=true",
                    "-dGrayImageDownsampleType=/Bicubic",
                    f"-dGrayImageResolution={self.resolution}",
                ]
            )

        if dst:
            result.extend(["-o", fspath(dst)])
        else:
            result.extend(["-dNOPAUSE", "-dBATCH"])  # included in -o

        if src:
            result.append(fspath(src))

        return result


async def shrink_file(
    source: Path,
    tolerance: float = 0.01,
    gs: GhostscriptOptions = GhostscriptOptions(),
    output: OutputOptions = OutputOptions(),
    subtasks: SubtasksColumn | None = None,
) -> ShrinkResult:
    if subtasks:
        subtasks.add(source.stem)
    with NamedTemporaryFile(
        delete_on_close=False, suffix=".pdf", prefix=f".{source.stem}__"
    ) as tempfile:
        tempfile.close()
        compressed = Path(tempfile.name)
        cmdline = gs.cmdline(source, compressed)
        logger.debug("Executing %s", join(cmdline))
        exitcode = await aexecute(
            cmdline,
            prefix=source.name + ": ",
            stdout_level=logging.DEBUG,
        )
        result = ShrinkResult(exitcode == 0, source, compressed, tolerance=tolerance)
        await output.finalize(result)
        if subtasks:
            subtasks.rm(source.stem)
        return result


class RenderableExtraColumn(ProgressColumn):
    def __init__(
        self, extra_key: str, default: str = "", table_column: Optional[Column] = None
    ):
        super().__init__(table_column=table_column)
        self.extra_key = extra_key
        self.default = default

    def render(self, task: Task) -> Text:
        return task.fields.get(self.extra_key, Text(self.default))


@app.default
async def pdfshrink(
    sources: list[Path],
    /,
    *,
    gs: GhostscriptOptions = GhostscriptOptions(),
    output: OutputOptions = OutputOptions(),
    tolerance: Annotated[float, Parameter(alias="t")] = 0.01,
    parallel: Annotated[int, Parameter(alias="-p")] = process_cpu_count() or 8,
    largest_first: Annotated[bool, Parameter(alias="-l")] = True,
    verbose: Annotated[bool, Parameter(alias="-v", negative=False)] = False,
    debug: Annotated[bool, Parameter(alias="-vv", negative=False)] = False,
):
    """
    Try to shrink all given PDF files using Ghostscript.

    Args:
        sources: The PDF files to shrink
        tolerance: Minimum improvement (as fraction) to consider a file shrunk
        parallel: how many processes to run in parallel
        largest_first: Start with the largest files first instead of the given order
        verbose: produce verbose output
        debug: even more vrbose output, including GhostScripts messages
    """
    configure_logging(
        level=logging.DEBUG if debug else (logging.INFO if verbose else logging.WARNING)
    )
    output.validate(sources)
    results: list[ShrinkResult] = []
    if largest_first:
        sources = sorted(sources, key=lambda p: p.stat().st_size, reverse=True)

    logging.debug("Shrinking %d PDFs: %s", len(sources), sources)

    with Progress(
        TextColumn("Shrinking PDFs"),
        BarColumn(),
        MofNCompleteColumn(),
        subtasks := SubtasksColumn(),
        transient=True,
    ) as progress:
        progress_task = progress.add_task("Shrinking PDFs...", total=len(sources))
        async for result in map_unordered(
            partial(
                shrink_file,
                tolerance=tolerance,
                gs=gs,
                output=output,
                subtasks=subtasks,
            ),
            sources,
            limit=parallel,
        ):
            progress.update(progress_task, advance=1, result=result)
            logger.info("%s", result)
            results.append(result)

    total_orig = sum(r.original_size for r in results)
    total_improvement = sum(r.improvement for r in results)
    n_improved = sum(r.improved for r in results)

    print(
        f"Shrunk {n_improved} of {len(sources)} files, winning {naturalsize(total_improvement)} of {naturalsize(total_orig)} ({total_improvement / total_orig:2.1%})"
    )
