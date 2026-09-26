# -*- coding: utf-8 -*-
"""Choose the exact distribution version before building the wheel.

Stable builds publish the declared version. Pull-request builds publish a PEP
440 local version, normalized exactly as the build backend normalizes it, so
the wheel filename, its metadata and the published key always agree (for
example an abbreviated revision beginning with 0 becomes a shorter numeric
local segment).
"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import sys

from packaging.version import Version


def release_version(base, change_id, revision):
    if not change_id:
        return str(Version(base))
    return str(Version('{}+pr.{}.{}'.format(base, change_id, revision)))


def wheel_name(version):
    return 'kylinpy-{}-py3-none-any.whl'.format(version)


if __name__ == '__main__':
    print(release_version(*sys.argv[1:4]))
