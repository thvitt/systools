from pathlib import Path
from platformdirs import PlatformDirs
import tomllib
from prompt_toolkit.lexers import PygmentsLexer
import questionary
from pygments.lexers.markup import MarkdownLexer
import shlex
import sys
from subprocess import run
from datetime import datetime

"""
Add a new item to today’s LogSeq journal.

There are three ways to run this:

- with arguments: The arguments are added as one item to the journal: `j New Content`
- content on stdin will be added: `echo "New Content" | j`
- interactively: Just `j` will ask for the content – in the terminal when stdout is a TTY, or in a rofi dialog otherwise.

You can configure the path to your journal files and the filename pattern in a TOML file at `~/.config/logseq_j/config.toml`,
if this file does not exist, you will be asked for the path and filename pattern on the first run.
"""


def load_config():
    dirs = PlatformDirs("logseq_j", "Thorsten Vitt")
    config_file = dirs.user_config_path / "config.toml"
    if config_file.exists():
        with config_file.open("rb") as f:
            return tomllib.load(f)
    else:
        config_file.parent.mkdir(parents=True, exist_ok=True)
        path = questionary.path(
            "Where are your LogSeq journal files?", only_directories=True
        ).ask()
        filenames = questionary.text(
            "What is the filename pattern for your journal files?",
            default="%Y_%m_%d.md",
        ).ask()
        questionary.print(f"Configuration info is saved to {config_file}.")
        config_file.write_text(f"path = {path!r}\npattern = {filenames!r}\n")
        return {"path": path, "pattern": filenames}


def rofi_read() -> str | None:
    proc = run(
        [
            "rofi",
            "-dmenu",
            "-keep-right",
            "-p",
            "– ",
            "-mesg",
            "Enter additional content for today’s journal",
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode == 1:
        sys.exit(proc.returncode)
    return proc.stdout


def main():
    options = load_config()
    args = sys.argv[1:]
    if args:
        text = shlex.join(args)
    elif sys.stdin.isatty():
        text = questionary.text(
            "Your journal entry:",
            lexer=PygmentsLexer(MarkdownLexer),
            default="- ",
            multiline=True,
        ).ask()
    elif not sys.stdout.isatty():
        text = rofi_read()
    else:
        text = sys.stdin.read()
        if not text:
            text = rofi_read()

    if text:
        if not text.startswith("- "):
            text = "- " + text
        if not text.startswith("\n"):
            text = "\n" + text
        if not text.endswith("\n"):
            text += "\n"
        journal = Path(options["path"]).expanduser() / datetime.now().strftime(
            options["pattern"]
        )
        with journal.open("a" if journal.exists() else "w") as f:
            f.write(text)
    else:
        sys.exit(1)
