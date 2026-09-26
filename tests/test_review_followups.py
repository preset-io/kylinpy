# -*- coding: utf-8 -*-
"""Regressions for literal percent signs, zone-aware timestamps and the CI release step."""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import datetime
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa

from kylinpy import kylindb

ROOT = Path(__file__).resolve().parents[1]
DSN = 'kylin://ADMIN:KYLIN@sandbox/learn_kylin'


def response(sql):
    return {
        'columnMetas': [{
            'label': 'SQL', 'columnTypeName': 'VARCHAR', 'displaySize': 256,
            'precision': 256, 'scale': 0, 'isNullable': 1,
        }],
        'results': [[sql]],
        'exceptionMessage': None,
    }


@pytest.fixture
def sent_sql(v1_api):
    sent = []

    def fake_query(client, endpoint, **kwargs):
        sent.append(kwargs['json']['sql'])
        return response(kwargs['json']['sql'])

    v1_api.patch('kylinpy.service.KylinService.api.query', side_effect=fake_query)
    return sent


# A literal % in driver SQL without parameters must not be treated as a placeholder.
def test_exec_driver_sql_with_literal_percent_and_no_parameters(sent_sql):
    engine = sa.create_engine(DSN)
    with engine.connect() as conn:
        conn.exec_driver_sql("SELECT 'a%b' AS x, 'done 100%' AS y")
    assert sent_sql == ["SELECT 'a%b' AS x, 'done 100%' AS y"]


def test_literal_percent_s_is_not_consumed_by_mapping_parameters(sent_sql):
    engine = sa.create_engine(DSN)
    with engine.connect() as conn:
        conn.exec_driver_sql("SELECT '%s' AS x")
        conn.exec_driver_sql("SELECT '%s' AS x, %(v)s AS y", {'v': 1})
    assert sent_sql == ["SELECT '%s' AS x", "SELECT '%s' AS x, 1 AS y"]


@pytest.mark.parametrize('query,parameters,expected', [
    ("LIKE 'a%'", {}, "LIKE 'a%'"),
    ("LIKE 'a%'", (), "LIKE 'a%'"),
    ("LIKE 'a%%' AND x = %(x)s", {'x': "it's"}, "LIKE 'a%' AND x = 'it''s'"),
    ("x = %s AND y = %s", (1, None), 'x = 1 AND y = NULL'),
    ("'%(x)s'", None, "'%(x)s'"),
])
def test_bind_parameters(query, parameters, expected):
    assert kylindb.bind_parameters(query, parameters) == expected


@pytest.mark.parametrize('query,parameters,message', [
    ('x = %(missing)s', {}, 'Missing parameter'),
    ('x = %s', (), 'Not enough parameters'),
    ('x = %s', (1, 2), '2 parameters supplied for 1'),
    ('x = %(v)s', (1,), 'needs mapping parameters'),
])
def test_bind_parameter_mismatches_raise_programming_error(query, parameters, message):
    with pytest.raises(kylindb.ProgrammingError, match=message):
        kylindb.bind_parameters(query, parameters)


# Calcite rejects an offset suffix in a TIMESTAMP literal; fail clearly instead.
@pytest.mark.parametrize('tz', [
    datetime.timezone.utc, datetime.timezone(datetime.timedelta(hours=5, minutes=30)),
])
def test_timezone_aware_datetime_is_rejected(tz):
    value = datetime.datetime(2026, 9, 24, 12, 34, 56, tzinfo=tz)
    with pytest.raises(kylindb.ProgrammingError, match='Timezone-aware'):
        kylindb.escape_parameter(value)


def test_naive_datetime_literal_has_no_offset():
    literal = kylindb.escape_parameter(datetime.datetime(2026, 9, 24, 12, 34, 56))
    assert literal == "TIMESTAMP '2026-09-24 12:34:56'"


# The master publish step must work when Jenkins provides no change number.
def test_jenkins_release_step_works_without_a_change_number():
    jenkinsfile = (ROOT / 'Jenkinsfile').read_text()
    line = next(
        line.strip() for line in jenkinsfile.splitlines()
        if line.strip().startswith('.venv/bin/python ci/release_version.py')
    )
    command = 'set -eu; ' + re.sub(r'^\.venv/bin/python', '"$PYTHON"', line).replace(
        '> release.version', '',
    )
    env = {k: v for k, v in os.environ.items() if k != 'CHANGE_NUMBER'}
    env.update(PYTHON=sys.executable, BASE_VERSION='2.8.5.2', REVISION='0123456789ab')
    out = subprocess.check_output(['sh', '-c', command], cwd=str(ROOT), env=env)
    assert out.decode('utf-8').strip() == '2.8.5.2'


# has_table resolves names case-insensitively, like Kylin, and uses a single-table lookup.
@pytest.mark.parametrize('name,schema,expected', [
    ('KYLIN_SALES', 'DEFAULT', True),
    ('kylin_sales', 'default', True),
    ('Kylin_Sales', 'DEFAULT', True),
    ('kylin_sales', None, True),
    ('default.kylin_sales', None, True),
    ('no_such_table', 'default', False),
    ('no_such_table', None, False),
    ('kylin_sales', 'other_schema', False),
])
def test_has_table_is_case_insensitive(v1_api, name, schema, expected):
    inspector = sa.inspect(sa.create_engine(DSN))
    assert inspector.has_table(name, schema) is expected


def test_has_table_with_schema_does_not_fetch_the_catalog(v1_api):
    from kylinpy.service import KylinService
    catalog = KylinService.api.tables_and_columns
    catalog.reset_mock()
    inspector = sa.inspect(sa.create_engine(DSN))
    assert inspector.has_table('kylin_sales', 'default') is True
    assert inspector.has_table('no_such_table', 'default') is False
    assert catalog.call_count == 0
    endpoints = [call.args[1] for call in KylinService.api.table_desc.call_args_list]
    assert endpoints[-2:] == ['/tables/learn_kylin/default.kylin_sales', '/tables/learn_kylin/default.no_such_table']


def test_single_table_lookup_quotes_path_segments(v1_api):
    from kylinpy.service import KylinService
    from kylinpy.kylinpy import Kylin
    Kylin(host='sandbox', project='a b/c').table_exists('t/1', 's p')
    assert KylinService.api.table_desc.call_args.args[1] == '/tables/a%20b%2Fc/s%20p.t%2F1'
