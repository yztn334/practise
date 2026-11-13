"""Discover PDF files and write a complete catalogue snapshot."""

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile


def _raise_walk_error(error: OSError) -> None:
    raise error


def find_pdfs(source: Path, recursive: bool) -> tuple[Path, list[Path]]:
    """Return the root for relative paths and the sorted PDFs to process."""
    if source.is_file():
        if source.suffix.lower() != ".pdf":
            raise ValueError(f"输入文件的扩展名必须是 .pdf：{source}")
        return source.parent, [source]

    if not source.is_dir():
        raise ValueError(f"输入路径不存在或无法读取：{source}")

    if recursive:
        candidates = (
            Path(directory) / name
            for directory, _, names in os.walk(source, onerror=_raise_walk_error)
            for name in names
        )
    else:
        candidates = source.iterdir()

    pdfs = [path for path in candidates if path.suffix.lower() == ".pdf" and path.is_file()]
    return source, sorted(pdfs, key=lambda path: (path.as_posix().casefold(), path.as_posix()))


def write_catalog(destination: Path, documents: list[dict], errors: list[dict]) -> None:
    """Replace the destination only after writing the whole JSON document."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": 1, "documents": documents, "errors": errors}
    temp_path = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temp_path = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        temp_path.replace(destination)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
