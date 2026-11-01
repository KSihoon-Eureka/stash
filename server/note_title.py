"""Helpers for turning shared page titles into Obsidian note file names."""
import os

VAULT_DIR = os.path.expanduser("~/Obsidian/Stash")
MAX_LEN = 80
MAX_BYTES = 255  # APFS/HFS+ file name limit, in UTF-8 bytes
EXT = ".md"


def note_filename(title):
    """Return a file name for a note titled `title`, at most MAX_LEN chars plus `.md`."""
    name = title.strip().replace(" ", "-")
    # Path separators would let a shared title escape VAULT_DIR (or replace it, if absolute).
    name = name.replace("/", "-").replace("\\", "-")
    # Multi-byte titles (e.g. emoji) can exceed the byte limit within MAX_LEN chars;
    # "ignore" drops a code point cut in half by the byte slice.
    name = name[:MAX_LEN].encode("utf-8")[:MAX_BYTES - len(EXT)].decode("utf-8", "ignore")
    return name + EXT


def note_path(title):
    """Absolute path inside the vault for a note titled `title`."""
    return os.path.join(VAULT_DIR, note_filename(title))
