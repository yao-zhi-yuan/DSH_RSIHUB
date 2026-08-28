import unittest
from module import unique_records

class Visible(unittest.TestCase):
    def test_first(self): self.assertEqual(unique_records([{'id': 1, 'v': 'a'}, {'id': 1, 'v': 'b'}], 'id'), [{'id': 1, 'v': 'a'}])

if __name__ == '__main__': unittest.main()
