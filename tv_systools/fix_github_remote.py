from cmath import isinf
from pathlib import Path
from posixpath import exists
import re
from enum import Enum
import logging
from subprocess import CalledProcessError
from typing import Annotated
from cyclopts import App, Parameter, validators
from rich.console import OverflowMethod
from rich.table import Column, Table
from rich import get_console
from rich.text import Text

from tv_systools.util import configure_logging, display_path, run_pipe

logger = logging.getLogger()
app = App()

class RemoteKind(Enum):
    GIT = "git"
    SSH = "ssh"
    HTTPS = "https"
    UNKNOWN = "?"

    @property
    def pattern(self):
        match self:
            case RemoteKind.GIT:
                return r'git://github\.com/([^/]+)/([^/]+)'
            case RemoteKind.SSH:
                return r'git@github\.com:([^/]+)/([^/]+)'
            case RemoteKind.HTTPS:
                return r'https://github\.com/([^/]+)/([^/]+)'
            case RemoteKind.UNKNOWN:
                return r'.*'

    @classmethod
    def of(cls, remote_url):
        for kind in cls:
            if re.match(kind.pattern, remote_url):
                return kind
        raise ValueError(f"Unknown remote URL format: {remote_url}")

    def __rich__(self) -> str:
        styles = {
            RemoteKind.GIT: "red",
            RemoteKind.SSH: "green",
            RemoteKind.HTTPS: "cyan",
            RemoteKind.UNKNOWN: "violet"
        }
        return f"[{styles[self]}]{self.value}"


class URL:

    def __init__(self, remote_url):
        self.url = remote_url
        self.kind = RemoteKind.of(remote_url)
        if self.kind == RemoteKind.UNKNOWN:
            self.user, self.repo = None, None
        else:
            match = re.match(self.kind.pattern, remote_url)
            assert match is not None
            self.user, self.repo = match.groups( )

    def to(self, kind: RemoteKind):
        if kind == RemoteKind.GIT:
            return f'git://github.com/{self.user}/{self.repo}'
        elif kind == RemoteKind.SSH:
            return f'git@github.com/{self.user}/{self.repo}'
        elif kind == RemoteKind.HTTPS:
            return f'https://github.com/{self.user}/{self.repo}'
        else:
            raise ValueError(f"Cannot convert {self} to {kind}")

    def __str__(self) -> str:
        return self.url

    def __eq__(self, value: object, /) -> bool:
        if isinstance(value, URL):
            return self.url == value.url
        else:
            return self.url == value

    def __rich__(self) -> Text:
        text = Text(self.url)
        if self.kind != RemoteKind.UNKNOWN:
            match = re.match(self.kind.pattern, self.url)
            assert match is not None
            text.stylize("cyan", *match.span(1))
            text.stylize("cyan", *match.span(2))

        return text


class Repository:

    path: Path
    remotes: dict[str, URL]
    push_remotes: dict[str, URL]

    def __init__(self, path: Path):
        self.path = Path(run_pipe("git", "rev-parse", "--show-toplevel", cwd=path))
        self.remotes = {}
        self.push_remotes = {}
        remotes_str = run_pipe('git', 'remote', '-v', cwd=self.path)
        for remote, url, method in re.findall(r'(\w+)\s+(\S+)\s+\((fetch|push)\)', remotes_str):
            try:
                if method == "push":
                    if url != self.remotes.get(remote):
                        self.push_remotes[remote] = URL(url)
                else:
                    self.remotes[remote] = URL(url)
            except ValueError as e:
                logger.warning('Repository at %s: Skipping remote %s (%s, %s): %s', self.path, remote, method, url, e, exc_info=e)


    def switch_remotes(self, kind: RemoteKind, push: bool):
        for remote, url in self.remotes.items():
            if url.kind == RemoteKind.UNKNOWN:
                continue

            cmd = ['git', 'remote', 'set-url']
            if push:
                cmd.append('--push')
            cmd.append(remote)
            if push and remote in self.push_remotes:
                cmd.append(self.push_remotes[remote].to(kind))
            else:
                cmd.append(url.to(kind))
            try:
                run_pipe(cmd, cwd=self.path)
            except CalledProcessError as e:
                logger.error('Failed to switch remote %s for repository at %s: %s (%d)', remote, self.path, e.stderr, e.returncode)

@app.default
def main(paths: Annotated[list[Path] | None, Parameter(required=False, validator=validators.Path(exists=True, file_okay=False))] = None, 
         /, *,
         to: Annotated[RemoteKind | None, Parameter(alias=["-t"])] = None,
         push: Annotated[bool, Parameter(alias=["-p"])] = False,
         submodules: Annotated[bool, Parameter(alias=["-s"])] = False):
    console = get_console()
    configure_logging(console=console, level=logging.INFO)
    if not paths:
        paths = [Path()]
    if submodules:
        for repository in paths:
            submodules_list = run_pipe('git', 'submodule', 'status', '--recursive', cwd=repository)
            for submodule in re.findall(r'.[0-9a-f]+\s+(.*)\s+\(.*\)', submodules_list):
                paths.append(repository / submodule)

    repositories = [Repository(path) for path in paths]

    table = Table(Column("repository"), "remote", "url", "kind", show_edge=False)
    for repo in repositories:
        for remote in repo.remotes:
            url = repo.remotes[remote]
            table.add_row(display_path(repo.path), remote, url, url.kind)
            if remote in repo.push_remotes:
                push_url = repo.push_remotes[remote]
                table.add_row("", f"{remote} [red](push)", push_url, push_url.kind)

    console.print(table)

    if to:
        for repo in repositories:
            repo.switch_remotes(to, push=push)
