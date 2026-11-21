"""Reading uploads for the web app, entirely in memory."""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

MAX_FILES = 300     # a season is rarely more than 100 episodes
MAX_FILE_MB = 5     # one screenplay is about 20 KB


def read_uploads(uploads, max_files: int = MAX_FILES, max_mb: float = MAX_FILE_MB) -> tuple[list[tuple[str, bytes]], list[str]]:
    """Turn uploaded .txt and .zip files into (name, bytes) pairs, in memory.

    uploads: objects with .name and .getvalue(), like Streamlit's UploadedFile.
    Returns the pairs and a list of notes about anything skipped. Never raises on bad input."""
    items, notes, seen = [], [], set()

    def add(name: str, data: bytes):
        if len(data) > max_mb * 1024 * 1024:
            notes.append(f"{name}: larger than {max_mb:g} MB, skipped")
        elif name in seen:
            notes.append(f"{name}: a file with this name was already uploaded, skipped")
        elif len(items) >= max_files:
            notes.append(f"{name}: more than {max_files} files, skipped")
        else:
            seen.add(name)
            items.append((name, data))

    for f in uploads:
        if f.name.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(f.getvalue())) as z:
                    for info in z.infolist():
                        name = Path(info.filename).name
                        if info.is_dir() or "__MACOSX" in info.filename or name.startswith("."):
                            continue
                        if not name.lower().endswith(".txt"):
                            continue
                        if info.file_size > max_mb * 1024 * 1024:   # check before unpacking
                            notes.append(f"{name}: larger than {max_mb:g} MB, skipped")
                        else:
                            add(name, z.read(info))
            except zipfile.BadZipFile:
                notes.append(f"{f.name}: not a readable zip file, skipped")
        else:
            add(Path(f.name).name, f.getvalue())
    return items, notes
