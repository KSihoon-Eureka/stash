import unittest

from note_title import note_filename


class NoteFilenameTest(unittest.TestCase):
    def test_spaces_become_dashes(self):
        self.assertEqual(note_filename("Hello World"), "Hello-World.md")


if __name__ == "__main__":
    unittest.main()
