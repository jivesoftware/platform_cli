#!/usr/bin/env python
# Copyright (C) 2013 Jive Software. All rights reserved.

import logging
import mock
import os
import StringIO
import sys
import unittest

from platform_cli import config, protected_file_path


def get_mock_open_func(file_contents_map=None, exceptions_map=None):

  class ContextStringIO(StringIO.StringIO):
    """StringIO needs context manager methods to mock return values for open().
    """
    def __enter__(self):
      return self
    def __exit__(self, exception_type, exception_value, traceback):
      pass

  def mock_open(fname, flags):
    if file_contents_map is not None and fname in file_contents_map:
      return ContextStringIO(file_contents_map[fname])
    elif exceptions_map is not None and fname in exceptions_map:
      raise exceptions_map[fname]
    else:
      raise IOError

  return mock_open
  
 
class TestConfig(unittest.TestCase):

  def setUp(self):
    logging.basicConfig( stream=sys.stderr )
    self.logger = logging.getLogger('TestConfig')
    self.logger.setLevel(logging.DEBUG)

  def testGetActiveValuesAndMetadata(self):
    """Mock the get_overrides func and just test logic."""
    defaults = [
        config.Default('main.home', '/opt/myplatform'),
        config.Default('fooservice.home', '{{main.home}}/fooservice'),
        config.Default('fooservice.bin', '{{fooservice.home}}/bin'),
        config.Default('barservice.max_heap_size', '1024'),
        config.Default('barservice.foo.endpoint', 'http://dev.example.com'),
    ]
    overrides = [
        config.Override('barservice.foo.endpoint', 'http://dev.example.com'),
        config.Override('main.home', '/opt/apps/myplatform'),
    ]
    suggestions = [
        config.Suggestion(
            'barservice.max_heap_size', '2048',
            'It looks like your OS can support giving BarService more memory.'
        ),
        config.Suggestion(
            'barservice.foo.endpoint', 'http://dev.example.com',
            'This suggestion not seen because it is already the active value.'
        )

    ]

    expected_active_values = {'main.home': '/opt/apps/myplatform',
                              'fooservice.home': '/opt/apps/myplatform/fooservice',
                              'fooservice.bin': '/opt/apps/myplatform/fooservice/bin',
                              'barservice.max_heap_size': '1024',
                              'barservice.foo.endpoint': 'http://dev.example.com'}
    expected_different_suggestions = {
        'barservice.max_heap_size': config.Suggestion(
            'barservice.max_heap_size', '2048',
            'It looks like your OS can support giving BarService more memory.'
        )
    }
    expected_different_defaults = {'main.home': config.Default('main.home', '/opt/myplatform')}

    overrides_mock = mock.MagicMock()
    config_cli = config.Config('test.properties',
                               defaults=defaults, suggestions=suggestions)
    config_cli.get_overrides = mock.MagicMock()
    config_cli.get_overrides.return_value = overrides
    active_values, diff_suggestions, diff_defaults = config_cli.get_active_values_and_metadata()


    def comparable(d):
      return set(d.items())
      
    self.logger.debug('{} == {}'.format(comparable(active_values), comparable(expected_active_values)))
    self.assertTrue(comparable(active_values) == comparable(expected_active_values))
    self.logger.debug('{} == {}'.format(comparable(diff_suggestions), comparable(expected_different_suggestions)))
    self.assertTrue(comparable(diff_suggestions) == comparable(expected_different_suggestions))
    self.logger.debug('{} == {}'.format(comparable(diff_defaults), comparable(expected_different_defaults)))
    self.assertTrue(comparable(diff_defaults) == comparable(expected_different_defaults))

        
  def testGetOverrides(self):
    file_contents_map = {
        'test.properties': ('foo.first = 1\n'
                            '# Random comment = Not included.\n'
                            'foo.second = Two\n'
                            'foo.third = Three\n'
                            '  !!\n'),
    }

    properties_expected = [config.Override('foo.first', '1'),
                           config.Override('foo.second', 'Two'),
                           config.Override('foo.third', 'Three\n!!')]

    open_mock = mock.MagicMock(side_effect=get_mock_open_func(file_contents_map))
    exists_mock = mock.MagicMock()
    protected_fp_mock = mock.MagicMock()
    mock.patch('protected_file_path.ProtectedFilePath', mock.MagicMock())
    with mock.patch('__builtin__.open', open_mock), mock.patch('os.path.exists', exists_mock):
      exists_mock.return_value = False
      conf = config.Config('test.properties')
      config_items = conf.get_overrides()
      open_mock.assert_has_calls([mock.call('test.properties', 'w'),
                                  mock.call('test.properties', 'r')])
      exists_mock.assert_has_calls([mock.call('test.properties')])
      self.logger.debug('{} == {}'.format(config_items, properties_expected))
      self.assertTrue(set(config_items) == set(properties_expected))
      
