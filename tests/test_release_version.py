# -*- coding: utf-8 -*-
"""Publishing uses the same normalized version as the built wheel."""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import runpy
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'ci' / 'release_version.py'
release = runpy.run_path(str(SCRIPT))


@pytest.mark.parametrize('base,change_id,revision,expected', [
    ('2.8.5.1', '', 'e2bc688a1b2c', '2.8.5.1'),
    ('2.8.5.1', '1', 'e2bc688a1b2c', '2.8.5.1+pr.1.e2bc688a1b2c'),
    ('2.8.5.1', '1', 'ABCDEF123456', '2.8.5.1+pr.1.abcdef123456'),
    ('2.8.5.1', '12', '012345678901', '2.8.5.1+pr.12.12345678901'),
])
def test_release_version(base, change_id, revision, expected):
    out = subprocess.check_output([sys.executable, str(SCRIPT), base, change_id, revision])
    assert out.decode('utf-8').strip() == expected


def test_wheel_name_uses_the_normalized_version():
    version = release['release_version']('2.8.5.1', '3', '0abc')
    assert release['wheel_name'](version) == 'kylinpy-2.8.5.1+pr.3.0abc-py3-none-any.whl'
