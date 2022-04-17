#!/usr/bin/env python3
# coding: utf8

from pgo2mbox import __version__ as pgo2mbox_version
from pgo2mbox import __author__ as pgo2mbox_author
from pgo2mbox import __email__ as pgo2mbox_authormail
from pgo2mbox import __license__ as pgo2mbox_license

from cx_Freeze import setup, Executable

base = "Console"

executables = [
    Executable(
        "pgo2mbox.py",
        base=base,
        copyright=f"Licensed under {pgo2mbox_license} by {pgo2mbox_author}",
        icon="icon/icon.ico")
]

packages = [
    'argparse', 'codecs', 'datetime', 'logging', 'os', 're', 'time', 'sys',
    'platform', 'unicodedata', 'email', 'sqlite3', 'mailbox', 'collections',
    'hashlib'
]

options = {
    'build_exe': {
        'packages': packages,
        "excludes": ["tkinter"],
        "include_msvcr": True,
        "optimize": 1,
    },
}

setup(name="pgo2mailbox",
      author=pgo2mbox_author,
      author_email=pgo2mbox_authormail,
      options=options,
      version=pgo2mbox_version,
      description='Convert PGOffline to Mbox',
      executables=executables)
