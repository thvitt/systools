from ast import Param
from os import fspath, renames
import os
from pathlib import Path
import re
from sys import exception
from typing import Annotated, Iterable
import unicodedata
from cyclopts import App, Parameter
from cyclopts.types import ExistingPath
from icukit import transliterate
import logging

from tv_systools.util import configure_logging2

app = App(default_parameter=Parameter(negative_bool=()))
app.register_install_completion_command(add_to_startup=False)
logger = logging.getLogger(__name__)


def fix_broken_string(
    source: str, candidates: tuple[str, ...] = ("cp437", "cp850", "cp1252")
):
    """
    Tries to fix a typical windows filename encoding error.

    Args:
        source: The broken string
        candidates: candidate encodings to try, in order
    """
    for encoding in candidates:
        try:
            binary = source.encode(encoding)
            fixed = binary.decode("utf-8")
            if fixed != source:
                fixed = unicodedata.normalize("NFC", fixed)
                return fixed, encoding
        except (UnicodeEncodeError, UnicodeDecodeError) as e:
            logger.debug("%s is not %s: %s", source, encoding, e)
            continue  # that's not the candidate
    return source, None


def recurse(args: Iterable[Path], top_down=False, include_dirs=True):
    for arg in args:
        for root, dirs, files in arg.walk(top_down=top_down):
            for name in files:
                yield root / name
            if include_dirs:
                for name in dirs:
                    yield root / name
        yield arg


@app.default
def fix_filename_encoding(
    files_or_dirs: list[ExistingPath],
    /,
    *,
    translit: Annotated[bool, Parameter(alias="-t")] = False,
    safe: Annotated[bool, Parameter(alias="-s")] = False,
    recursive: Annotated[bool, Parameter(alias=["-r"])] = False,
    dry_run: Annotated[bool, Parameter(alias="-n")] = False,
    verbose: Annotated[int, Parameter(alias="-v", count=True)] = 0,
):
    """
    Tries to fix broken or potentially problematic filenames.

    Default operation will try to recognize file names that have been mis-encoded, fix them and rename files accordingly.

    Args:
        files_or_dirs: Files or directories to work on.
        translit: Transliterate all characters to ASCII.
        safe: Replace stretches of potentially unsafe characters with '-'.
        recursive: Recursively operate on all files and directories below.
        dry_run: Do not actually rename files, just print out possible renames.
        verbose: Tell what we're doing.
    """
    if dry_run:
        verbose = max(verbose, 1)
    configure_logging2(verbosity=verbose, show_time=False)
    if recursive:
        files = recurse(files_or_dirs)
    else:
        files = files_or_dirs

    for file in files:
        try:
            source = file.name
            fixed, encoding = fix_broken_string(source)
            if translit:
                fixed = transliterate(fixed, "de-ASCII; Any-Latin; Latin-ASCII")
            if safe:
                fixed = re.sub(rf"[^\w.-{re.escape(os.pathsep)}]+", "-", fixed)
            target = file.with_name(fixed)
            if file != target:
                note = f" ({encoding})" if encoding else ""
                logger.info(f"{file} → {target}{note}")
                if not dry_run:
                    renames(file, target)
        except (OSError, ValueError) as e:
            logger.error(
                "Failed to process %s: %s",
                file,
                e,
                exc_info=logger.isEnabledFor(logging.DEBUG),
            )
