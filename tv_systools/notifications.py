from subprocess import run
import json
from rich.table import Table
from rich import get_console
import re


def simplify_json(data):
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            if isinstance(value, dict) and "data" in value:
                result[key] = simplify_json(value["data"])
            else:
                result[key] = value
        return result
    else:
        return data


def pango2markup(text):
    text = re.sub(r"<b>(.*?)</b>", r"[bold]\1[/bold]", text)
    text = re.sub(r"<i>(.*?)</i>", r"[italic]\1[/italic]", text)
    text = re.sub(r"<.*?>", "", text)
    return text


def history():
    proc = run(["dunstctl", "history"], capture_output=True)
    text = proc.stdout
    data = json.loads(text)
    return data["data"][0]


def history_table():
    table = Table(title="Notification History", box=None)
    table.add_column("ID", justify="right", style="cyan", no_wrap=True)
    table.add_column("App", style="magenta")
    table.add_column("Summary", style="green")
    table.add_column("Body")

    for notification_ in history():
        notification = simplify_json(notification_)
        table.add_row(
            str(notification["id"]),
            notification["appname"],
            notification["summary"],
            pango2markup(notification["body"]),
        )

    return table


if __name__ == "__main__":
    get_console().print(history_table())
