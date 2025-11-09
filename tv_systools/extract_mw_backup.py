from lxml import etree
from pathlib import Path
from mimetypes import guess_extension
from cyclopts import App

app = App()
app.register_install_completion_command(add_to_startup=False)


@app.default
def main(export_xml: Path, output_folder: Path):
    """
    Extracts pages from a MediaWiki XML backup file.

    Args:
        export_xml: The MediaWiki XML backup file.
        output_folder: The folder where the pages will be extracted. Will be created if it doesn't exist.
    """
    backup = etree.parse(export_xml)
    ns = {"mw": backup.getroot().nsmap.get(None)}

    namespaces = {
        el.get("key"): el.text for el in backup.xpath("//mw:namespace", namespaces=ns)
    }

    print("namespace", "format", "title", "file", sep="\t")
    for page in backup.xpath("//mw:page", namespaces=ns):
        title = page.find("mw:title", namespaces=ns).text
        content = page.find("mw:revision/mw:text", namespaces=ns).text
        if content:
            namespace = (
                namespaces.get(page.find("mw:ns", namespaces=ns).text, "Main") or "Main"
            )
            format = page.find("mw:revision/mw:format", namespaces=ns).text
            pagefile = (output_folder / namespace / title).with_suffix(
                guess_extension(format) or ".wiki"
            )
            print(namespace, format, title, pagefile, sep="\t")
            pagefile.parent.mkdir(parents=True, exist_ok=True)
            pagefile.write_text(content)
