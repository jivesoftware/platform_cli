#!/usr/bin/env python
# Copyright (C) 2013 Jive Software. All rights reserved.

"""High-level functions for manipulating a .properties file.
"""

import ConfigParser
import itertools
import os
import StringIO

FAKE_SECTION_NAME = 'fake_section'


class Error(Exception):
  """Base exception class for this module."""


class _AsPropsFile(object):
  """Read a .properties file with ConfigParser.

  Fake a section heading so that ConfigParser can read the .properties file
  as an .ini file.
  """

  def __init__(self, file_obj, section_name='asection', allow_multiline_values=True):
    """Initialize the AsPropsFile .properties file wrappper."""

    section_head = '[{}]\n'.format(section_name)
    self.conf_lines = itertools.chain((section_head,), file_obj, ('',))
    self.allow_multiline_values = allow_multiline_values

  def readline(self):
    """Provide a readline method for readfp to call."""
    line = self.conf_lines.next()
    if not self.allow_multiline_values:
      line = line.lstrip(' \t')
    return line


def _open_props(file_path, create_new=False, allow_multiline_values=True):
  """Get a ConfigParser object with the contents of a .properties file."""
  conf = ConfigParser.ConfigParser()
  conf.optionxform = str # Otherwise ConfigParser auto-converts to lower.
  if create_new and not os.path.exists(file_path):
    try:
      with open(file_path, 'w') as _:
        pass
    except IOError, err:
      raise Error('Cannot create file at {}:\n{}'.format(
                  file_path, err))
  try:
    with open(file_path, 'r') as file_obj:
      conf.readfp(_AsPropsFile(file_obj, FAKE_SECTION_NAME, allow_multiline_values))
  except IOError, err:
    raise Error('Cannot open file at {}:\n{}'.format(
                file_path, err))
  return conf


def _edit_props(file_path, mutation_func, create_new=False):
  """Safe edit to a .properties config file."""
  conf = _open_props(file_path, create_new)
  mutation_func(conf)
  memoryfile = StringIO.StringIO()
  conf.write(memoryfile)
  temp_path = file_path + '.temp'
  try:
    with open(temp_path, 'w') as temp_conf_file:
      for line in memoryfile.getvalue().split('\n')[1:]:
        temp_conf_file.write('{}\n'.format(line))
  except IOError, err:
    raise Error('Cannot write to temp config file at {}:\n{}'.format(
                temp_path, err))
  try:
    os.rename(temp_path, file_path)
  except OSError, err:
    raise Error('Cannot rename file {} to {}:\n{}'.format(
                temp_path, file_path, err))


def get_items(file_path, create_new=False, allow_multiline_values=True):
  """Return a list of tuples in a .properties file."""
  conf = _open_props(file_path, create_new, allow_multiline_values)
  return conf.items(FAKE_SECTION_NAME)


def set_key(file_path, key, value, create_new=False):
  """Set key to value in a .properties file."""
  _edit_props(file_path,
              lambda x: x.set(FAKE_SECTION_NAME, key, value),
              create_new)

def delete_key(file_path, key, create_new=False):
  """Delete a key from a .properties file."""
  _edit_props(file_path,
              lambda x: x.remove_option(FAKE_SECTION_NAME, key),
              create_new)
