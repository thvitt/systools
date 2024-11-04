from pathlib import Path
from difflib import unified_diff
import typer
from .util import configure_logging
from rich.console import Console
from rich.syntax import Syntax
import logging

app = typer.Typer()
logger = logging.getLogger(__name__)
console = Console()


def basepath(conflict: Path) -> Path:
    new_suffixes = "".join(
        suffix for suffix in conflict.suffixes if "sync-conflict" not in suffix
    )
    print(conflict.suffixes, "=>", new_suffixes)
    if new_suffixes and new_suffixes[0] != ".":
        new_suffixes = "." + new_suffixes
    return conflict.with_name(conflict.name[: conflict.name.find(".")] + new_suffixes)


@app.command()
def clean_interactively(roots: list[Path]):
    configure_logging(console)
    for root in roots:
        for conflict in root.glob("**/*.sync-conflict-*"):
            base = basepath(conflict)
            console.print(f"Comparing {base} with {conflict.name} ...")
            base_text = base.read_text()
            conflict_text = conflict.read_text()
            if base_text == conflict_text:
                console.print("Files are identical, removing conflict file.")
                # conflict.unlink()
                continue
            else:
                diff = list(
                    unified_diff(
                        base_text.splitlines(),
                        conflict_text.splitlines(),
                        fromfile=base.name,
                        tofile=conflict.name,
                    )
                )
            console.print(Syntax("\n".join(diff), "udiff"))


if __name__ == "__main__":
    app()
