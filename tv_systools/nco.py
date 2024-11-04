#!/usr/bin/env python3

from pathlib import Path
import sys
from urllib.parse import urlencode
import webbrowser


def main():
    if len(sys.argv) > 1:
        paths = [Path(arg) for arg in sys.argv[1:]]
    else:
        paths = [Path()]
    dirs = [path if path.is_dir() else path.parent for path in paths]
    root = Path.home() / "Documents/OwnCloud"
    reldirs = [str(dir.absolute().relative_to(root)) for dir in dirs]
    for reldir in reldirs:
        webbrowser.open(
            "https://cloud.thorstenvitt.de/apps/files?" + urlencode({"dir": reldir})
        )
