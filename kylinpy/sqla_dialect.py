# -*- coding: utf-8 -*-
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import itertools

import sqlalchemy.exc
from sqlalchemy import pool
from sqlalchemy.engine import default
from sqlalchemy.sql import compiler

from kylinpy.exceptions import NoSuchTableError
from kylinpy.kylindb import Connection
from kylinpy.utils.keywords import CALCITE_KEYWORDS
from kylinpy.utils.sqla_types import kylin_to_sqla

SUPERSET_KEYWORDS = set([
    '__timestamp',
])


class KylinIdentifierPreparer(compiler.IdentifierPreparer):
    # Scoped to this preparer. Assigning to the base IdentifierPreparer would
    # change identifier quoting for every other dialect in the process.
    reserved_words = set(
        itertools.chain(*[[e.lower(), e] for e in CALCITE_KEYWORDS]),
    ) | SUPERSET_KEYWORDS

    def __init__(self, dialect, initial_quote='"',
                 final_quote=None, escape_quote='"', omit_schema=True):
        super(KylinIdentifierPreparer, self).__init__(
            dialect, initial_quote, final_quote, escape_quote, omit_schema,
        )

    def format_label(self, label, name=None):
        return self.quote(name or label.name)


class KylinSQLCompiler(compiler.SQLCompiler):
    pass


def _dbapi_connection(connection):
    """Return the kylinpy DB-API connection behind a SQLAlchemy Connection.

    SQLAlchemy 2.0 removed ``Connection.connect()``; reflection receives a
    Connection and must reach the driver connection through the pool proxy.
    """
    return connection.connection.dbapi_connection


class KylinDialect(default.DefaultDialect):
    name = 'kylin'
    driver = 'kylin'

    statement_compiler = KylinSQLCompiler
    preparer = KylinIdentifierPreparer

    preexecute_pk_sequences = True
    supports_pk_autoincrement = True
    supports_sequences = True
    sequences_optional = True
    supports_native_decimal = True
    supports_default_values = True
    supports_native_boolean = True
    poolclass = pool.SingletonThreadPool
    supports_unicode_statements = True
    # The compiler holds no per-statement state, so compiled forms are cacheable.
    supports_statement_cache = True

    default_paramstyle = 'pyformat'

    def __init__(self, *args, **kwargs):
        super(KylinDialect, self).__init__(*args, **kwargs)

    @classmethod
    def import_dbapi(cls):
        return Connection

    @classmethod
    def dbapi(cls):
        # SQLAlchemy < 2.0 entry point.
        return Connection

    def initialize(self, connection):
        self.server_version_info = None
        self.default_schema_name = None
        self.default_isolation_level = None
        self.returns_unicode_strings = True

    def create_connect_args(self, url):
        kwargs = {
            'host': url.host,
            'port': url.port or 7070,
            'username': url.username,
            'password': url.password,
            'project': url.database or 'default',
        }
        kwargs.update(url.query)
        if 'is_ssl' in kwargs:
            if kwargs['is_ssl'] in ['1', 'true', 'True', True]:
                kwargs.update({'is_ssl': True})
            else:
                kwargs.update({'is_ssl': False})
        return [[], kwargs]

    def do_execute(self, cursor, statement, parameters, context=None):
        super(KylinDialect, self).do_execute(cursor, statement, parameters, context)

    def get_table_names(self, connection, schema=None, **kw):
        return _dbapi_connection(connection).get_all_tables(schema)

    def get_schema_names(self, connection, schema=None, **kw):
        return sorted(_dbapi_connection(connection).get_all_schemas())

    def has_table(self, connection, table_name, schema=None, **kw):
        if schema is None and '.' in table_name:
            schema, table_name = table_name.split('.', 1)
        return table_name in _dbapi_connection(connection).get_all_tables(schema)

    def has_sequence(self, connection, sequence_name, schema=None, **kw):
        return False

    def get_columns(self, connection, table_name, schema=None, **kw):
        try:
            columns = _dbapi_connection(connection).get_table_source(table_name, schema).columns
            return [{
                'name': col.name,
                'type': kylin_to_sqla(col.datatype),
            } for col in columns]
        except NoSuchTableError:
            raise sqlalchemy.exc.NoSuchTableError

    def get_foreign_keys(self, connection, table_name, schema=None, **kw):
        return []

    def get_indexes(self, connection, table_name, schema=None, **kw):
        return []

    def get_view_names(self, connection, schema=None, **kw):
        return []

    def get_pk_constraint(self, connection, table_name, schema=None, **kw):
        # Kylin has no primary keys; SQLAlchemy 2 expects this shape.
        return {'constrained_columns': [], 'name': None}

    def get_unique_constraints(self, connection, table_name, schema=None, **kw):
        return []
