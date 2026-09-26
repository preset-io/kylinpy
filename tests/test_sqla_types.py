# -*- coding: utf-8 -*-
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

from kylinpy.utils.sqla_types import kylin_to_sqla


def test_string():
    string_obj = kylin_to_sqla('CHAR(64) hello this is long descrition')
    assert string_obj.length == 64

    string_obj = kylin_to_sqla('STRING(64) hello this is long descrition')
    assert string_obj.length == 64

    string_obj = kylin_to_sqla('VARCHAR(64) hello this is long descrition')
    assert string_obj.length == 64


def test_float():
    decimal_obj = kylin_to_sqla('DECIMAL(20,6)')
    assert decimal_obj.precision == 20
    assert decimal_obj.scale == 6

    decimal_obj = kylin_to_sqla('DOUBLE(20)')
    assert decimal_obj.precision == 20

    decimal_obj = kylin_to_sqla('FLOAT(20)')
    assert decimal_obj.precision == 20


def test_int():
    assert str(kylin_to_sqla('BIGINT')) == 'BIGINT'
    assert str(kylin_to_sqla('INTEGER')) == 'INTEGER'
    assert str(kylin_to_sqla('INT')) == 'INTEGER'
    assert str(kylin_to_sqla('TINYINT')) == 'SMALLINT'
    assert str(kylin_to_sqla('SMALLINT')) == 'SMALLINT'
    assert str(kylin_to_sqla('INT4')) == 'BIGINT'
    assert str(kylin_to_sqla('LONG8')) == 'BIGINT'


def test_others():
    assert str(kylin_to_sqla('BOOLEAN')) == 'BOOLEAN'
    assert str(kylin_to_sqla('DATE')) == 'DATE'
    assert str(kylin_to_sqla('DATETIME')) == 'DATETIME'
    assert str(kylin_to_sqla('TIMESTAMP')) == 'TIMESTAMP'


def test_decimal_with_space_after_comma_keeps_scale():
    # Kylin's /tables_and_columns metadata reports 'DECIMAL(12, 2)'.
    decimal_obj = kylin_to_sqla('DECIMAL(12, 2)')
    assert decimal_obj.precision == 12
    assert decimal_obj.scale == 2
    assert str(decimal_obj) == 'DECIMAL(12, 2)'

    decimal_obj = kylin_to_sqla('decimal( 19 , 4 )')
    assert (decimal_obj.precision, decimal_obj.scale) == (19, 4)


def test_varchar_with_charset_suffix():
    string_obj = kylin_to_sqla(
        'VARCHAR(256) CHARACTER SET "UTF-16LE" COLLATE "UTF-16LE$en_US$primary"')
    assert string_obj.length == 256


def test_timestamp_precision_is_not_a_timezone_flag():
    # Kylin reports TIMESTAMP(0)/TIMESTAMP(3); the number is fractional-second
    # precision and must not become SQLAlchemy's positional timezone argument.
    for spec in ('TIMESTAMP(0)', 'TIMESTAMP(3)', 'TIMESTAMP'):
        ts = kylin_to_sqla(spec)
        assert ts.timezone is False
        assert str(ts) == 'TIMESTAMP'
