#!/usr/bin/env python3
# coding:utf-8

from email.message import Message
from email.parser import BytesParser
from email.policy import default


def parse_header(line):
    line = line or ""

    message = Message()
    message["content-type"] = line

    params = message.get_params(header="content-type") or []
    value = params[0][0] if params else ""
    options = {}
    for key, item in params[1:]:
        options[key] = item

    return value, options


def parse_multipart(fp, pdict):
    boundary = pdict.get("boundary")
    if not boundary:
        return {}

    if isinstance(boundary, str):
        boundary_bytes = boundary.encode("ascii")
    else:
        boundary_bytes = boundary

    content_length = int(pdict.get("CONTENT-LENGTH", 0) or 0)
    body = fp.read(content_length) if content_length else b""

    header = (
        b"Content-Type: multipart/form-data; boundary="
        + boundary_bytes
        + b"\r\nMIME-Version: 1.0\r\n\r\n"
    )
    message = BytesParser(policy=default).parsebytes(header + body)

    form = {}
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue

        payload = part.get_payload(decode=True)
        if payload is None:
            payload = b""

        form.setdefault(name, []).append(payload)

    return form
