from itertools import count
from pathlib import Path
from typing import Annotated, Iterable, Literal, Mapping, MutableMapping
import sys

from lxml import etree
from cyclopts import App, Parameter

app = App()
app.register_install_completion_command(add_to_startup=False)

XSI_SL = "{http://www.w3.org/2001/XMLSchema-instance}schemaLocation"


def safe_update(
    mapping: MutableMapping,
    updates: Mapping,
    on_duplicate: Literal["suffix", "return"] = "suffix",
):
    result = {}
    for key, value in updates.items():
        if key not in mapping:
            mapping[key] = value
        elif mapping[key] != value:
            if on_duplicate == "suffix":
                for i in count():
                    cand = key + str(i)
                    if cand not in mapping:
                        mapping[cand] = value
                        break
                    elif mapping[cand] == value:
                        break
            else:
                result[key] = value
    return result


def tupelize[T](
    source: Iterable[T], n=2, on_rest: Literal["drop", "append", "fail"] = "drop"
) -> Iterable:
    cand = []
    i = 0
    for i, item in enumerate(source, start=1):
        cand.append(item)
        if i % n == 0:
            yield (tuple(cand))
            cand = []
    if cand:
        if on_rest == "append":
            yield cand
        elif on_rest == "fail":
            raise ValueError(
                f"Source with {i} items cannot be split into {n}-tuples, remainder: {cand}"
            )


@app.default()
def main(
    src: Path,
    /,
    dst: Annotated[Path | None, Parameter(["-o", "--output"])] = None,
    *,
    pretty: Annotated[bool, Parameter(["-p", "--pretty"])] = False,
):
    """
    Try to move all namespace declarations and xsi:schemaLocations to the root element of an XML document.

    Args:
        src: Input XML file
        dst: Output XML file, if missing, write to stdout
        pretty: pretty-print the resulting document
    """

    src_tree = etree.parse(src)
    src_root = src_tree.getroot()

    # collect namespaces and xsi:schemaLocation from all elements in the tree
    namespaces = {}
    locations = {}
    for el in src_tree.iter():
        safe_update(namespaces, el.nsmap)
        el_locs_raw = el.get(XSI_SL, "")
        el_locs = dict(tupelize(el_locs_raw.split())) if el_locs_raw else {}
        conflicts = safe_update(locations, el_locs)
        if conflicts:
            el.set(XSI_SL, "\n".join(f"{ns} {loc}" for ns, loc in conflicts.items()))
        else:
            el.attrib.pop(XSI_SL, "")

    dst_root = etree.Element(
        src_root.tag, src_root.attrib, nsmap=namespaces
    )  # typing: ignore
    if src_root.text:
        dst_root.text = src_root.text
    dst_root.extend(src_root.iterchildren())
    if locations:
        dst_root.set(XSI_SL, "\n".join(f"{ns} {loc}" for ns, loc in locations.items()))
    dst_tree = etree.ElementTree(dst_root)
    dst_tree.write(dst or sys.stdout.buffer, encoding="utf-8", xml_declaration=True)
