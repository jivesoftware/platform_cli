#!/usr/bin/env python
# Copyright (C) 2013 Jive Software. All rights reserved.

"""Define commands for managing processes.
"""
import getpass
import os
import shlex
import sys
import psutil
import time
from . import template, protected_file_path
from clint.textui import colored, puts


class Error(Exception):
  """Base exception class for this module."""


# pylint: disable=too-many-public-methods
# pylint: disable=too-many-instance-attributes,too-many-arguments
class SplitResult(str):
  """Template string that must be split after it is rendered."""


# pylint: disable=too-many-public-methods
# pylint: disable=too-many-instance-attributes,too-many-arguments
class SubstitutePropertyValue(str):
  """Wrapper to signify that we should use the property value of the given keyname."""


def wait_dots(wait_secs, proc):
  """Wait for wait_secs and print dots. Return True if proc stops running."""
  for _ in range(wait_secs):
    if not proc.is_running():
      return True
    sys.stdout.write('.')
    sys.stdout.flush()
    time.sleep(1)
  return False


class ServiceProfile(object):
  """Define how a service will be started and stopped.
  """
  # pylint: disable=too-many-locals
  def __init__(self,
               cli_name,
               name,
               process_name,
               start_cmd_tmpl,
               stop_cmd_tmpl=None,
               graceful_cmd_tmpl=None,
               env_tmpl=None,
               cwd_key=None,
               prop_validation_functions=None,
               pre_graceful_functions=None,
               pre_start_functions=None,
               runtime_template_key_functions=None,
               run_sigterm=True,
               run_sigkill=False,
               after_stop_cmd_seconds=5,
               after_sigterm_seconds=5,
               after_sigkill_seconds=5,
               external_pidfile_key=None,
               external_procname_key=None,
               ):
    """Initialize a ServiceProfile.

    Args:
      cli_name: The name that will identify stdout log entries.
      name: The name of the process used at the command line.
      process_name: Within the process list this becomes the first argument of
        the command line, making it easier to identify the process.
      start_cmd_tmpl: List of templatized args used to start the service.
      stop_cmd_tmpl: List of templatized args used to stop the service.
      graceful_cmd_tmpl: List of templatized args used to gracefully restart.
      env_tmpl: Dictionary mapping environment variables to templatized values.
      cwd_key: Template property pointing to the current working directory for
        start/stop commands to be run from.
      prop_validation_functions: List of functions which take the template dictionary
        as a single argument, and return a string if there is some issue.
      pre_graceful_functions: List of functions which take the template dictionary
        as a single argument, and perform some task prior to service graceful restart.
      pre_start_functions: List of functions which take the template dictionary
        as a single argument, and perform some task prior to service start.
      runtime_template_key_functions: Dictionary mapping a new template property
        to a value derived from a function at runtime. Each function must take the
        template dictionary as a single argument.
      run_sigterm: Send SIGTERM as a means to stop the process.
      run_sigkill: Send SIGKILL as a means to stop the process.
      after_stop_cmd_seconds: Seconds to wait after running the stop command,
        before sending SIGTERM.
      after_sigterm_seconds: Seconds to wait after sending SIGTERM, before
        sending SIGKILL.
      after_sigkill_seconds: Seconds to wait after sending SIGKILL, before
        signalling failure of the stop command.
      external_pidfile_key: Template property pointing to a pidfile path, for
        services which manage their own pidfiles.
      external_procname_key: Template property pointing to a process name, for
        services which manage their own pidfiles.
    """
    if not run_sigterm and not stop_cmd_tmpl:
      raise Error('Need to specify either run_sigterm or stop_cmd_tmpl.')
    self.cli_name = cli_name
    self.name = name
    self.process_name = process_name
    self.start_cmd_tmpl = start_cmd_tmpl
    self.stop_cmd_tmpl = stop_cmd_tmpl if stop_cmd_tmpl is not None else []
    self.graceful_cmd_tmpl = graceful_cmd_tmpl if graceful_cmd_tmpl is not None else []
    self.env_tmpl = env_tmpl if env_tmpl is not None else {}
    self.cwd_key = cwd_key
    self.prop_validation_functions = (prop_validation_functions
                                      if prop_validation_functions is not None else [])
    self.pre_graceful_functions = (pre_graceful_functions
                                if pre_graceful_functions is not None else [])
    self.pre_start_functions = (pre_start_functions
                                if pre_start_functions is not None else [])
    self.runtime_template_key_functions = (
        runtime_template_key_functions if runtime_template_key_functions else {}
    )
    self.run_sigterm = run_sigterm
    self.after_stop_cmd_seconds = after_stop_cmd_seconds
    self.run_sigkill = run_sigkill
    self.after_sigterm_seconds = after_sigterm_seconds
    self.after_sigkill_seconds = after_sigkill_seconds
    self.external_pidfile_key = external_pidfile_key
    self.external_procname_key = external_procname_key
    self.external_pidfile = None
    self.external_procname = None
    self.start_cmd = []
    self.stop_cmd = []
    self.graceful_cmd = []
    self.env = {}
    self.cwd = None
    self.values = {}
    self.stdout = None
    self.enabled = False
    self.pid_file = None
    self.priority = None
    self.snap_cmd = None
    self.start_wait_seconds = None

  # pylint: disable=too-many-branches
  def assign_template_values(self, template_values):
    """Apply template values including custom runtime values.
    """
    def render_cmd_from_tmpl(rend, tmpl):
      """Render template strings in a list.

      If a list element in the template is a SplitResult instance, we will
      expand the rendered result within the list we return.
      """
      cmd = []
      for val in tmpl:
        rendered_val = rend.render(val)
        if rendered_val:
          if isinstance(val, SplitResult):
            cmd.extend(shlex.split(rendered_val))
          else:
            cmd.append(rendered_val)
      return cmd

    self.values = template_values.copy()
    for key, func in self.runtime_template_key_functions.iteritems():
      if key not in self.values and not '___' in key and not ' ' in key:
        self.values[key] = func(self.values.copy())
    renderer = template.Renderer(self.values)
    self.start_cmd = render_cmd_from_tmpl(renderer, self.start_cmd_tmpl)
    self.stop_cmd = render_cmd_from_tmpl(renderer, self.stop_cmd_tmpl)
    self.graceful_cmd = render_cmd_from_tmpl(renderer, self.graceful_cmd_tmpl)
    self.env = dict([(key, renderer.render(val))
                    for key, val in self.env_tmpl.iteritems()])
    if self.cwd_key is not None:
      self.cwd = self.values[self.cwd_key]
    self.stdout = self.values['{}.stdout'.format(self.name)]
    self.priority = int(self.values['{}.priority'.format(self.name)])
    self.pid_file = os.path.join(self.values['main.pidfile_dir'],
                                 '{}.pid'.format(self.name))
    self.enabled = self.values['{}.enabled'.format(self.name)] in (
        'True', 'true', '1', 'on', 'yes')
    self.snap_cmd = self.values.get('{}.snap_cmd'.format(self.name))
    self.start_wait_seconds = int(self.values['main.start_wait_seconds'])
    if self.external_pidfile_key is not None:
      self.external_pidfile = self.values[self.external_pidfile_key]
    if self.external_procname_key is not None:
      self.external_procname = self.values[self.external_procname_key]
    if isinstance(self.after_stop_cmd_seconds, SubstitutePropertyValue):
      self.after_stop_cmd_seconds = int(self.values[self.after_stop_cmd_seconds])
    if isinstance(self.after_sigterm_seconds, SubstitutePropertyValue):
      self.after_sigterm_seconds = int(self.values[self.after_sigterm_seconds])
    if isinstance(self.after_sigkill_seconds, SubstitutePropertyValue):
      self.after_sigkill_seconds = int(self.values[self.after_sigkill_seconds])

  def _ensure_stdout_dirs_exist(self):
    """Make sure the directories under our stdout file exist."""
    stdout_dir = os.path.split(self.stdout)[0]
    if not os.path.exists(stdout_dir):
      os.makedirs(stdout_dir)

  def _get_process_name(self):
    """Get the process list version of the first arg in the command line."""
    if self.external_procname is not None:
      return self.external_procname
    else:
      return self.process_name

  def _get_pidfile(self):
    """Get the pid file path."""
    if self.external_pidfile is not None:
      return self.external_pidfile
    else:
      return self.pid_file

  def _is_externally_managed_process(self):
    """Return True if the pid file is externally managed."""
    if self.external_pidfile is not None:
      return True
    return False

  def _get_running_process_if_exists(self, delete_stale_pidfiles=False):
    """Find running proc based on pid file. Remove pid file if stale.

    Stale pid is if:
      * there's no process

      * there's a process but is neither a zombie nor does it match the
        username and command-line signature we expect.

    """
    pidfile_name = self._get_pidfile()
    process_name = self._get_process_name()

    if not delete_stale_pidfiles:
      noop = True
    else:
      noop = False

    with protected_file_path.ProtectedFilePath(pidfile_name, noop=noop):
      try:
        with open(pidfile_name, 'r') as pidfile:
          pid = int(pidfile.read().strip())
      except IOError:
        pid = None
      except ValueError:
        pid = None
        for proc in psutil.process_iter():
          if proc.name == os.path.basename(process_name):
            proc.kill()
        os.remove(pidfile_name)
      if pid is not None:
        try:
          proc = psutil.Process(pid)
        except psutil.error.NoSuchProcess:
          if delete_stale_pidfiles:
            os.remove(pidfile_name)
          return None
        if ((proc.username == getpass.getuser() and
             proc.cmdline and
             proc.cmdline[0] == process_name) or
            proc.status == psutil.STATUS_ZOMBIE):
          return proc
        else:
          if delete_stale_pidfiles:
            os.remove(pidfile_name)
          return None

  #pylint: disable=superfluous-parens
  def start(self):
    """Start the service."""
    proc = self._get_running_process_if_exists(delete_stale_pidfiles=True)
    pidfile_name = self._get_pidfile()
    if proc is not None:
      print('{} is already running.'.format(self.name))
    else:
      self._ensure_stdout_dirs_exist()
      with open(self.stdout, 'a') as stdout:
        with protected_file_path.ProtectedFilePath(pidfile_name):
          sys.stdout.write('Starting {}'.format(self.name))
          sys.stdout.flush()
          for func in self.pre_start_functions:
            func(self.values)
          stdout.write('[{}] {} starting {}:\n{}\n'.format(time.strftime('%Y-%m-%d %H:%M:%S'),
                                                           self.cli_name, self.name,
                                                           ' '.join(self.start_cmd)))
          stdout.flush()
          proc = psutil.Popen(args=([self.process_name] + self.start_cmd[1:]),
                              executable=self.start_cmd[0],
                              stdout=stdout,
                              stderr=stdout,
                              env=self.env,
                              cwd=self.cwd)
          if not self._is_externally_managed_process():
            with open(pidfile_name, 'w') as pid_file:
              pid_file.write(str(proc.pid))

        for _ in range(self.start_wait_seconds):
          sys.stdout.write('.')
          sys.stdout.flush()
          time.sleep(1)
        post_start_proc = self._get_running_process_if_exists(delete_stale_pidfiles=True)
        if post_start_proc is not None and post_start_proc.status != psutil.STATUS_ZOMBIE:
          puts(colored.green('process started.'))
          stdout.write('[{}] {} started process ({})\n'.format(time.strftime('%Y-%m-%d %H:%M:%S'),
                                                               self.cli_name, proc.pid))
          stdout.flush()
        else:
          puts(colored.red('no process found. See logs: {}'.format(self.stdout)))
          stdout.write('[{}] {} no process found after startup\n'.format(
                       time.strftime('%Y-%m-%d %H:%M:%S'), self.cli_name))
          stdout.flush()
          sys.exit(1)

  def status(self, verbose=False):
    """Print process status."""
    main_proc = self._get_running_process_if_exists()
    listening_str = ''
    running_pid = ''
    if main_proc is not None:
      running_pid = main_proc.pid
      if verbose:
        listening = []
        for proc in [main_proc] + main_proc.get_children():
          listening.extend([conn.local_address
                            for conn in proc.get_connections()
                            if conn.status == 'LISTEN'])

        listening_str = [':'.join([ip, str(port)]) for ip, port in listening]
        listening_str = 'listening={}'.format(','.join(list(set(listening_str))))
    output = ''.join((self.name.ljust(20),
                      'running' if running_pid else 'stopped',
                      '={}'.format(running_pid).ljust(17) if running_pid else ''.ljust(17),
                      'enabled'.ljust(10) if self.enabled else 'disabled'.ljust(10),
                      listening_str))
    if running_pid:
      puts(colored.green(output))
    else:
      puts(output)

  #pylint: disable=superfluous-parens
  def graceful(self):
    """If the service supports it, run graceful restart.

    Currently this assumes that the pid file is externally managed, for example
    by apachectl.
    """
    if not self.graceful_cmd:
      print('{} does not support graceful restart, skipping.'.format(self.name))
    else:
      proc = self._get_running_process_if_exists(delete_stale_pidfiles=True)
      pidfile_name = self._get_pidfile()
      if proc is not None:
        self._ensure_stdout_dirs_exist()
        with protected_file_path.ProtectedFilePath(pidfile_name):
          print('Gracefully restarting {} with:\n{}'.format(
                self.name, self.graceful_cmd))
          for func in self.pre_graceful_functions:
            func(self.values)
          with open(self.stdout, 'a') as stdout:
            # pylint: disable=unused-variable
            graceful_proc = psutil.Popen(args=self.graceful_cmd,
                                         stdout=stdout,
                                         stderr=stdout,
                                         env=self.env,
                                         cwd=self.cwd)

  def snap(self, iteration, output=None):
    """Create a performance snapshot of the service and dump to stdout."""
    proc = self._get_running_process_if_exists()
    pidfile_name = self._get_pidfile()
    if output is not None:
      out = open(output, 'a+')
    else:
      out = sys.stdout
    if self.snap_cmd and proc is not None and proc.status != psutil.STATUS_ZOMBIE:
      with protected_file_path.ProtectedFilePath(pidfile_name):
        snap_env = {'PID': str(proc.pid)}
        out.write('[{}] Snapshot #{} for {}. Running: {}. Environment: {}\n'.format(
                  time.strftime('%Y-%m-%d %H:%M:%S'), iteration,
                  self.name, self.snap_cmd, snap_env))
        out.flush()
        snap_proc = psutil.Popen(self.snap_cmd, env=snap_env, shell=True, stdout=out, stderr=out)
        if snap_proc.wait() != 0:
          out.write('Snapshot #{} for {} failed. Process {} may be hung.'.format(
                    iteration, self.name, proc.pid))
    if output is not None:
      out.close()

  def stop(self):
    """Stop the service."""
    proc = self._get_running_process_if_exists(delete_stale_pidfiles=True)
    pidfile_name = self._get_pidfile()
    proc_stopped = False
    if proc is not None:
      self._ensure_stdout_dirs_exist()
      sys.stdout.write('Stopping {}: '.format(self.name))
      sys.stdout.flush()
      with protected_file_path.ProtectedFilePath(pidfile_name):
        with open(self.stdout, 'a') as stdout:
          if self.stop_cmd:
            sys.stdout.write('running stop command')
            stdout.write('[{}] {} stopping {}:\n{}\n'.format(
                         time.strftime('%Y-%m-%d %H:%M:%S'), self.cli_name,
                         self.name, ' '.join(self.stop_cmd)))
            stdout.flush()
            # pylint: disable=unused-variable
            stop_proc = psutil.Popen(args=self.stop_cmd,
                                     stdout=stdout,
                                     stderr=stdout,
                                     env=self.env,
                                     cwd=self.cwd)
            proc_stopped = wait_dots(self.after_stop_cmd_seconds, proc)
          if self.run_sigterm and not proc_stopped:
            sys.stdout.write('sending SIGTERM')
            sys.stdout.flush()
            stdout.write('[{}] {} sending SIGTERM to {}\n'.format(
                         time.strftime('%Y-%m-%d %H:%M:%S'), self.cli_name, self.name))
            stdout.flush()
            try:
              proc.terminate()
            except psutil.error.NoSuchProcess:
              pass
            proc_stopped = wait_dots(self.after_sigterm_seconds, proc)
          if self.run_sigkill and not proc_stopped:
            sys.stdout.write('sending SIGKILL')
            sys.stdout.flush()
            stdout.write('[{}] {} sending SIGKILL to {}\n'.format(
                         time.strftime('%Y-%m-%d %H:%M:%S'), self.cli_name, self.name))
            stdout.flush()
            try:
              proc.kill()
            except psutil.error.NoSuchProcess:
              pass
            proc_stopped = wait_dots(self.after_sigkill_seconds, proc)
          if not proc_stopped:
            puts(colored.red('process still running ({}).'.format(proc.pid)))
            stdout.write('[{}] {} process still running({})\n'.format(
                         time.strftime('%Y-%m-%d %H:%M:%S'), self.cli_name, proc.pid))
            stdout.flush()
            sys.exit(1)
          else:
            if not self._is_externally_managed_process():
              os.remove(self.pid_file)
            puts(colored.green('stopped'))
            stdout.write('[{}] {} stopped process ({})\n'.format(
                         time.strftime('%Y-%m-%d %H:%M:%S'), self.cli_name, proc.pid))
