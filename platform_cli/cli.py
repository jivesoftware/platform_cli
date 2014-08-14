#!/usr/bin/env python
# Copyright (C) 2013 Jive Software. All rights reserved.

"""Glue the config to the service profiles and make command line interface."""

import collections
import subprocess
import sys
import time
import textwrap
from platform_cli import config
from clint.textui import puts, indent


class CLI(object):
  """Provide a command line interface for starting and stopping services."""

  #pylint: disable=too-many-arguments
  def __init__(self, progname, overrides_path, defaults, suggestions, docs, service_profiles,
               os_requirements):

    self.progname = progname
    self.conf = config.Config(overrides_path, defaults, suggestions, docs)
    self.template_values, self.different_suggestions, _ = self.conf.get_active_values_and_metadata()

    self.os_requirements = os_requirements

    for service in service_profiles:
      service.assign_template_values(self.template_values)

    self.services_by_name = collections.OrderedDict(
        (service.name, service) for service in sorted(service_profiles,
                                                      key=lambda x: x.priority)
    )

  def add_subcommands(self, subparsers):
    """Add subparsers for the operation of the CLI."""

    def add_service_name_argument(parser):
      """Standardize the way we set service_name as an argument."""
      parser.add_argument('service_name', nargs='?', default=None,
                          choices=self.services_by_name.keys(),
                         )

    start_parser = subparsers.add_parser('start', help='start service(s)')
    add_service_name_argument(start_parser)
    start_parser.add_argument('--skip-setup', action='store_true')
    start_parser.set_defaults(func=self.start)

    stop_parser = subparsers.add_parser('stop', help='stop service(s)')
    add_service_name_argument(stop_parser)
    stop_parser.set_defaults(func=self.stop)

    restart_parser = subparsers.add_parser('restart', help='restart service(s)')
    restart_parser.add_argument('--graceful', action='store_true')
    restart_parser.add_argument('--skip-setup', action='store_true')
    add_service_name_argument(restart_parser)
    restart_parser.set_defaults(func=self.restart)

    status_parser = subparsers.add_parser('status',
                                          help='get status for service(s)')
    add_service_name_argument(status_parser)
    status_parser.add_argument('--verbose', '-v', action='store_true')
    status_parser.set_defaults(func=self.status)

    enable_parser = subparsers.add_parser('enable', help='enable a service')
    enable_parser.add_argument('service_name',
                               choices=self.services_by_name.keys())
    enable_parser.set_defaults(func=self.conf.enable)

    disable_parser = subparsers.add_parser('disable',
                                           help='disable a service')
    disable_parser.add_argument('service_name',
                                choices=self.services_by_name.keys())
    disable_parser.set_defaults(func=self.conf.disable)

    list_parser = subparsers.add_parser('list',
                                        help='list startup properties')
    list_parser.add_argument('--verbose', '-v', action='store_true')
    list_parser.add_argument('--as-props', '-p', action='store_true')
    list_parser.add_argument('substring_match', nargs='?', default=None)
    list_parser.set_defaults(func=self.conf.list_vars)

    set_parser = subparsers.add_parser('set',
                                       help='set startup property override',
                                       usage=('%(prog)s [-h] property_name property_value\n\n'
                                              'If the property value starts with a dash, surround '
                                              'it with quotes\nand add a space at the beginning, '
                                              'i.e. " -Dmyoption".'))
    set_parser.add_argument('property_name')
    set_parser.add_argument('property_value')
    set_parser.set_defaults(func=self.conf.set_var)

    delete_parser = subparsers.add_parser(
        'del', help='delete startup property override')
    delete_parser.add_argument('property_name')
    delete_parser.set_defaults(func=self.conf.delete_var)

    doc_parser = subparsers.add_parser(
        'doc', help='get documentation on each startup property')
    doc_parser.set_defaults(func=self.conf.show_docs)

    setup_parser = subparsers.add_parser(
        'setup', help='check OS-level and service requirements')
    add_service_name_argument(setup_parser)
    setup_parser.set_defaults(func=self.setup)

    snap_parser = subparsers.add_parser(
        'snap', help='take performance snapshots')
    snap_parser.add_argument('--count', '-c', default=1, type=int)
    snap_parser.add_argument('--interval', '-i', default=3, type=int)
    snap_parser.add_argument('--output', '-o')
    add_service_name_argument(snap_parser)
    snap_parser.set_defaults(func=self.snap)

  def start(self, args):
    """Start all enabled services in priority order."""
    persistent_skip_setup = self.template_values.get('main.skip_setup')
    if not args.skip_setup and not persistent_skip_setup in ('True', 'true', '1'):
      setup_ok = self.setup(args)
      if not setup_ok:
        puts('\nTo ignore setup checks, use --skip-setup or set an override for main.skip_setup.')
        sys.exit(1)
    if args.service_name is None:
      for service in self.services_by_name.values():
        if service.enabled:
          service.start()
    else:
      self.services_by_name[args.service_name].start()
    puts('To view listening ports, run "{} status -v".'.format(self.progname))

  def stop(self, args):
    """Stop all running services in reverse priority order."""
    if args.service_name is None:
      for service in self.services_by_name.values()[::-1]:
        service.stop()
    else:
      self.services_by_name[args.service_name].stop()

  def restart(self, args):
    """Restart all enabled services."""
    if args.graceful:
      if args.service_name is None:
        for service in self.services_by_name.values():
          if service.enabled:
            service.graceful()
      else:
        self.services_by_name[args.service_name].graceful()
    else:
      self.stop(args)
      self.start(args)

  def status(self, args):
    """Show status for all enabled services."""
    if args.service_name is None:
      for service in self.services_by_name.values():
        service.status(args.verbose)
    else:
      self.services_by_name[args.service_name].status(args.verbose)


  def _get_setup_steps(self, services):
    """If any setup steps are required, generate some user output in a dictionary."""
    setup_steps = collections.OrderedDict()
    if self.os_requirements:
      for title, steps in self.os_requirements.iteritems():
        setup_steps[title] = steps

    if not any((srv.enabled for srv in services)):
      title = 'Enable services before starting them:'
      setup_steps[title] = [('Enable the desired services with '
                             '\'{} enable <servicename>\'.'.format(self.progname))]
    for service in services:
      if service.enabled:
        for func in service.prop_validation_functions:
          title = func(self.template_values)
          if title:
            setup_steps[title] = []

    if self.different_suggestions:
      for suggestion in self.different_suggestions.values():
        setup_steps.setdefault(suggestion.why, [])
        if suggestion.value.startswith('-'):
          val = '" {} "'.format(suggestion.value)
        else:
          val = '"{}"'.format(suggestion.value)
        setup_steps[suggestion.why].append(
            '\n{} set {} {}\n    (current value: {})'.format(
            self.progname, suggestion.name, val, self.template_values[suggestion.name])
        )
    return setup_steps


  def setup(self, args):
    """Report on OS-level and service reqs, returning True if setup is complete."""
    if args.service_name is None:
      services = [srv for srv in self.services_by_name.values() if srv.enabled]
    else:
      services = [self.services_by_name[args.service_name],]
    setup_steps = self._get_setup_steps(services)
    if setup_steps:
      puts('Setup required.')
      for title, steps in setup_steps.iteritems():
        puts()
        puts('\n'.join(textwrap.wrap(title)))
        for step in steps:
          with indent(4):
            puts(step)
      return False
    else:
      puts('Setup OK.')
      return True

  def snap(self, args):
    """Return a performance snapshot."""
    if args.service_name is None:
      services = [srv for srv in self.services_by_name.values()]
    else:
      services = [self.services_by_name[args.service_name],]
    system_info_cmd = self.template_values.get('main.system_info_cmd')
    for iteration in range(1, args.count + 1):
      if system_info_cmd:
        if args.output:
          out = open(args.output, 'a+')
        else:
          out = sys.stdout
        out.write('[{}] System info #{}. Running: {}.\n'.format(
                  time.strftime('%Y-%m-%d %H:%M:%S'), iteration, system_info_cmd))
        out.flush()
        subprocess.call(system_info_cmd, shell=True, stdout=out, stderr=out)
        if args.output:
          out.close()
      for svc in services:
        svc.snap(iteration, args.output)
      if iteration != args.count:
        time.sleep(args.interval)
