from fastapi import UploadFile


class UploadLimitError(ValueError):
    """Raised when an upload exceeds configured byte limits."""


class UploadDecodeError(ValueError):
    """Raised when uploaded text is not valid UTF-8."""


async def read_upload_text_bounded(
    upload: UploadFile,
    *,
    max_bytes: int,
    chunk_size: int,
) -> str:
    """Read a text upload incrementally, enforcing a byte limit before decoding."""
    effective_chunk_size = max(1, chunk_size)
    total_bytes = 0
    chunks: list[bytes] = []

    while True:
        chunk = await upload.read(effective_chunk_size)
        if not chunk:
            break
        total_bytes += len(chunk)
        if max_bytes > 0 and total_bytes > max_bytes:
            raise UploadLimitError(f"Uploaded file exceeds {max_bytes} bytes")
        chunks.append(chunk)

    try:
        return b"".join(chunks).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UploadDecodeError("Uploaded file must be valid UTF-8 text") from exc


async def read_uploads_text_bounded(
    uploads: list[UploadFile],
    *,
    max_file_bytes: int,
    max_total_bytes: int,
    max_files: int,
    chunk_size: int,
) -> list[tuple[str | None, str]]:
    """Read multiple uploads with per-file, total-byte, and file-count limits."""
    if max_files > 0 and len(uploads) > max_files:
        raise UploadLimitError(f"Too many uploaded files: {len(uploads)} exceeds limit {max_files}")

    total_bytes = 0
    decoded_uploads: list[tuple[str | None, str]] = []
    for upload in uploads:
        content = await read_upload_text_bounded(
            upload,
            max_bytes=max_file_bytes,
            chunk_size=chunk_size,
        )
        # UTF-8 text byte length is recomputed from decoded content so callers can enforce
        # an aggregate bound without retaining each original byte buffer.
        total_bytes += len(content.encode("utf-8"))
        if max_total_bytes > 0 and total_bytes > max_total_bytes:
            raise UploadLimitError(f"Uploaded files exceed {max_total_bytes} total bytes")
        decoded_uploads.append((upload.filename, content))

    return decoded_uploads
