from shutil import which
from subprocess import PIPE, run
import json
from shlex import quote
import logging
from textwrap import wrap

logger = logging.getLogger(__name__)


def get_pipx_specs():
    pipx_path = which("pipx")
    if pipx_path is None:
        raise ValueError("pipx not found")
    pipx = run([pipx_path, "list", "--json"], stdout=PIPE)
    spec = json.loads(pipx.stdout)
    for venv, metadata_ in spec["venvs"].items():
        metadata = metadata_["metadata"]
        try:
            main_pkg = metadata["main_package"]["package_or_url"]
            injected = [
                inj["package_or_url"] for inj in metadata["injected_packages"].values()
            ]
            if injected:
                args = "--with=" + ",".join(map(quote, injected)) + " "
            else:
                args = ""

            apps = " ".join(metadata["main_package"].get("apps", []))
            print(
                *wrap(
                    apps,
                    80,
                    initial_indent=f"# {venv}: ",
                    subsequent_indent="# " + " " * (len(venv) + 2),
                    break_on_hyphens=False,
                    break_long_words=False,
                ),
                sep="\n",
            )
            print(
                f"uv tool install {args}{quote(main_pkg)}",
                end="\n\n",
            )
        except KeyError as e:
            logger.exception(
                "%s: key %s missing (metadata=%s)", venv, e, metadata.keys()
            )
