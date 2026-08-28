import unittest
from module import chunks

class Visible(unittest.TestCase):
    def test_list(self): self.assertEqual(chunks([1, 2, 3], 2), [[1, 2], [3]])

if __name__ == '__main__': unittest.main()
