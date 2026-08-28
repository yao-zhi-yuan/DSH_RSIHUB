import unittest
from module import safe_relative_path

class Visible(unittest.TestCase):
    def test_basic(self): self.assertEqual(safe_relative_path('./a/b'), 'a/b')

if __name__ == '__main__': unittest.main()
