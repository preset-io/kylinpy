# -*- coding: utf-8 -*-
"""SQLAlchemy 2 dialect and DB-API regressions."""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import datetime
import decimal
import json
import subprocess
import sys
import warnings

import pytest
import sqlalchemy as sa
from sqlalchemy.sql import compiler

from kylinpy import kylindb
from kylinpy.utils.kylin_types import kylin_to_python

DSN = 'kylin://ADMIN:KYLIN@sandbox/learn_kylin'


def query_response(sql):
    return {
        'columnMetas': [{
            'label': 'SQL', 'columnTypeName': 'VARCHAR', 'displaySize': 256,
            'precision': 256, 'scale': 0, 'isNullable': 1,
        }],
        'results': [[sql]],
        'exceptionMessage': None,
    }


@pytest.fixture
def engine():
    engine = sa.create_engine(DSN)
    yield engine
    engine.dispose()


@pytest.fixture
def sent_sql(v1_api):
    """Capture the SQL text sent to Kylin's query endpoint."""
    sent = []

    def fake_query(client, endpoint, **kwargs):
        sent.append(kwargs['json']['sql'])
        return query_response(kwargs['json']['sql'])

    v1_api.patch('kylinpy.service.KylinService.api.query', side_effect=fake_query)
    return sent


# Reflection receives a Connection; SQLAlchemy 2.0 removed Connection.connect().
def test_reflection_uses_the_dbapi_connection(v1_api, engine):
    inspector = sa.inspect(engine)
    assert inspector.get_schema_names() == ['DEFAULT']
    assert 'KYLIN_SALES' in inspector.get_table_names('DEFAULT')
    columns = inspector.get_columns('KYLIN_SALES', 'DEFAULT')
    assert columns[0]['name'] == 'TRANS_ID'
    assert isinstance(columns[0]['type'], sa.BigInteger)


def test_table_autoload_reflects_under_sqlalchemy_2(v1_api, engine):
    table = sa.Table('KYLIN_SALES', sa.MetaData(), schema='DEFAULT', autoload_with=engine)
    assert 'TRANS_ID' in table.c
    assert list(table.primary_key.columns) == []


def test_pk_constraint_has_the_reflection_shape(v1_api, engine):
    pk = sa.inspect(engine).get_pk_constraint('KYLIN_SALES', 'DEFAULT')
    assert pk == {'constrained_columns': [], 'name': None}


# Inspector.has_table passes info_cache=; the answer must reflect the catalog.
def test_has_table_accepts_inspector_keywords_and_reports_existence(v1_api, engine):
    inspector = sa.inspect(engine)
    assert inspector.has_table('KYLIN_SALES', 'DEFAULT') is True
    assert inspector.has_table('NO_SUCH_TABLE', 'DEFAULT') is False
    assert inspector.has_table('KYLIN_SALES', 'OTHER_SCHEMA') is False


def test_has_sequence_accepts_inspector_keywords(v1_api, engine):
    assert sa.inspect(engine).has_sequence('ANY', 'DEFAULT') is False


# Core select() must compile with SQLAlchemy >= 1.4 compiler signatures.
def test_core_select_compiles_and_executes(sent_sql, engine):
    sales = sa.table('KYLIN_SALES', sa.column('TRANS_ID'), sa.column('PRICE'), schema='DEFAULT')
    stmt = (
        sa.select(sales.c.TRANS_ID, sa.func.sum(sales.c.PRICE).label('total'))
        .where(sales.c.TRANS_ID < 3)
        .group_by(sales.c.TRANS_ID)
        .order_by(sales.c.TRANS_ID)
        .limit(10)
    )
    compiled = str(stmt.compile(engine, compile_kwargs={'literal_binds': True}))
    assert 'FROM "DEFAULT"."KYLIN_SALES"' in compiled
    assert 'LIMIT 10' in compiled
    with engine.connect() as conn:
        conn.execute(stmt).fetchall()
    assert 'WHERE "DEFAULT"."KYLIN_SALES"."TRANS_ID" < 3' in sent_sql[-1]


def test_dialect_supports_statement_cache_without_warnings(sent_sql, engine):
    with warnings.catch_warnings():
        warnings.simplefilter('error')
        engine = sa.create_engine(DSN)
        with engine.connect() as conn:
            conn.execute(sa.select(sa.literal_column('1'))).fetchall()
    assert 'supports_statement_cache' in vars(type(engine.dialect))


