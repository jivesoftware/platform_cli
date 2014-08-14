#!/usr/bin/env python
# Copyright (C) 2013 Jive Software. All rights reserved.

"""Utilities for managing mustache template substitutions.

We want to be able to use dots as separators in our .properties file keys. We
need to transform those dots to something else (triple-underscores) during the
substitution process so those dots are not interpreted by pystache as attribute
references.
"""

import pystache
import re


class Error(Exception):
  """Base exception class for this module."""


def _modified_dict_keys_and_values(adict, func):
  """Get a new dictionary with key and value strings modified by func."""
  return dict((func(key), func(value)) for key, value in adict.iteritems())


def _modified_dict_keys(adict, func):
  """Get a new dictionary with key strings modified by func."""
  return dict((func(key), value) for key, value in adict.iteritems())


def _dots_to_triple_under(astring):
  """Convert all instances of '.' to '___'."""
  return re.sub(r'\.', '___', astring)


def _triple_under_to_dots(astring):
  """Convert all instances of '___' to '.'."""
  return re.sub(r'___', '.', astring)


class Renderer(object):
  """Wrapper around a pystache renderer."""

  def __init__(self, value_map):
    """Initialize renderer with the substitution map."""
    self.value_map = _modified_dict_keys(value_map, _dots_to_triple_under)
    self.renderer = pystache.Renderer(missing_tags='strict', escape=lambda x: x)

  def render(self, element):
    """Render a string template."""
    subbed = _dots_to_triple_under(element)
    try:
      rendered = self.renderer.render(subbed, self.value_map)
    except pystache.context.KeyNotFoundError, err:
      raise Error('Template key not found for "{}":\n{}'.format(element, err))
    unsubbed_and_rendered = _triple_under_to_dots(rendered)
    return unsubbed_and_rendered


def render_values_in_template_map(value_map, max_substitution_runs=10):
  """Populate templated values in template map through successive runs.

  For example, start with a dictionary that maps these values:
    main.home = /opt/myplatform
    fooservice.home = {{main.home}}/fooservice
    fooservice.bin = {{fooservice.home}}/bin

  And end with:
    main.home = /opt/myplatform
    fooservice.home = /opt/myplatform/fooservice
    fooservice.bin = /opt/myplatform/fooservice/bin

  We only support nested substitutions up to a certain number of iterations,
  max_substitution_runs, to avoid never-ending cycles.
  """
  previous_run = _modified_dict_keys_and_values(value_map,
                                                _dots_to_triple_under)
  this_run = {}
  for _ in range(max_substitution_runs):
    renderer = Renderer(previous_run)
    for key, value in previous_run.iteritems():
      try:
        this_run[key] = renderer.render(value)
      except pystache.context.KeyNotFoundError, err:
        raise Error('Template key not found for "{}":\n{}'.format(value, err))
    if set(previous_run.items()) == set(this_run.items()):
      break
    previous_run = this_run
    this_run = {}
  else:
    raise Error('Could not substitute variable values after {} runs.'.format(
                max_substitution_runs))

  return _modified_dict_keys_and_values(this_run, _triple_under_to_dots)
