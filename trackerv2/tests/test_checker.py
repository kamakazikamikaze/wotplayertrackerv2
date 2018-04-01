from __future__ import absolute_import
import unittest
import os
from tempfile import NamedTemporaryFile

from ..client import checker


class TestChecker(unittest.TestCase):

    def test_checksha1(self):
        f = NamedTemporaryFile(delete=False)
        try:
            f.write(b'a\nb\nc\nd\n')
            f.close()
            self.assertEqual(
                checker.getsha1(f.name),
                '1b4355ee62c132356630e714935aa5491c66974f',
                'SHA1 hash not equal')

        finally:
            os.unlink(f.name)


if __name__ == '__main__':
    unittest.main()
