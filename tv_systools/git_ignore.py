from pathlib import Path

from cyclopts import App

app = App()
app.register_install_completion_command(add_to_startup=False)


@app.default
def git_ignore(patterns: list[str], /):
    """
    Add patterns to the .gitignore file.
    """
    gitignore_file = Path(".gitignore")
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
