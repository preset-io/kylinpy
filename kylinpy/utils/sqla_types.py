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
# constructor arguments, and only this many of them: a length, or DECIMAL's
# precision and scale. FLOAT takes a precision only; its second positional
# argument is ``asdecimal``, not a scale. For the other types the arguments
# mean something else (for example TIMESTAMP(3) is a fractional seconds
# precision, not SQLAlchemy's positional ``timezone`` flag, and INTEGER(11) is
# a display width), so they are dropped.
_PARAMETERIZED = dict(CHAR=1, STRING=1, VARCHAR=1, DECIMAL=2, DOUBLE=1, FLOAT=1)


def _type_args(arg_text, max_args):
    # Keep the leading integer arguments, up to what the constructor takes, so
    # an unexpected shape such as 'DECIMAL(12,)' or 'DECIMAL(12,2,3)' keeps the
    # arguments it can rather than dropping them all.
    args = []
    for part in (arg_text or '').split(','):
        part = part.strip()
        if not part.isdigit() or len(args) == max_args:
            break
        args.append(int(part))
    return args


def kylin_to_sqla(s):
    # the '|' operator is never greedy, so sorted keys by key length.
    # Kylin reports parameterised types both as 'DECIMAL(12,2)' and, from its
    # JDBC-style metadata, as 'DECIMAL(12, 2)'; allow whitespace around the
    # arguments so the scale is not silently dropped.
    keys = list(sorted(KylinType.keys(), key=len, reverse=True))
    type_re = re.compile(
        r'^\s*({})\s*(?:\(([^)]*)\))?.*$'.format('|'.join(keys)),
        flags=re.IGNORECASE | re.DOTALL,
    )
    _type, arg_text = type_re.match(s).groups()
    _type = _type.upper()
    _args = _type_args(arg_text, _PARAMETERIZED.get(_type, 0))
    return KylinType.get(_type)(*_args)
