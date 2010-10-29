import doctest
import unittest

import batchmod
from batchmod.tests import web_ui

def suite():
    suite = unittest.TestSuite()
    suite.addTest(web_ui.suite())
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
