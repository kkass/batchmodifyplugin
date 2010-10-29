from trac.test import EnvironmentStub, Mock
from trac.log import logger_factory
from trac.config import Option, ListOption

import unittest
import logging

import web_ui

class BatchModifyTestCase(unittest.TestCase):
    
    def setUp(self):
        self._logger = logger_factory()
        self._fields_as_list = ['keywords']
        self._list_separator_regex = '[,\s]+'
        self._list_connector_string = ' '
        self._batchmod = web_ui.BatchModifier(self._fields_as_list, 
                                              self._list_separator_regex,
                                              self._list_connector_string)
    
    def test_merge_keywords_adds_new_keyword(self):        
        original_keywords = 'foo'
        new_keywords = 'bar'
        
        result = self._batchmod._merge_keywords(original_keywords, 
                                                new_keywords, self._logger)
        self.assertEqual('foo bar', result)
    
    def test_merge_keywords_removes_keyword(self):
        original_keywords = 'foo bar'
        new_keywords = '-bar'
        
        result = self._batchmod._merge_keywords(original_keywords,
                                                new_keywords, self._logger)
        self.assertEqual('foo', result)
    
    def test_merge_keywords_does_not_duplicate_keyword(self):
        original_keywords = 'foo'
        new_keywords = 'foo'
        
        result = self._batchmod._merge_keywords(original_keywords, 
                                                new_keywords, self._logger)
        self.assertEqual('foo', result)
    
    def test_merge_keywords_adds_multiple_keywords(self):
        original_keywords = 'foo'
        new_keywords = 'bar baz'
        
        result = self._batchmod._merge_keywords(original_keywords,
                                                new_keywords, self._logger)
        self.assertEqual('foo bar baz', result)
    
    def test_merge_keywords_removes_multiple_keywords(self):
        original_keywords = 'foo bar baz'
        new_keywords = '-foo -baz'
        
        result = self._batchmod._merge_keywords(original_keywords,
                                                new_keywords, self._logger)
        self.assertEqual('bar', result)
    
    def test_remove_resolution_if_not_closed_sets_resolution_to_empty_string_when_status_is_not_closed(self):
        values = {'status':'reopened'}
        self._batchmod._remove_resolution_if_not_closed(values)
        self.assertEqual('', values['resolution'])
    
    def test_remove_resolution_does_nothing_if_status_is_unchanged(self):
        values = {}
        self._batchmod._remove_resolution_if_not_closed(values)
        self.assertEqual({}, values)
    
    def test_remove_resolution_does_nothing_if_status_is_set_to_closed(self):
        values = {'status':'closed'}
        self._batchmod._remove_resolution_if_not_closed(values)
        self.assertFalse(values.has_key('resolution'))
    
    def test_check_for_resolution_sets_status_to_closed_if_resolution_is_set(self):
        values = {'resolution':'fixed'}
        self._batchmod._check_for_resolution(values)
        self.assertEqual('closed', values['status'])
        
    def test_check_for_resolution_does_nothing_if_no_resolution_set(self):
        values = {}
        self._batchmod._check_for_resolution(values)
        self.assertEqual({}, values)

def suite():
    return unittest.makeSuite(BatchModifyTestCase, 'test')

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
