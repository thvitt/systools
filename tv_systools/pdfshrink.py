import logging
import shutil
from dataclasses import dataclass
from functools import partial
from os import PathLike, fspath, process_cpu_count
from pathlib import Path
from shlex import join
from tempfile import NamedTemporaryFile
from typing import Annotated, Optional

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
from typing_extensions import Literal

from .util import configure_logging

logger = logging.getLogger(__name__)

app = App()
app.register_install_completion_command(add_to_startup=False)


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

    def finalize(self):
        if self.improved:
            try:
                self.compressed.replace(self.output or self.original)
            except OSError as e:
                logging.debug(
                    "Failed to move compressed file %s into place, trying copy+delete: %s",
                    self.compressed,
                    e,
                )
                shutil.copy2(self.compressed, self.output or self.original)
                self.compressed.unlink()


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
        cmd = shutil.which("gs")
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
    output: Path | None = None,
    tolerance: float = 0.01,
    gs: GhostscriptOptions = GhostscriptOptions(),
) -> ShrinkResult:
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
        result = ShrinkResult(
            exitcode == 0, source, compressed, output, tolerance=tolerance
        )
        result.finalize()
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
    results: list[ShrinkResult] = []
    if largest_first:
        sources = sorted(sources, key=lambda p: p.stat().st_size, reverse=True)

    logging.debug("Shrinking %d PDFs: %s", len(sources), sources)

    with Progress(
        TextColumn("Shrinking PDFs"),
        BarColumn(),
        MofNCompleteColumn(),
        RenderableExtraColumn("result"),
        transient=True,
    ) as progress:
        progress_task = progress.add_task("Shrinking PDFs...", total=len(sources))
        async for result in map_unordered(
            partial(shrink_file, tolerance=tolerance, gs=gs), sources, limit=parallel
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
