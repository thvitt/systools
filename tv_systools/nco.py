from os import fspath
import socket
from pathlib import Path
from typing import Optional
from xdg.BaseDirectory import get_runtime_dir
from functools import cached_property
from cyclopts import App

app = App()
app.register_install_completion_command(add_to_startup=False)


class NextcloudSocket:
    sock: socket.socket

    def __init__(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        socket_path = Path(get_runtime_dir(), "Nextcloud", "socket")
        self.sock.connect(fspath(socket_path))
        self.sock.settimeout(1)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.sock.close()

    def command(self, command: str) -> None:
        if not command.endswith("\n"):
            command += "\n"
        self.sock.sendall(command.encode())

    def receive(self) -> str:
        result = b""
        try:
            while True:
                result += self.sock.recv(1024)
        except TimeoutError:
            return result.decode()

    @cached_property
    def paths(self) -> set[Path]:
        self.command("VERSION:")
        resp = self.receive()
        result = set()
        for line in resp.splitlines():
            key, value = line.split(":", 1)
            if key == "REGISTER_PATH":
                result.add(Path(value))
        return result

    def is_managed(self, path: Path | str) -> bool:
        abs = Path(path).resolve()
        return any(abs.is_relative_to(root) for root in self.paths)

    def open_in_browser(self, path: Path | str) -> None:
        if not self.is_managed(path):
            raise ValueError(f"{path} is not in a NextCloud managed folder")
        else:
            self.command(f"OPEN_PRIVATE_LINK:{fspath(path)}")


@app.default
def main(path: Optional[Path]):
    """
    Open the given NextCloud path in the browser.
    """
    with NextcloudSocket() as nc:
        if path is None:
            path = Path()
        nc.open_in_browser(path)


if __name__ == "__main__":
    app()
