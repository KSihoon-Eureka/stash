import os
import unittest

from note_title import MAX_BYTES, MAX_LEN, note_filename, note_path


class NoteFilenameTest(unittest.TestCase):
    def test_spaces_become_dashes(self):
        self.assertEqual(note_filename("Hello World"), "Hello-World.md")

    def test_long_title_is_capped_at_max_len(self):
        self.assertEqual(note_filename("a" * (MAX_LEN + 20)), "a" * MAX_LEN + ".md")

    def test_multibyte_title_fits_filesystem_byte_limit(self):
        name = note_filename("😀" * MAX_LEN)
        self.assertLessEqual(len(name.encode("utf-8")), MAX_BYTES)
        self.assertEqual(name, "😀" * 63 + ".md")

    def test_path_separators_cannot_escape_vault(self):
        vault = "/tmp/vault"
        for title in ("../outside", "/etc/passwd", "a/../../b", "..\\x"):
            path = note_path(vault, title)
            self.assertEqual(os.path.dirname(path), vault, title)


if __name__ == "__main__":
    unittest.main()
