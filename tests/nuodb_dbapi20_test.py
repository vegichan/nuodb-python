#!/usr/bin/env python

import unittest

from . import dbapi20
from .nuodb_base import NuoBase


class test_NuoDB(NuoBase, dbapi20.DatabaseAPI20Test):
    def setUp(self):
        dbapi20.DatabaseAPI20Test.setUp(self)

    def tearDown(self):
        dbapi20.DatabaseAPI20Test.tearDown(self)

    # Unsupported tests
    def test_nextset(self): pass

    def test_setoutputsize(self): pass

    def test_callproc(self): pass


if __name__ == '__main__':
    unittest.main()
