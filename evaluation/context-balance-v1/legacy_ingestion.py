"""Bounded local input and deterministic chunks with original line numbers."""
import hashlib
import os
import stat
from pathlib import Path

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_LINE_BYTES = 8192
TARGET_CHUNK_BYTES = 1200
PARSER_VERSION = "text-lines-v1"


class IngestError(ValueError):
    """Source rejected before changing the index."""


def normalize(text):
    if not isinstance(text, str):
        raise IngestError("Text must be a string")
    if len(text.encode("utf-8")) > MAX_FILE_BYTES or "\x00" in text:
        raise IngestError("Input exceeds 2 MiB or contains NUL bytes")
    return text.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n")


def chunks(text):
    """Paragraphs, split only at whole source lines. No lossy trimming."""
    result, pending, start = [], [], 1
    def flush():
        if pending:
            result.append((start, start + len(pending) - 1, "\n".join(pending)))
            pending.clear()
    lines = text.split("\n")
    if len(lines) > 100_000:
        raise IngestError("Input exceeds 100000 source lines")
    for number, line in enumerate(lines, 1):
        if len(line.encode("utf-8")) > MAX_LINE_BYTES:
            raise IngestError("A source line exceeds 8192 bytes; wrap it before ingesting")
        if not line.strip():
            flush()
            continue
        if pending and (line.lstrip().startswith("#") or len(("\n".join(pending) + "\n" + line).encode("utf-8")) > TARGET_CHUNK_BYTES):
            flush()
        if not pending:
            start = number
        pending.append(line)
    flush()
    if not result or len(result) > 10_000:
        raise IngestError("Input is empty or exceeds 10000 chunks")
    return result


def read_permitted_file(path, roots):
    """Descriptor-relative reads reject symlinks in every descendant component.

    This POSIX path protects against descendant symlink swaps. The configured
    root and its ancestors remain trusted OS locations. Unsupported platforms
    fail explicitly; there is no silently weaker filesystem fallback.
    """
    requested = Path(os.path.abspath(Path(path).expanduser()))
    binding = next(((canonical, requested.relative_to(prefix)) for alias, canonical in roots
                    for prefix in (alias, canonical) if requested.is_relative_to(prefix)), None)
    if binding is None:
        raise IngestError("File is outside the configured permitted roots")
    approved, relative = binding
    selected = approved / relative
    if not relative.parts or selected.suffix.lower() not in {".txt", ".md", ".markdown"}:
        raise IngestError("Only local .txt, .md and .markdown files are supported")
    if not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd:
        raise IngestError("Safe descriptor-relative ingestion is unavailable on this platform")
    directory = None
    descriptor = None
    try:
        directory = os.open(approved, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        for part in relative.parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        descriptor = os.open(relative.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_FILE_BYTES:
            raise IngestError("Source must be a regular file of at most 2 MiB")
        with os.fdopen(descriptor, "rb") as source:
            descriptor = None
            raw = source.read(MAX_FILE_BYTES + 1)
            after = os.fstat(source.fileno())
        if len(raw) > MAX_FILE_BYTES:
            raise IngestError("Source exceeds 2 MiB")
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise IngestError("Source changed while being read; retry after the writer finishes")
        text = raw.decode("utf-8")
        return selected, text, hashlib.sha256(raw).hexdigest()
    except (OSError, UnicodeError) as exc:
        raise IngestError("Cannot safely read this UTF-8 regular file") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if directory is not None:
            os.close(directory)
