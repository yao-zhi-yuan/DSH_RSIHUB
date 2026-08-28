import unittest
from module import redact

class Visible(unittest.TestCase):
    def test_token(self): self.assertEqual(redact('token=abc'), 'token=[REDACTED]')

if __name__ == '__main__': unittest.main()
