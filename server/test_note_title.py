import os
import unittest

from note_title import MAX_LEN, VAULT_DIR, note_filename, note_path


class NoteFilenameTest(unittest.TestCase):
    def test_spaces_become_dashes(self):
        self.assertEqual(note_filename("Hello World"), "Hello-World.md")

    def test_long_title_is_capped_at_max_len(self):
        self.assertEqual(note_filename("a" * (MAX_LEN + 20)), "a" * MAX_LEN + ".md")

    def test_path_separators_cannot_escape_vault(self):
        for title in ("../outside", "/etc/passwd", "a/../../b", "..\\x"):
            path = note_path(title)
            self.assertEqual(os.path.dirname(path), VAULT_DIR, title)


if __name__ == "__main__":
    unittest.main()
