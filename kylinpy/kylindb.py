# -*- coding: utf-8 -*-
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import datetime
import decimal
import math
import re

try:
    from collections.abc import Mapping
except ImportError:  # Python 2
    from collections import Mapping

from kylinpy.client import HTTPError
from kylinpy.kylinpy import Kylin
from kylinpy.utils.compat import as_unicode, binary_type, integer_types, string_types
from kylinpy.utils.kylin_types import kylin_to_python


class ProgrammingError(Exception):
    pass


def escape_parameter(value):
    """Render one Python value as a Kylin (Calcite) SQL literal.

    Kylin's query API takes SQL text only, so pyformat parameters are bound
    client-side. Strings use standard SQL quoting (a single quote is doubled;
    backslash is not an escape character in Calcite string literals).
    """
    if value is None:
        return 'NULL'
    if isinstance(value, bool):
        return 'TRUE' if value else 'FALSE'
    if isinstance(value, integer_types):
        return str(int(value))
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise ProgrammingError('Unsupported non-finite float parameter: {!r}'.format(value))
        return repr(value)
    if isinstance(value, decimal.Decimal):
        if not value.is_finite():
            raise ProgrammingError('Unsupported non-finite decimal parameter: {!r}'.format(value))
        return str(value)
    if isinstance(value, datetime.datetime):
        if value.utcoffset() is not None:
            # Kylin TIMESTAMP literals carry no zone and Calcite rejects an
            # offset suffix; converting silently would shift the instant.
            raise ProgrammingError(
                'Timezone-aware datetime parameters are not supported ({!r}); '
                'pass a naive datetime in the time zone of the stored data.'.format(value),
            )
        return "TIMESTAMP '{}'".format(value.isoformat(sep=str(' ')))
    if isinstance(value, datetime.date):
        return "DATE '{}'".format(value.isoformat())
    if isinstance(value, binary_type) and not isinstance(value, string_types):
        raise ProgrammingError('Unsupported bytes parameter')
    if isinstance(value, string_types):
        return "'{}'".format(value.replace("'", "''"))
    raise ProgrammingError('Unsupported parameter type: {}'.format(type(value).__name__))


_PLACEHOLDER = re.compile(r'%\((?P<name>[^)]*)\)s|%s|%%')


def bind_parameters(query, parameters):
    """Apply DB-API pyformat parameters (a mapping) or format parameters (a sequence).

    Only ``%(name)s`` (mapping), ``%s`` (sequence) and ``%%`` are interpreted.
    Any other ``%`` is literal SQL, so a statement such as ``LIKE 'a%'`` run
    with empty parameters is sent unchanged instead of failing, and a literal
    ``%s`` is never consumed by a mapping. Parameters given as ``None`` leave
    the statement untouched.
    """
    if parameters is None:
        return query
    by_name = isinstance(parameters, Mapping)
    values = None if by_name else [escape_parameter(value) for value in parameters]
    position = [0]

    def substitute(match):
        token = match.group(0)
        if token == '%%':
            return '%'
        name = match.group('name')
        if name is not None:
            if not by_name:
                raise ProgrammingError('Named placeholder %({})s needs mapping parameters'.format(name))
            if name not in parameters:
                raise ProgrammingError('Missing parameter: {!r}'.format(name))
            return escape_parameter(parameters[name])
        if by_name:
            return token
        if position[0] >= len(values):
            raise ProgrammingError('Not enough parameters for the %s placeholders')
        position[0] += 1
        return values[position[0] - 1]

    bound = _PLACEHOLDER.sub(substitute, query)
    if not by_name and position[0] != len(values):
        raise ProgrammingError(
            '{} parameters supplied for {} %s placeholders'.format(len(values), position[0]),
        )
    return bound


class Cursor(object):
    def __init__(self, connection):
        self.connection = connection
        self._arraysize = 1
        self.rowcount = -1
        self.results = []
        self.fetched_rows = 0
        self._column_metas = []

    def callproc(self):
        pass

    def close(self):
        pass

    @property
    def description(self):
        return tuple([
            as_unicode(c['label']),
            c['columnTypeName'].lower(),
            c['displaySize'],
            None,
            c['precision'],
            c['scale'],
            c['isNullable'],
        ] for c in self._column_metas)

    def execute(self, query, parameters=None):
        # Parameters are SQL values, never REST request options.
        resp = self.connection.query(bind_parameters(query, parameters))

        self._column_metas = resp.get('columnMetas')
        self.results = [tuple([
            kylin_to_python(self.description[col][1], cell)
            for (col, cell) in enumerate(row)
        ]) for row in resp['results']]
        self.rowcount = len(self.results)
        self.fetched_rows = 0

    def executemany(self, query, seq_params=None):
        if seq_params is None:
            seq_params = []
        results = []
        for param in seq_params:
            self.execute(query, param)
            results.extend(self.results)

        self.results = results
        self.rowcount = len(self.results)
        self.fetched_rows = 0

    def fetchone(self):
        if self.fetched_rows < self.rowcount:
            row = self.results[self.fetched_rows]
            self.fetched_rows += 1
            return row
        else:
            return None

    def fetchmany(self, size=None):
        fetched_rows = self.fetched_rows
        size = size or self.arraysize
        self.fetched_rows = fetched_rows + size
        return self.results[fetched_rows: self.fetched_rows]

    def fetchall(self):
        fetched_rows = self.fetched_rows
        self.fetched_rows = self.rowcount
        return self.results[fetched_rows:]

    def nextset(self):
        pass

    @property
    def arraysize(self):
        return self._arraysize

    @arraysize.setter
    def arraysize(self, array_size):
        self._arraysize = array_size

    def setinputsizes(self):
        pass

    def setoutputsize(self):
        pass


class Connection(Kylin):
    paramstyle = 'pyformat'
    threadsafety = 2
    apilevel = '2.0'
    Error = HTTPError
    ProgrammingError = ProgrammingError

    def __init__(self, **kwargs):
        super(Connection, self).__init__(**kwargs)

    @classmethod
    def connect(cls, **kwargs):
        return cls(**kwargs)

    def close(self):
        pass

    def commit(self):
        pass

    def rollback(self):
        pass

    def cursor(self):
        return Cursor(self)
