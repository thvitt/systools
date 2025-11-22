from rich.progress import BarColumn, ProgressColumn, MofNCompleteColumn, Task, TextColumn
from typing import Optional
from rich.table import Column
from rich.text import Text
from functools import partial
from rich.progress import Progress
from typing import Annotated
from .async_utils import map_unordered
from .util import configure_logging
from os import fspath, process_cpu_count
from pathlib import Path
import shutil
from cyclopts import App, Parameter, validators
from humanize import naturalsize
from rich import print
from tempfile import NamedTemporaryFile
from logproc import aexecute
import logging

logger = logging.getLogger(__name__)

app = App()
app.register_install_completion_command(add_to_startup=False)

class ShrinkResult:

    def __init__(self, success: bool, original: Path, compressed: Path, output: Path | None = None, tolerance: float = 0.01):
        self.success = success
        self.original = original
        self.compressed = compressed
        self.output = output
        self.tolerance = tolerance

        self.original_size = original.stat().st_size
        self.output_size = compressed.stat().st_size
        self.max_tolerable_size = int(self.original_size * (1 - self.tolerance)) if self.tolerance < 1 else self.original_size - int(self.tolerance)

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
            self.compressed.replace(self.output or self.original)


async def shrink_file(source: Path, output: Path | None = None, tolerance: float = 0.01) -> ShrinkResult:
    gs = shutil.which("gs")
    if gs is None:
        raise OSError("Ghostscript (gs) not found in PATH")
    with NamedTemporaryFile(delete_on_close=False, suffix=".pdf", prefix=f".{source.stem}__") as tempfile:
        tempfile.close()
        compressed = Path(tempfile.name)
        exitcode = await aexecute([
            gs,
            f"-o{fspath(compressed)}",
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.4",
            "-dPDFSETTINGS=/screen",
            # "-dQUIET",
            "-dNOPAUSE",
            fspath(source),
        ], prefix=source.name + ": ", stdout_level=logging.DEBUG)
        result = ShrinkResult(exitcode == 0, source, compressed, output, tolerance=tolerance)
        result.finalize()
        return result

class RenderableExtraColumn(ProgressColumn):
    def __init__(self, extra_key: str, default: str = "", table_column: Optional[Column] = None):
        super().__init__(table_column=table_column)
        self.extra_key = extra_key
        self.default = default

    def render(self, task: Task) -> Text:
        return task.fields.get(self.extra_key, Text(self.default))

@app.default
async def pdfshrink(
        sources: list[Path],
        /, *,
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
    configure_logging(level=logging.DEBUG if debug else (logging.INFO if verbose else logging.WARNING))
    results: list[ShrinkResult] = []
    if largest_first:
        sources = sorted(sources, key=lambda p: p.stat().st_size, reverse=True)

    with Progress(TextColumn("Shrinking PDFs"), BarColumn(), MofNCompleteColumn(), RenderableExtraColumn('result'), transient=True) as progress:
        progress_task = progress.add_task("Shrinking PDFs...", total=len(sources))
        async for result in map_unordered(partial(shrink_file, tolerance=tolerance), sources, limit=parallel):
            progress.update(progress_task, advance=1, result=result)
            logger.info("%s", result)
            results.append(result)

    total_orig = sum(r.original_size for r in results)
    total_improvement = sum(r.improvement for r in results)
    n_improved = sum(r.improved for r in results)

    print(f"Shrunk {n_improved} of {len(sources)} files, winning {naturalsize(total_improvement)} of {naturalsize(total_orig)} ({total_improvement / total_orig:2.1%})")
