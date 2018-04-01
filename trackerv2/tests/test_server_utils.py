from __future__ import absolute_import
import unittest

from ..server import utils


class TestServerUtils(unittest.TestCase):

    def test_checkuuid(self):
        self.assertEqual(
            utils.genuuid('192.168.1.1'),
            '91b37835-d2a6-5c0b-9585-122d57ec4694',
            'UUID not equal')


if __name__ == '__main__':
    unittest.main()