# Parameters are SQL values, bound client-side; never REST request options.
def test_bound_parameters_are_rendered_as_sql_literals(sent_sql, engine):
    tricky = "O'Brien \\ café 雪 :name ; -- /* x */ \" %s %(k)s"
    with engine.connect() as conn:
        conn.execute(sa.text('SELECT :v AS a, :v AS b, :n AS c'), {'v': tricky, 'n': None})
        conn.execute(sa.text('SELECT 1 FROM T WHERE ID < :limit'), {'limit': 3})
    assert sent_sql[0] == (
        "SELECT 'O''Brien \\ café 雪 :name ; -- /* x */ \" %s %(k)s' AS a, "
        "'O''Brien \\ café 雪 :name ; -- /* x */ \" %s %(k)s' AS b, NULL AS c"
    )
    assert sent_sql[1] == 'SELECT 1 FROM T WHERE ID < 3'


def test_percent_literals_survive_parameterized_and_unparameterized_text(sent_sql, engine):
    with engine.connect() as conn:
        conn.execute(sa.text("SELECT '100%' AS a WHERE 1 = :one"), {'one': 1})
        conn.execute(sa.text("SELECT '100%' AS a"))
    assert sent_sql == ["SELECT '100%' AS a WHERE 1 = 1", "SELECT '100%' AS a"]


def test_raw_dbapi_execute_without_parameters_is_unchanged(sent_sql):
    conn = kylindb.Connection(host='sandbox', project='learn_kylin')
    conn.cursor().execute("SELECT '100%' AS a")
    assert sent_sql == ["SELECT '100%' AS a"]


@pytest.mark.parametrize('value,literal', [
    (None, 'NULL'),
    (True, 'TRUE'),
    (False, 'FALSE'),
    (-9223372036854775808, '-9223372036854775808'),
    (1.25, '1.25'),
    (decimal.Decimal('-0.000000000000000001'), '-1E-18'),
    (datetime.date(2000, 2, 29), "DATE '2000-02-29'"),
    (datetime.datetime(2026, 9, 24, 12, 34, 56, 123456), "TIMESTAMP '2026-09-24 12:34:56.123456'"),
    ("it's", "'it''s'"),
])
def test_escape_parameter(value, literal):
    assert kylindb.escape_parameter(value) == literal


@pytest.mark.parametrize('value', [
    float('nan'), float('inf'), decimal.Decimal('NaN'), b'bytes', object(),
])
def test_unsupported_parameters_are_rejected(value):
    with pytest.raises(kylindb.ProgrammingError):
        kylindb.escape_parameter(value)


# DECIMAL values arrive as exact strings and must not pass through float.
def test_decimal_values_are_exact():
    value = kylin_to_python('DECIMAL(38,18)', '12345678901234567890.123456789012345678')
    assert type(value) is decimal.Decimal
    assert value == decimal.Decimal('12345678901234567890.123456789012345678')


def test_decimal_results_are_exact_through_sqlalchemy(v1_api, engine):
    v1_api.patch('kylinpy.service.KylinService.api.query', return_value={
        'columnMetas': [{
            'label': 'AMOUNT', 'columnTypeName': 'DECIMAL', 'displaySize': 40,
            'precision': 38, 'scale': 18, 'isNullable': 1,
        }],
        'results': [['12345678901234567890.123456789012345678'], [None]],
        'exceptionMessage': None,
    })
    with engine.connect() as conn:
        rows = conn.execute(sa.text('SELECT AMOUNT FROM T')).scalars().all()
    assert rows == [decimal.Decimal('12345678901234567890.123456789012345678'), None]


# Importing the dialect must not change quoting for any other dialect.
def test_importing_the_dialect_leaves_base_reserved_words_unchanged():
    code = (
        'import json\n'
        'from sqlalchemy.sql import compiler\n'
        'before = set(compiler.IdentifierPreparer.reserved_words)\n'
        'base = compiler.IdentifierPreparer.reserved_words\n'
        'import kylinpy.sqla_dialect as d\n'
        'after = compiler.IdentifierPreparer.reserved_words\n'
        'print(json.dumps(dict(same_object=after is base, same_words=set(after) == before,\n'
        '                      kylin_has_calcite=\"SELECT\" in d.KylinIdentifierPreparer.reserved_words,\n'
        '                      kylin_has_superset=\"__timestamp\" in d.KylinIdentifierPreparer.reserved_words)))\n'
    )
    out = subprocess.check_output([sys.executable, '-c', code]).decode('utf-8')
    assert json.loads(out.strip().splitlines()[-1]) == {
        'same_object': True, 'same_words': True,
        'kylin_has_calcite': True, 'kylin_has_superset': True,
    }


def test_other_dialect_quoting_is_unaffected_after_import():
    import kylinpy.sqla_dialect  # noqa: F401
    preparer = compiler.IdentifierPreparer(sa.engine.default.DefaultDialect())
    # 'value' and 'year' are Calcite keywords but not SQLAlchemy base reserved words.
    assert preparer.quote('value') == 'value'
    assert preparer.quote('year') == 'year'


def test_kylin_quoting_uses_calcite_keywords(engine):
    assert engine.dialect.identifier_preparer.quote('value') == '"value"'
