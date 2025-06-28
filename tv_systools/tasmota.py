from collections.abc import Mapping, MutableMapping
from typing import Annotated, Any, Optional
import typer
import httpx
from xdg.BaseDirectory import load_config_paths, save_config_path
from pathlib import Path
from collections import ChainMap
from rich.table import Table
from rich import get_console
from rich.progress import track
import tomlkit
import jsonpath

from .util import first

app = typer.Typer()

def load_config() -> MutableMapping[str, Any]:
    potential_device_files = [Path(dir) / "devices.toml" for dir in load_config_paths("tasmota")]
    device_files = [file for file in potential_device_files if file.exists()]
    configs = [tomlkit.parse(file.read_text()) for file in device_files]
    return ChainMap(*configs)

def device_names(config: MutableMapping[str, Any]) -> list[str]:
    return [name for name, value in config.items() if isinstance(value, Mapping)]

config  = load_config()

def complete_devices(incomplete: str) -> list[str]:
    """
    Autocomplete function for device names.
    """
    return [(name, config[name].get('description')) for name in device_names(config) if name.startswith(incomplete.strip())]

def complete_commands(ctx: typer.Context, incomplete: str) -> list[str]:
    try:
        device = resolve_device(ctx.params.get("device", ""))
        if device and device in config:
            commands = config[device].get("commands", {})
            return [cmd for cmd in commands if cmd.startswith(incomplete.strip())]
    except typer.BadParameter:
        return []

def show_device_info():
    table = Table(
        "Name",
        "Description",
        "Status",
        title="Configured Devices", box=None)
    for name in track(device_names(config), description="Checking device status", transient=True):
        status_command = config[name].get('status')
        if status_command:
            response = httpx.get(config[name].get('url'), params={"cmnd": status_command})
            if response.is_success:
                msg = format_response(name, status_command, response.json())
                status = f"[bold green]{msg}[/bold green]"
            else:
                status = f"[bold red]Error:[/bold red] {response.status_code} {response.text}"
        else:
            status = '?'
        table.add_row(
            name,
            config[name].get('description', ''),
            status)
    get_console().print(table)
    
def format_response(device: str, command: str, response: dict) -> str:
    result_mapping = config[device].get("results", {}).get(command)
    if result_mapping is None:
        variables = response
    elif isinstance(result_mapping, str):
        variables = first(jsonpath.findall(result_mapping, response))
    elif isinstance(result_mapping, Mapping):
        variables = {key: first(jsonpath.findall(path, response)) for key, path in result_mapping.items()}
    else:
        raise ValueError(f"Invalid result mapping for command '{command}' in device '{device}': {result_mapping}")
    template = config[device].get("templates", {}).get(command)
    if template:
        if isinstance(variables, Mapping):
            return template.format_map(variables)
        else:
            return template.format(variables)
    else:
        return str(variables)
    
def resolve_device(device: str) -> str:
    """
    Resolve the device name to its full name.
    """
    if device in config:
        return device
    else:
        candidates = [name for name in device_names(config) if name.startswith(device)]
        if len(candidates) == 1:
            return candidates[0]
        else:
            raise typer.BadParameter(f"Device '{device}' not found. Available devices: {', '.join(device_names(config))}")

@app.command()
def command(device: Annotated[Optional[str], typer.Argument(autocompletion=complete_devices)] = None,
            command: Annotated[Optional[str], typer.Argument(autocompletion=complete_commands)] = None):
    if device is None:
        show_device_info()
        return 0
    device = resolve_device(device)
    commands = config[device].get("commands", {})
    if command is None:
        command = config[device].get("default")
    if command is None:
        command = first(commands, default="Status")
    if command in commands:
        cmnd = commands[command]
    else:
        cmnd = command
    url = config[device].get("url")
    response = httpx.get(url, params={"cmnd": cmnd})
    if response.is_success:
        msg = format_response(device, command, response.json())
        get_console().print(f"[bold green]{config[device].get("description", device)}[/bold green]: {msg}")
    else:
        get_console().print(f"[bold red]Error:[/bold red] {response.status_code} - {response.text}")
        return 1