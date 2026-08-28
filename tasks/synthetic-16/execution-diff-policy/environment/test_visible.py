import unittest
from module import allowed_changes

class Visible(unittest.TestCase):
    def test_src(self): self.assertTrue(allowed_changes(['src/app.py']))
    def test_docs(self): self.assertFalse(allowed_changes(['README.md']))

if __name__ == '__main__': unittest.main()
