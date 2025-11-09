#!/usr/bin/env python3
import webbrowser
from cyclopts.parameter import Parameter
from typing_extensions import Annotated
from cyclopts import App
import re
from pathlib import Path
import sys
from secrets import token_urlsafe
from typing import Optional
from subprocess import run
from tempfile import NamedTemporaryFile
from rich.table import Table
from rich.console import Console
console = Console()

app = App()
app.register_install_completion_command(add_to_startup=False)

LOCAL_ROOT = (Path.home() / "Documents/OwnCloud").resolve()
URL_ROOT = "https://public.thorstenvitt.de"
HOST = "cloud.thorstenvitt.de"
ALIAS_ROOT = "/var/www/nextcloud/data/tv/files/"
CONFIG_FILE = "/etc/nginx/public-paths.conf"
CONFIG_FORMAT = "location {url} {{ alias {path} ; }}"
CONFIG_RE = re.compile(r'location\s*(\S+)\s*{\s*alias\s*([^\s;}]+)\s*;\s*}\s*;?')

def read_config(raw=False):
    result = run(['ssh', HOST, 'cat', CONFIG_FILE], capture_output=True, encoding='utf-8')
    result.check_returncode()
    if raw:
        return result.stdout
    aliases = {match.group(1): match.group(2) for match in CONFIG_RE.finditer(result.stdout)}
    return aliases

def write_config(config: str | dict[str, str]):
    if isinstance(config, str):
        config_str = config
    else:
        config_str = '\n'.join(CONFIG_FORMAT.format_map(dict(url=url, path=path)) for (url, path) in config.items()) + '\n'
    result = run(['ssh', HOST, 'sudo', 'tee', CONFIG_FILE], input=config_str, encoding='utf-8', capture_output=True)
    result.check_returncode()

def restart_server():
    result = run(['ssh', HOST, 'sudo', 'systemctl', 'restart', 'nginx.service'])
    result.check_returncode()

@app.command()
def edit():
    config = read_config(raw=True)
    with NamedTemporaryFile('wt', encoding='utf-8', suffix='.conf', delete=False) as f:
        f.write(config)
        f.close()
        run(['nvim', '-c', 'set ft=nginx', f.name])
        write_config(Path(f.name).read_text())
    restart_server()

@app.command()
def add(path: Optional[Path] = None,
        urlpath: Optional[str] = None):
    """
    Adds a new urlpath configuration.

    Args:
        path: The local path to publish. Must be inside {LOCAL_ROOT}. If missing, assume current path.
        urlpath: The remote urlpath to use. If missing, create a safe automatic one.
    """
    if not path:
        path = Path()
    full_path = path.resolve()
    if not full_path.is_relative_to(LOCAL_ROOT):
        print(f"Path {path} must be somewhere below {LOCAL_ROOT}.")
        sys.exit(1)

    remote_path = str(ALIAS_ROOT / full_path.relative_to(LOCAL_ROOT))

    if not urlpath:
        urlpath = token_urlsafe(12)
    if urlpath[0] != '/':
        urlpath = '/' + urlpath
    if urlpath[-1] == '/':
        urlpath = urlpath[:-1]

    print(f'Adding alias {urlpath} for {remote_path}')
    config = read_config()
    if urlpath in config:
        raise ValueError(r'{urlpath} is already in config, associated with {config[urlpath]}')
    if remote_path in config.values():
        known_aliases = [key for key in config if config[key] == remote_path]
        print(f'WARNING: {remote_path} is already available at {", ".join(known_aliases)}')
    config[urlpath] = remote_path
    write_config(config)
    restart_server()
    webbrowser.open(URL_ROOT + urlpath, autoraise=True)

@app.command()
def list():
    config = read_config()
    table = Table("URL", "Path")
    for urlpath, localpath in config.items():
        table.add_row(URL_ROOT + urlpath, str(LOCAL_ROOT / localpath[len(ALIAS_ROOT):]))
    console.print(table)




if __name__ == "__main__":
    app()
