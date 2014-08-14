Platform CLI
=========

#### Objective

Platform CLI is a Python module that allows software packagers to build custom
command line tools for managing process startup and configuration.  It allows a
packager of a multi-service software platform to ship to an on-premise systems
administrator or an internal ops team and have them be able to do site-specific
startup configuration in a concise and discoverable way.

#### What it does

Platform CLI creates a single bucket of startup properties, which all ship with
default values, and which are overrideable by the user without erasing the
default. These startup properties can be designed by the packager to set
environment variables or command line flags during startup, or even to
regenerate config files if needed.

It also allows the packager to implement checks which are done prior to
startup, offering suggestions about startup property values based on the
user's environment.

Once the startup property overrides for a particular installation are in place,
the user can start, stop, or query status on multiple services at one time,
including listening ports.

#### Licensing
Platform CLI is licensed under the Apache License, Version 2.0. See LICENSE for full license text.
