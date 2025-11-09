from tv_systools.async_utils import map_unordered
import asyncio
from os import fspath
from pathlib import Path
import shutil
from cyclopts import App, Parameter, validators
from humanize import naturalsize
from rich import print
from subprocess import run
from tempfile import NamedTemporaryFile

app = App()
app.register_install_completion_command(add_to_startup=False)

class ShrinkResult:

    def __init__(self, success: bool, original: Path, compressed: Path, output: Path | None = None):
        self.success = success
        self.original = original
        self.compressed = compressed
        self.output = output

        self.original_size = original.stat().st_size
        self.output_size = compressed.stat().st_size

    @property
    def improved(self) -> bool:
        return self.success and self.output_size < self.original_size

    def improvement_desc(self) -> str:
        return f"{naturalsize(self.original_size)} -> {naturalsize(self.output_size)} ({self.output_size / self.original_size:2.1%})"

    def improvement(self):
        return max(0, self.original_size - self.output_size)

    def __rich__(self) -> str:
        if self.success:
            if self.improved:
                if self.output:
                    return f"[green]Reduced[/green] {self.original} to {self.output}: {self.improvement_desc()}"
                else:
                    return f"[green]Reduced[/green] {self.original}: {self.improvement_desc()}"
            else:
                return f"[yellow]No improvement[/yellow]: {naturalsize(self.original_size)}"
        else:
            return f"[red]Failed[/red] to compress {self.original}"

    def finalize(self):
        if self.improved:
            self.compressed.replace(self.output or self.original)


async def shrink_file(source: Path, output: Path | None = None) -> ShrinkResult:
    gs = shutil.which("gs")
    if gs is None:
        raise OSError("Ghostscript (gs) not found in PATH")
    with NamedTemporaryFile(delete_on_close=False, suffix=".pdf", prefix=f".{source.stem}__") as tempfile:
        tempfile.close()
        compressed = Path(tempfile.name)
        proc = await asyncio.create_subprocess_exec(
            gs,
            f"-o{fspath(compressed)}",
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.4",
            "-dPDFSETTINGS=/screen",
            "-dQUIET",
            "-dNOPAUSE",
            fspath(source),
        )
        exitcode = await proc.wait()
        result = ShrinkResult(exitcode == 0, source, compressed, output)
        result.finalize()
        return result

@app.default
async def pdfshrink(
        *sources: Path,
):
    results: list[ShrinkResult] = []
    # for result in asyncio.as_completed(
    #         [shrink_file(source, None) for source in sources]
    # ):
    async for result_ in map_unordered(shrink_file, sources, limit=16):
        # result_ = await result
        print(result_)
        results.append(result_)
    print(f"Total improvement: {naturalsize(sum(r.improvement() for r in results))}")
