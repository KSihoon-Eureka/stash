"""Helpers for turning shared page titles into Obsidian note file names."""
import os

VAULT_DIR = os.path.expanduser("~/Obsidian/Stash")
MAX_LEN = 80


def note_filename(title):
    """Return a file name for a note titled `title`, at most MAX_LEN chars plus `.md`."""
    name = title.strip().replace(" ", "-")
    return name[:MAX_LEN + 1] + ".md"


def note_path(title):
    """Absolute path inside the vault for a note titled `title`."""
    return os.path.join(VAULT_DIR, note_filename(title))
