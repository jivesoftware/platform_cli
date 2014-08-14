#!/usr/bin/env python
# Copyright (C) 2013 Jive Software. All rights reserved.

"""Context manager marking a path with a .lock directory for exclusive access.
"""

import os
import time


class Error(Exception):
  """Base exception class for this module."""


class ProtectedFilePath(object):
  """Context manager for exclusive access to a file path."""

  WAIT_INTERVALS_SEC = (0.1, 0.2, 0.3, 0.5, 0.7, 1.0)

  def __init__(self, file_path, noop=False):
    """Initialize the ProtectedFilePath context manager."""
    self.file_path = file_path
    self.lockdir_path = '{}.lock'.format(self.file_path)
    self.noop = noop

  def __enter__(self):
    """Control access to 'afile' using lock dir 'afile.lock'."""
    if not self.noop:
      for interval in self.WAIT_INTERVALS_SEC:
        try:
          os.mkdir(self.lockdir_path)
          break
        except OSError:
          time.sleep(interval)
      else:
        raise Error('Cannot create lock directory at {}.'.format(
                    self.lockdir_path))

  def __exit__(self, exception_type, exception_value, traceback):
    """On exit, remove the lock."""
    if not self.noop:
      try:
        os.rmdir(self.lockdir_path)
      except IOError, err:
        raise Error('Cannot remove lock directory at {}:\n{}'.format(
                    self.lockdir_path, err))

