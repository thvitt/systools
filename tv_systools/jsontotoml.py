import json
from cyclopts import App
import toml
from pathlib import Path

app = App()
app.register_install_completion_command(add_to_startup=False)


def denull(data, replacement=None):
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            if value is None:
                if replacement is not None:
                    result[key] = replacement
            else:
                result[key] = denull(value, replacement)
        return result
    elif isinstance(data, list):
        result = []
        for item in data:
            if data is None:
                if replacement is not None:
                    result.append(replacement)
            else:
                result.append(denull(item, replacement))
        return result
    elif data is None:
        if replacement is not None:
            return replacement
        else:
            raise ValueError("Cannot have None value in data")
    else:
        return data


@app.default
def convert(json_file: Path, toml_file: Path, null_replacement=None):
    with open(json_file, "r") as f:
        data = json.load(f)
    if isinstance(data, list):
        if len(data) == 1:
            data = data[0]
        else:
            data = {json_file.stem: "data"}

    data = denull(data, null_replacement)

    with open(toml_file, "w") as f:
        toml.dump(data, f)
