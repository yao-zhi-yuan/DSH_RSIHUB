import unittest
from module import summarize_jsonl

class Visible(unittest.TestCase):
    def test_valid(self): self.assertEqual(summarize_jsonl('{"value":2}\n'), {'valid': 1, 'invalid': 0, 'total_value': 2})

if __name__ == '__main__': unittest.main()
