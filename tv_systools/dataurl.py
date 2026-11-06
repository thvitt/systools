from base64 import b64encode, urlsafe_b64encode, b64decode
import base64
from cmath import isinf
import re
import sys
from mimetypes import guess_extension
from pathlib import Path
from typing import Annotated
from urllib.parse import quote_from_bytes, unquote
from xdg import Mime

from cyclopts import App, Parameter
from cyclopts.types import StdioPath

app = App()

_urlchar = r"[^\s:/?#[]@!$&\'()*+,;]"
_token = r"[^]\s()<>@,;:\\\"?=[]+"

DATA_URL = re.compile(
    rf"data:(?P<mime>{_token}+(?:;{_token}={_token})?)?(?P<base64>;base64)?,(?P<data>{_urlchar}+)"
)


@app.command(alias="-d")
def decode(
    url: str | None = None,
    out: Annotated[Path | None, Parameter(alias="-o")] = None,
    add_extension: Annotated[bool, Parameter(alias="-x")] = False,
    strict: bool = False,
):
    """
    Decode a data: url.

    Args:
        url: The url to decode. If missing, read from stdin.
        out: The file in which to save the data. If missing, write to stdout.
        add_extension: If we create a file, add a suitable extension for the MIME type in the url.
    """
    if url is None:
        url = sys.stdin.read().strip()

    assert url is not None
    match = DATA_URL.match(url)
    if match:
        mime = match["mime"] or "text/plain;charset=US-ASCII"
        data_ = match["data"]
        b64 = match["base64"]

    else:
        if strict:
            raise ValueError(f"'{url}' is not a data URL.")

        # try to decode manually
        mime, data_ = url[5:].split(",")
        b64 = mime.endswith(";base64")
        if b64:
            mime = mime[:-7]

    if b64:
        data = base64.urlsafe_b64decode(data_)
    else:
        data = unquote(data_).encode("utf-8")

    if out:
        if add_extension:
            extension = guess_extension(mime)
            if extension:
                out = out.with_suffix(extension)
        out.write_bytes(data)
    else:
        sys.stdout.buffer.write(data)


@app.default
def encode(
    src: str = "-", /, *, mime: Mime.MIMEtype | None = None, base64: bool | None = None
):
    """
    Encode data to a data: URL. The URL is output to stdout afterwards.

    Args:
        src: What to encode. This can either be `-` to read from stdin (the default), the path to an existing file to read from that, or directly the data.
        mime: The data's MIME type. If missing, we guess.
        base64: Force encoding using base64. If missing, we decide by final length.
    """
    filename = None
    if src == "-":
        data = sys.stdin.buffer.read()
    elif (file := Path(src)).exists():
        data = file.read_bytes()
        filename = file
    else:
        data = src.encode()

    defaulttype = Mime.MIMEtype("text", "plain")
    if mime is None:
        if filename:
            mime = Mime.get_type2(filename)
        else:
            mime = Mime.get_type_by_data(data)
    mime = mime or defaulttype

    if base64 is None:
        b64enc = urlsafe_b64encode(data)
        qdata = quote_from_bytes(data)
        base64 = len(b64enc) + 7 < len(qdata)
        encoded = b64enc if base64 else qdata
    elif base64:
        encoded = urlsafe_b64encode(data)
    else:
        encoded = quote_from_bytes(data)

    if isinstance(encoded, bytes):
        encoded = encoded.decode()

    url = f"data:{mime if mime != defaulttype else ''}{';base64' if base64 else ''},{encoded}"
    print(url)
