# Module:   main
# Date:     12th July 2010
# Author:   James Mills, prologic at shortcircuit dot net dot au

"""Main

...
"""

import os
import sys

from mercurial.ui import ui
from mercurial.hgweb import hgweb

from circuits.app import Daemon
from circuits import Manager, Debugger

try:
    from circuits.web.apps import MemoryMonitor
except ImportError:
    MemoryMonitor = None  # NOQA

from circuits.web.wsgi import Gateway
from circuits.web import Logger, Server, Sessions, Static

from root import Root
from config import Config
from env import Environment
from tools import CacheControl, Compression
from tools import ErrorHandler, SignalHandler


def main():
    config = Config()

    manager = Manager()

    if config.get("debug"):
        manager += Debugger(
            events=config.get("verbose"),
            file=config.get("errorlog"),
        )

    environ = Environment(config)

    SignalHandler(environ).register(environ)

    manager += environ

    if config.get("sock") is not None:
        bind = config.get("sock")
    elif ":" in config.get("bind"):
        address, port = config.get("bind").split(":")
        bind = (address, int(port),)
    else:
        bind = (config.get("bind"), config.get("port"),)

    server = (
        Server(bind)
        + Sessions()
        + Root(environ)
        + CacheControl(environ)
        + ErrorHandler(environ)
    )

    if MemoryMonitor is not None:
        MemoryMonitor(channel="/memory").register(server)

    if not config.get("disable-logging"):
        server += Logger(file=config.get("accesslog", sys.stdout))

    if not config.get("disable-static"):
        server += Static(docroot=os.path.join(config.get("theme"), "htdocs"))

    if not config.get("disable-hgweb"):
        baseui = ui()
        baseui.setconfig("web", "prefix", "/+hg")
        baseui.setconfig("web", "style", "gitweb")
        baseui.setconfig("web", "allow_push", "*")
        baseui.setconfig("web", "push_ssl", False)
        baseui.setconfig("web", "allow_archive", ["bz2", "gz", "zip"])
        baseui.setconfig("web", "description", config.get("description"))

        server += Gateway({
            "/+hg": hgweb(
                environ.storage.repo_path,
                config.get("name"),
                baseui
            )
        })

    if not config.get("disable-compression"):
        server += Compression(environ)

    if config.get("daemon"):
        manager += Daemon(config.get("pidfile"))

    server.register(manager)

    manager.run()

if __name__ == "__main__":
    main()
