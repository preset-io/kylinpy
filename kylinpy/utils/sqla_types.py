# -*- coding: utf-8 -*-
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import re

from sqlalchemy.types import (
    BIGINT,
    BOOLEAN,
    CHAR,
    DATE,
    DATETIME,
    DECIMAL,
    FLOAT,
    INTEGER,
    SMALLINT,
    TIMESTAMP,
    VARCHAR,
)

KylinType = dict(
    CHAR=CHAR,
    STRING=VARCHAR,
    VARCHAR=VARCHAR,
    DECIMAL=DECIMAL,
    DOUBLE=FLOAT,
    FLOAT=FLOAT,
    BIGINT=BIGINT,
    LONG=BIGINT,
    INTEGER=INTEGER,
    INT=INTEGER,
    TINYINT=SMALLINT,
    SMALLINT=SMALLINT,
    INT4=BIGINT,
    LONG8=BIGINT,
    BOOLEAN=BOOLEAN,
    DATE=DATE,
    DATETIME=DATETIME,
    TIMESTAMP=TIMESTAMP,
)


# Only these types take their parenthesised arguments as SQLAlchemy
# constructor arguments (length, or precision and scale). For the others the
# arguments mean something else (for example TIMESTAMP(3) is a fractional
# seconds precision, not SQLAlchemy's positional ``timezone`` flag), so they
# are dropped.
_PARAMETERIZED = frozenset(('CHAR', 'STRING', 'VARCHAR', 'DECIMAL', 'DOUBLE', 'FLOAT'))


def kylin_to_sqla(s):
    # the '|' operator is never greedy, so sorted keys by key length.
    # Kylin reports parameterised types both as 'DECIMAL(12,2)' and, from its
    # JDBC-style metadata, as 'DECIMAL(12, 2)'; allow whitespace around the
    # arguments so the scale is not silently dropped.
    keys = list(sorted(KylinType.keys(), key=len, reverse=True))
    type_re = re.compile(
        r'^\s*({})\s*(?:\(\s*(\d+)?\s*(?:,\s*(\d+)\s*)?\))?.*$'.format('|'.join(keys)),
        flags=re.IGNORECASE | re.DOTALL,
    )
    type_tuple = type_re.match(s).groups()
    _type = type_tuple[0].upper()
    _args = [int(e) for e in type_tuple[1:] if e] if _type in _PARAMETERIZED else []
    return KylinType.get(_type)(*_args)
