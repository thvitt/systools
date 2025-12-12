import logging
import subprocess
from collections.abc import Sequence
from pathlib import Path

import httpx
from cyclopts import App
from pzp import pzp
from rich.logging import RichHandler

from tv_systools.ui import edit

app = App()
app.register_install_completion_command(add_to_startup=False)

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    handlers=[RichHandler(show_time=False, show_path=False, rich_tracebacks=True)],
    format="%(message)s",
)


@app.command(name=["-f", "--find"])
def find_gitignore() -> Path:
    """
    Print the nearest .gitignore file’s path, falling back to the repository root.
    """
    current = Path(".gitignore")
    if current.exists():
        return current

    root = Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    cand = current
    cwd = Path().absolute()
    while cwd.is_relative_to(root):
        cand = cwd / ".gitignore"
        if cand.exists():
            break
        if cwd == root:
            break
        cwd = cwd.parent
    return cand


@app.command(name=["-e", "--edit"])
def edit_gitignore() -> int:
    """
    Edit the nearest .gitignore file, falling back to the repository root.
    """
    return edit(find_gitignore())


@app.command(name=["-t", "--template"])
def gitignore_template(templates: list[str]):
    """
    Add the given templates from github to the gitignore file.
    """
    with find_gitignore().open("at") as gitignore, httpx.Client() as client:
        logger.info("Appending to gitignore file %s", gitignore.name)
        for template_name in templates:
            response = client.get(
                f"https://api.github.com/gitignore/templates/{template_name}",
                headers={
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            if response.is_success:
                template = response.json()
                gitignore.writelines(
                    [f"# --- {template['name']} ---", template["source"]]
                )
                logger.info(
                    "Added %d lines for %s (%s)",
                    len(template["source"]),
                    template_name,
                    template["name"],
                )
            else:
                logger.error("Failed to fetch template %s: %s", template_name, response)


@app.command(name=["-p", "--pick"])
def pick_templates():
    available_templates = httpx.get(
        "https://api.github.com/gitignore/templates",
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    ).json()
    selected_templates = []

    while selection := pzp(
        available_templates,
        height=20,
        fullscreen=False,
        layout="reverse",
        prompt_str="Pick a template, Esc if you are done: ",
    ):
        selected_templates.append(selection)
    if selected_templates:
        gitignore_template(selected_templates)


@app.default
def git_ignore(patterns: Sequence[str] = (), /):
    """
    Add patterns to the .gitignore file.
    """
    if patterns:
        gitignore_file = find_gitignore()
        lines = gitignore_file.read_text().splitlines()

        for pattern in patterns:
            path = Path(pattern)
            if (
                path.exists()
                and not path.is_absolute()
                and path.is_relative_to(gitignore_file.parent)
            ):
                new_pattern = "/" + str(path.relative_to(gitignore_file.parent))
                lines.append(new_pattern)
            else:
                lines.append(pattern)
    else:
        pick_templates()
