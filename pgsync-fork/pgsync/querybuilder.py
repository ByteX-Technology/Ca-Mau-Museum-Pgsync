"""PGSync QueryBuilder."""

import threading
import typing as t
from collections import defaultdict

import sqlalchemy as sa

from .base import compiled_query, TupleIdentifierType
from .constants import OBJECT, ONE_TO_MANY, ONE_TO_ONE, SCALAR
from .exc import ForeignKeyError
from .node import Node
from .settings import IS_MYSQL_COMPAT


def JSON_OBJECT(*args: t.Any) -> sa.sql.functions.Function:
    """JSON object constructor."""
    return (
        sa.func.JSON_OBJECT(*args)
        if IS_MYSQL_COMPAT
        else sa.func.JSON_BUILD_OBJECT(*args)
    )


def JSON_ARRAY(*args: t.Any) -> sa.sql.functions.Function:
    """JSON array constructor."""
    return (
        sa.func.JSON_ARRAY(*args)
        if IS_MYSQL_COMPAT
        else sa.func.JSON_BUILD_ARRAY(*args)
    )


def JSON_AGG(expr: t.Any) -> sa.sql.functions.Function:
    """Aggregate into JSON array."""
    return (
        sa.func.JSON_ARRAYAGG(sa.distinct(expr))
        if IS_MYSQL_COMPAT
        else sa.func.JSON_AGG(expr)
    )


def JSON_TYPE() -> t.Any:
    """Resulting JSON type to annotate/cast."""
    return sa.JSON if IS_MYSQL_COMPAT else sa.dialects.postgresql.JSONB


def JSON_CAST(expression: t.Any) -> t.Any:
    """
    Ensure the expression is treated as JSON by SQLAlchemy.
    - PG: emit CAST(... AS JSONB)
    - MySQL/MariaDB: avoid emitting CAST; only annotate type
    """
    return (
        sa.type_coerce(expression, sa.JSON)
        if IS_MYSQL_COMPAT
        else sa.cast(expression, sa.dialects.postgresql.JSONB)
    )


def JSON_CONCAT(a: t.Any, b: t.Any) -> t.Any:
    """
    Merge/concatenate JSON values (object-merge & array-append).
    - PG: jsonb || jsonb
    - MySQL/MariaDB: JSON_MERGE_PRESERVE(a,b) (keeps array elements)
    """
    return (
        sa.func.JSON_MERGE_PRESERVE(a, b) if IS_MYSQL_COMPAT else a.op("||")(b)
    )


class QueryBuilder(threading.local):
    """Query builder."""

    def __init__(self, verbose: bool = False):
        """Query builder constructor."""
        self.verbose: bool = verbose
        self.isouter: bool = True
        self._cache: dict = {}

    def _eval_expression(
        self, expression: sa.sql.elements.BinaryExpression
    ) -> sa.sql.elements.BinaryExpression:
        if IS_MYSQL_COMPAT:
            return expression
        if isinstance(
            expression.left.type, sa.dialects.postgresql.UUID
        ) or isinstance(expression.right.type, sa.dialects.postgresql.UUID):
            if not isinstance(
                expression.left.type, sa.dialects.postgresql.UUID
            ) or not isinstance(
                expression.right.type, sa.dialects.postgresql.UUID
            ):
                # handle UUID typed expressions:
                # psycopg2.errors.UndefinedFunction: operator does not exist: uuid = integer
                return expression.left is None

        return expression

    def _build_filters(
        self, filters: t.Dict[str, t.List[dict]], node: Node
    ) -> t.Optional[sa.sql.elements.BooleanClauseList]:
        """
        Build SQLAlchemy filters.

        NB:
        assumption dictionary is an AND and list is an OR
        filters = {
            'book': [
                {'id': 1, 'uid': '001'},
                {'id': 2, 'uid': '002'},
            ],
            'city': [
                {'id': 1},
                {'id': 2},
            ],
        }
        """
        if filters is not None:
            if filters.get(node.table):
                clause: t.List = []
                for values in filters.get(node.table):
                    where: t.List = []
                    for column, value in values.items():
                        where.append(
                            self._eval_expression(
                                node.model.c[column] == value
                            )
                        )
                    # and clause is applied for composite primary keys
                    clause.append(sa.and_(*where))
                return sa.or_(*clause)

    def _json_build_object(
        self, columns: t.List, chunk_size: int = 100
    ) -> sa.sql.elements.BinaryExpression:
        """
        Tries to get aroud the limitation of JSON_BUILD_OBJECT which
        has a default limit of 100 args.
        This results in the error: 'cannot pass more than 100 arguments
        to a function'

        with the 100 arguments limit this implies we can only select 50 columns
        at a time.
        """
        i: int = 0
        expression: t.Optional[sa.sql.elements.BinaryExpression] = None
        while i < len(columns):
            chunk = columns[i : i + chunk_size]
            piece = JSON_CAST(JSON_OBJECT(*chunk))
            expression = (
                piece if expression is None else JSON_CONCAT(expression, piece)
            )
            i += chunk_size

        if expression is None:
            raise RuntimeError("invalid expression")
        return expression

    # this is for handling non-through tables
    def get_foreign_keys(
        self, node_a: Node, node_b: Node
    ) -> t.Dict[str, t.List[str]]:
        """
        Return all FK columns between node_a and node_b using SQLAlchemy introspection.
        """
        cache_key = (node_a, node_b)
        if cache_key in self._cache:
            return self._cache[cache_key]

        fkeys = defaultdict(list)

        def add(table_key, col):
            if table_key and col and col not in fkeys[table_key]:
                fkeys[table_key].append(col)

        def qname(sa_table):
            if sa_table is None:
                return None
            schema = getattr(sa_table, "schema", None)
            name = getattr(sa_table, "name", None) or getattr(sa_table, "key", None)
            if not name:
                return None
            return f"{schema}.{name}" if schema else str(name)

        # Get tables
        A = getattr(getattr(node_a, "model", None), "original", None)
        B = getattr(getattr(node_b, "model", None), "original", None)
        A_q = qname(A)
        B_q = qname(B)

        def same_table(t1, t2):
            return qname(t1) is not None and qname(t1) == qname(t2)

        if A is not None and B is not None:
            # Check A -> B
            for fk in getattr(A, "foreign_keys", []):
                column = getattr(fk, "column", None)
                parent = getattr(fk, "parent", None)
                if parent is not None and column is not None:
                    parent_table = getattr(parent, "table", None)
                    column_table = getattr(column, "table", None)
                    if same_table(parent_table, A) and same_table(column_table, B):
                        add(A_q, getattr(parent, "name", None))
                        add(B_q, getattr(column, "name", None))

            # Check B -> A
            for fk in getattr(B, "foreign_keys", []):
                column = getattr(fk, "column", None)
                parent = getattr(fk, "parent", None)
                if parent is not None and column is not None:
                    parent_table = getattr(parent, "table", None)
                    column_table = getattr(column, "table", None)
                    if same_table(parent_table, B) and same_table(column_table, A):
                        add(B_q, getattr(parent, "name", None))
                        add(A_q, getattr(column, "name", None))

        if not fkeys:
            raise ForeignKeyError(
                f"No foreign key relationship between {A_q or node_a} and {B_q or node_b}"
            )

        self._cache[cache_key] = dict(fkeys)
        return self._cache[cache_key]

    def _get_column_foreign_keys(
        self,
        columns: t.List[str],
        foreign_keys: dict,
        table: str = None,
        schema: str = None,
    ) -> list:
        """
        Get the foreign keys where the columns are provided.

        e.g
            foreign_keys = {
                'schema.table_a': ['column_a', 'column_b', 'column_X'],
                'schema.table_b': ['column_x'],
                'schema.table_c': ['column_y']
            }
            columns = ['column_a', 'column_b']
            returns ['column_a', 'column_b']
        """
        # TODO: normalize this elsewhere
        try:
            column_names: t.List[str] = [column.name for column in columns]
        except AttributeError:
            column_names: t.List[str] = [column for column in columns]

        if table is None:
            for table, cols in foreign_keys.items():
                if set(cols).issubset(set(column_names)):
                    return foreign_keys[table]
            # No match found - return empty list instead of None
            return []
        else:
            # only return the intersection of columns that match
            if not table.startswith(f"{schema}."):
                table = f"{schema}.{table}"
            # FIX: Don't modify list while iterating - create new filtered list
            print(f"[DEBUG _get_column_foreign_keys] table={table}, foreign_keys[table]={foreign_keys.get(table)}, columns={column_names}")
            # Check if table exists in foreign_keys dict
            if table not in foreign_keys:
                print(f"[DEBUG _get_column_foreign_keys] table {table} not in FK dict, returning empty")
                return []
            filtered_keys = [value for value in foreign_keys[table] if value in column_names]
            print(f"[DEBUG _get_column_foreign_keys] filtered_keys={filtered_keys}")
            return filtered_keys

    def _get_child_keys(
        self, node: Node, params: dict
    ) -> sa.sql.elements.Label:
        row = JSON_CAST(
            JSON_OBJECT(
                node.table,
                params,
            )
        )
        for child in node.children:
            if (
                not child.parent.relationship.throughs
                and child.parent.relationship.type == ONE_TO_MANY
            ):
                row = JSON_CONCAT(
                    row, JSON_CAST(JSON_AGG(child._subquery.c._keys))
                )
            else:
                row = JSON_CONCAT(
                    row, JSON_CAST(JSON_ARRAY(child._subquery.c._keys))
                )

        return row.label("_keys")

    def _root(
        self,
        node: Node,
        txmin: t.Optional[int] = None,
        txmax: t.Optional[int] = None,
        ctid: t.Optional[dict] = None,
    ) -> None:
        columns = [
            JSON_ARRAY(
                *[
                    child._subquery.c._keys
                    for child in node.children
                    if hasattr(
                        child._subquery.c,
                        "_keys",
                    )
                ]
            ),
            self._json_build_object(node.columns),
            *node.primary_keys,
        ]
        node._subquery = sa.select(*columns)

        if self.from_obj is not None:
            node._subquery = node._subquery.select_from(self.from_obj)

        if ctid is not None:
            subquery = []
            for page, rows in ctid.items():
                subquery.append(
                    sa.select(
                        *[
                            JSON_CAST(
                                sa.literal_column(f"'({page},'")
                                .concat(sa.column("s"))
                                .concat(")"),
                                TupleIdentifierType,
                            )
                        ]
                    ).select_from(
                        sa.sql.Values(
                            sa.column("s"),
                        )
                        .data([(row,) for row in rows])
                        .alias("s")
                    )
                )
            if subquery:
                node._filters.append(
                    sa.or_(
                        *[
                            node.model.c.ctid
                            == sa.any_(sa.func.ARRAY(q.scalar_subquery()))
                            for q in subquery
                        ]
                    )
                )

        if txmin:
            node._filters.append(
                sa.cast(
                    sa.cast(
                        node.model.c.xmin,
                        sa.Text,
                    ),
                    sa.BigInteger,
                )
                >= txmin
            )
        if txmax:
            node._filters.append(
                sa.cast(
                    sa.cast(
                        node.model.c.xmin,
                        sa.Text,
                    ),
                    sa.BigInteger,
                )
                < txmax
            )

        # Apply filters to all nodes (not just root)
        # For child nodes (LATERAL subqueries), this includes correlation with parent
        if node._filters:
            node._subquery = node._subquery.where(sa.and_(*node._filters))
        node._subquery = node._subquery.alias()

        if not node.is_root:
            if not IS_MYSQL_COMPAT:
                node._subquery = node._subquery.lateral()

    def _children(self, node: Node) -> None:
        print(f"[DEBUG _children] Processing node: {node.table}, children count: {len(node.children)}")
        for child in node.children:
            print(f"[DEBUG _children] Processing child: {child.table}, label: {child.label}, parent: {child.parent.table}")
            onclause: t.List = []

            if child.relationship.throughs:
                child.parent.columns.extend(
                    [
                        child.label,
                        child._subquery.c[child.label],
                    ]
                )

                through: Node = child.relationship.throughs[0]
                foreign_keys: dict = self.get_foreign_keys(
                    child.parent, through
                )

                left_foreign_keys: list = self._get_column_foreign_keys(
                    child._subquery.columns,
                    foreign_keys,
                    table=through.name,
                    schema=child.schema,
                )
                right_foreign_keys: list = self._get_column_foreign_keys(
                    child.parent.model.columns,
                    foreign_keys,
                )

                for i in range(len(right_foreign_keys)):
                    onclause.append(
                        child._subquery.c[left_foreign_keys[i]]
                        == child.parent.model.c[right_foreign_keys[i]]
                    )

            else:
                child.parent.columns.extend(
                    [
                        child.label,
                        child._subquery.c[child.label],
                    ]
                )

                foreign_keys: dict = self.get_foreign_keys(node, child)
                print(f"[DEBUG _children] FK lookup: {node.table} -> {child.table}, result: {foreign_keys}")
                left_foreign_keys: list = self._get_column_foreign_keys(
                    child._subquery.columns,
                    foreign_keys,
                )
                print(f"[DEBUG _children] left_foreign_keys: {left_foreign_keys}")

                if left_foreign_keys == child.table:
                    right_foreign_keys = left_foreign_keys
                else:
                    right_foreign_keys: list = self._get_column_foreign_keys(
                        child.parent.model.columns,
                        foreign_keys,
                    )

                # For LATERAL subqueries, add correlation as WHERE clause inside the subquery
                # For non-LATERAL, add to JOIN ON clause
                for i in range(len(left_foreign_keys)):
                    correlation_clause = (
                        child._subquery.c[left_foreign_keys[i]]
                        == child.parent.model.c[right_foreign_keys[i]]
                    )

                    # Add to onclause for JOIN
                    onclause.append(correlation_clause)

            # For LATERAL subqueries, add correlation as a filter to the child node
            # This must happen before the child's subquery is aliased
            if not child.is_root and not IS_MYSQL_COMPAT:
                # Add correlation filters to child node before its subquery is finalized
                for i in range(len(left_foreign_keys)):
                    # Create correlation: child.foreign_key = parent.primary_key
                    # Note: child.model hasn't been aliased yet, so we use it directly
                    child._filters.append(
                        child.model.c[left_foreign_keys[i]]
                        == child.parent.model.c[right_foreign_keys[i]]
                    )

            if self.from_obj is None:
                self.from_obj = child.parent.model

            if child._filters:

                for _filter in child._filters:
                    if isinstance(_filter, sa.sql.elements.BinaryExpression):
                        for column in _filter._orig:
                            if hasattr(column, "value"):
                                _column = child._subquery.c
                                if column._orig_key in node.table_columns:
                                    _column = node.model.c
                                if hasattr(_column, column._orig_key):
                                    onclause.append(
                                        _column[column._orig_key]
                                        == column.value
                                    )
                    elif isinstance(
                        _filter,
                        sa.sql.elements.BooleanClauseList,
                    ):
                        for clause in _filter.clauses:
                            for column in clause._orig:
                                if hasattr(column, "value"):
                                    _column = child._subquery.c
                                    if column._orig_key in node.table_columns:
                                        _column = node.model.c
                                    if hasattr(_column, column._orig_key):
                                        onclause.append(
                                            _column[column._orig_key]
                                            == column.value
                                        )
                if self.verbose:
                    compiled_query(child._subquery, "child._subquery")

            op = sa.and_
            if child.table == child.parent.table:
                op = sa.or_
            print(f"[DEBUG _children] Creating join for {child.table}, onclause count: {len(onclause)}")
            if len(onclause) == 0:
                print(f"[DEBUG _children] WARNING: Empty onclause for {child.table}! This will create a CROSS JOIN!")
            self.from_obj = self.from_obj.join(
                child._subquery,
                onclause=op(*onclause),
                isouter=self.isouter,
            )
            print(f"[DEBUG _children] Join created for {child.table}")
            # Log the SQL query
            try:
                from sqlalchemy.dialects import postgresql
                compiled = str(child._subquery.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
                print(f"[DEBUG SQL] {child.table} subquery: {compiled[:500]}")
            except:
                pass
            # Log the SQL query
            try:
                from sqlalchemy.dialects import postgresql
                compiled = str(child._subquery.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
                print(f"[DEBUG SQL] {child.table} subquery: {compiled[:500]}")
            except:
                pass

    def _through(self, node: Node) -> None:  # noqa: C901
        through: Node = node.relationship.throughs[0]
        # base: fks from through -> node
        base = self.get_foreign_keys(through, node)
        foreign_keys: t.Dict[str, t.List[str]] = {
            k: list(v) for k, v in base.items()
        }

        for table, cols in self.get_foreign_keys(through, node.parent).items():
            if table not in foreign_keys:
                continue
            dst = foreign_keys[table]
            # extend uniquely and preserve order
            dst.extend([col for col in cols if col not in dst])

        foreign_key_columns: list = self._get_column_foreign_keys(
            node.model.columns,
            foreign_keys,
            table=node.table,
            schema=node.schema,
        )

        params: list = []
        for foreign_key_column in foreign_key_columns:
            params.append(
                JSON_OBJECT(
                    str(foreign_key_column),
                    JSON_ARRAY(node.model.c[foreign_key_column]),
                )
            )

        _keys: sa.sql.elements.Label = self._get_child_keys(
            node, JSON_ARRAY(*params).label("_keys")
        )

        columns = [_keys]
        # We need to include through keys and the actual keys
        if node.relationship.variant == SCALAR:
            columns.append(node.columns[1].label("anon"))
        elif node.relationship.variant == OBJECT:
            if node.relationship.type == ONE_TO_ONE:
                if not node.children:
                    columns.append(
                        JSON_OBJECT(
                            node.columns[0],
                            node.columns[1],
                        ).label("anon")
                    )
                else:
                    columns.append(
                        self._json_build_object(node.columns).label("anon")
                    )
            elif node.relationship.type == ONE_TO_MANY:
                columns.append(
                    self._json_build_object(node.columns).label("anon")
                )

        columns.extend(
            [
                node.model.c[foreign_key_column]
                for foreign_key_column in foreign_key_columns
            ]
        )

        from_obj = None

        for child in node.children:
            onclause = []

            if child.relationship.throughs:
                child_through: Node = child.relationship.throughs[0]
                child_foreign_keys: dict = self.get_foreign_keys(
                    child, child_through
                )
                for key, values in self.get_foreign_keys(
                    child_through,
                    child.parent,
                ).items():
                    if key in child_foreign_keys:
                        for value in values:
                            if value not in child_foreign_keys[key]:
                                child_foreign_keys[key].append(value)
                        continue
                    child_foreign_keys[key] = values

                left_foreign_keys: list = self._get_column_foreign_keys(
                    child._subquery.columns,
                    child_foreign_keys,
                    table=child_through.table,
                    schema=child.schema,
                )

            else:
                child_foreign_keys: dict = self.get_foreign_keys(
                    child.parent, child
                )
                left_foreign_keys: list = self._get_column_foreign_keys(
                    child._subquery.columns,
                    child_foreign_keys,
                )

            right_foreign_keys: list = child_foreign_keys[child.parent.name]

            for i in range(len(left_foreign_keys)):
                onclause.append(
                    child._subquery.c[left_foreign_keys[i]]
                    == child.parent.model.c[right_foreign_keys[i]]
                )

            if from_obj is None:
                from_obj = node.model

            if child._filters:

                for _filter in child._filters:
                    if isinstance(_filter, sa.sql.elements.BinaryExpression):
                        for column in _filter._orig:
                            if hasattr(column, "value"):
                                _column = child._subquery.c
                                if column._orig_key in node.table_columns:
                                    _column = node.model.c
                                if hasattr(
                                    _column,
                                    column._orig_key,
                                ):
                                    onclause.append(
                                        _column[column._orig_key]
                                        == column.value
                                    )
                    elif isinstance(
                        _filter,
                        sa.sql.elements.BooleanClauseList,
                    ):
                        for clause in _filter.clauses:
                            for column in clause._orig:
                                if hasattr(column, "value"):
                                    _column = child._subquery.c
                                    if column._orig_key in node.table_columns:
                                        _column = node.model.c
                                    if hasattr(_column, column._orig_key):
                                        onclause.append(
                                            _column[column._orig_key]
                                            == column.value
                                        )

            from_obj = from_obj.join(
                child._subquery,
                onclause=sa.and_(*onclause),
                isouter=self.isouter,
            )

        outer_subquery = sa.select(*columns)

        parent_foreign_key_columns: list = self._get_column_foreign_keys(
            through.columns,
            base,
            schema=node.schema,
        )
        where: list = []
        for i in range(len(foreign_key_columns)):
            where.append(
                node.model.c[foreign_key_columns[i]]
                == through.model.c[parent_foreign_key_columns[i]]
            )
        outer_subquery = outer_subquery.where(sa.and_(*where))

        if node._filters:
            outer_subquery = outer_subquery.where(sa.and_(*node._filters))

        if from_obj is not None:
            outer_subquery = outer_subquery.select_from(from_obj)

        if IS_MYSQL_COMPAT:
            outer_subquery = outer_subquery.alias()
        else:
            outer_subquery = outer_subquery.alias().lateral()

        if self.verbose:
            compiled_query(outer_subquery, "Outer subquery")

        params = []
        for primary_key in through.model.primary_keys:
            params.append(
                JSON_OBJECT(
                    str(primary_key),
                    JSON_ARRAY(through.model.c[primary_key]),
                )
            )

        through_keys = JSON_CAST(
            JSON_OBJECT(
                node.relationship.throughs[0].table,
                JSON_ARRAY(*params),
            ),
        )

        # book author through table
        _keys = JSON_AGG(
            JSON_CONCAT(JSON_CAST(outer_subquery.c._keys), through_keys)
        ).label("_keys")

        left_foreign_keys = foreign_keys[node.name]
        right_foreign_keys: list = self._get_column_foreign_keys(
            through.columns,
            base,
            table=through.table,
            schema=node.schema,
        )

        columns = [
            _keys,
            JSON_AGG(outer_subquery.c.anon).label(node.label),
        ]

        foreign_keys: dict = self.get_foreign_keys(node.parent, through)

        for column in foreign_keys[through.name]:
            columns.append(through.model.c[str(column)])

        inner_subquery = sa.select(*columns)

        if self.verbose:
            compiled_query(inner_subquery, "Inner subquery")

        onclause: list = []
        for i in range(len(left_foreign_keys)):
            onclause.append(
                outer_subquery.c[left_foreign_keys[i]]
                == through.model.c[right_foreign_keys[i]]
            )

        op = sa.and_
        if node.table == node.parent.table:
            op = sa.or_

        from_obj = through.model.join(
            outer_subquery,
            onclause=op(*onclause),
            isouter=self.isouter,
        )

        node._subquery = inner_subquery.select_from(from_obj)

        # NB do not apply filters to the child node as they are applied to the parent
        # if node._filters:
        #     node._subquery = node._subquery.where(sa.and_(*node._filters))

        node._subquery = node._subquery.group_by(
            *[through.model.c[column] for column in foreign_keys[through.name]]
        )

        if self.verbose:
            compiled_query(node._subquery, "Combined subquery")

        node._subquery = node._subquery.alias()
        if not node.is_root:
            if not IS_MYSQL_COMPAT:
                node._subquery = node._subquery.lateral()

    def _non_through(self, node: Node) -> None:  # noqa: C901
        from_obj = None

        for child in node.children:
            onclause: t.List = []

            foreign_keys: dict = self.get_foreign_keys(node, child)
            table: t.Optional[str] = (
                child.relationship.throughs[0].table
                if child.relationship.throughs
                else None
            )
            foreign_key_columns: list = self._get_column_foreign_keys(
                child._subquery.columns,
                foreign_keys,
                table=table,
                schema=child.schema,
            )

            for i in range(len(foreign_key_columns)):
                onclause.append(
                    child._subquery.c[foreign_key_columns[i]]
                    == node.model.c[foreign_keys[node.name][i]]
                )

            if from_obj is None:
                from_obj = node.model

            if child._filters:

                for _filter in child._filters:
                    if isinstance(_filter, sa.sql.elements.BinaryExpression):
                        for column in _filter._orig:
                            if hasattr(column, "value"):
                                _column = child._subquery.c
                                if column._orig_key in node.table_columns:
                                    _column = node.model.c
                                if hasattr(_column, column._orig_key):
                                    onclause.append(
                                        _column[column._orig_key]
                                        == column.value
                                    )
                    elif isinstance(
                        _filter,
                        sa.sql.elements.BooleanClauseList,
                    ):
                        for clause in _filter.clauses:
                            for column in clause._orig:
                                if hasattr(column, "value"):
                                    _column = child._subquery.c
                                    if column._orig_key in node.table_columns:
                                        _column = node.model.c
                                    if hasattr(_column, column._orig_key):
                                        onclause.append(
                                            _column[column._orig_key]
                                            == column.value
                                        )

            from_obj = from_obj.join(
                child._subquery,
                onclause=sa.and_(*onclause),
                isouter=self.isouter,
            )

        foreign_keys: dict = self.get_foreign_keys(node.parent, node)

        foreign_key_columns: list = self._get_column_foreign_keys(
            node.model.columns,
            foreign_keys,
            table=node.table,
            schema=node.schema,
        )

        params: list = []
        if node.parent.is_root:
            for primary_key in node.primary_keys:
                params.extend(
                    [
                        str(primary_key.name),
                        JSON_ARRAY(node.model.c[primary_key.name]),
                    ]
                )
        else:
            for primary_key in node.primary_keys:
                params.extend(
                    [
                        str(primary_key.name),
                        node.model.c[primary_key.name],
                    ]
                )

        if node.relationship.type == ONE_TO_ONE:
            _keys = self._get_child_keys(node, self._json_build_object(params))
        elif node.relationship.type == ONE_TO_MANY:
            _keys = self._get_child_keys(
                node, JSON_AGG(self._json_build_object(params))
            )

        columns: t.List = [_keys]

        if node.relationship.variant == SCALAR:
            # TODO: Raise exception here if the number of columns > 1
            if node.relationship.type == ONE_TO_ONE:
                columns.append(node.model.c[node.columns[0]].label(node.label))
            elif node.relationship.type == ONE_TO_MANY:
                columns.append(
                    JSON_AGG(node.model.c[node.columns[0]]).label(node.label)
                )
        elif node.relationship.variant == OBJECT:
            if node.relationship.type == ONE_TO_ONE:
                columns.append(
                    self._json_build_object(node.columns).label(node.label)
                )
            elif node.relationship.type == ONE_TO_MANY:
                columns.append(
                    JSON_AGG(self._json_build_object(node.columns)).label(
                        node.label
                    )
                )

        for column in foreign_key_columns:
            columns.append(node.model.c[column])

        node._subquery = sa.select(*columns)

        if from_obj is not None:
            node._subquery = node._subquery.select_from(from_obj)

        parent_foreign_key_columns: list = self._get_column_foreign_keys(
            node.parent.model.columns,
            foreign_keys,
            table=node.parent.table,
            schema=node.parent.schema,
        )
        print(f"[DEBUG _non_through] Node: {node.table}, FK columns check")
        print(f"[DEBUG _non_through] foreign_key_columns: {foreign_key_columns}, length: {len(foreign_key_columns)}")
        print(f"[DEBUG _non_through] parent_foreign_key_columns: {parent_foreign_key_columns}, length: {len(parent_foreign_key_columns)}")

        # Validate FK columns match in length
        if len(foreign_key_columns) != len(parent_foreign_key_columns):
            print(f"[DEBUG _non_through] WARNING: FK column count mismatch for {node.table}! Skipping WHERE clause")
            print(f"[DEBUG _non_through] This usually means auto-detection failed. Check schema.json foreign_key specification")
            # Skip WHERE clause - will return all rows (not ideal but won't crash)
            where: list = []
        else:
            where: list = []
            for i in range(len(foreign_key_columns)):
                where.append(
                    node.model.c[foreign_key_columns[i]]
                    == node.parent.model.c[parent_foreign_key_columns[i]]
                )
        print(f"[DEBUG _non_through] Node: {node.table}, WHERE clauses: {len(where)}")
        print(f"[DEBUG _non_through] foreign_key_columns: {foreign_key_columns}")
        print(f"[DEBUG _non_through] parent_foreign_key_columns: {parent_foreign_key_columns}")
        if where:
            node._subquery = node._subquery.where(sa.and_(*where))
        else:
            print(f"[DEBUG _non_through] WARNING: No WHERE clause for {node.table}! This will return all rows!")

        # NB do not apply filters to the child node as they are applied to the parent
        # if node._filters:
        #     node._subquery = node._subquery.where(sa.and_(*node._filters))

        if node.relationship.type == ONE_TO_MANY:
            node._subquery = node._subquery.group_by(
                *[node.model.c[key] for key in foreign_key_columns]
            )
        node._subquery = node._subquery.alias()

        if not node.is_root:
            if not IS_MYSQL_COMPAT:
                node._subquery = node._subquery.lateral()

    def build_queries(
        self,
        node: Node,
        filters: t.Optional[dict] = None,
        txmin: t.Optional[int] = None,
        txmax: t.Optional[int] = None,
        ctid: t.Optional[dict] = None,
    ) -> None:
        """Build node query."""
        self.from_obj = None
        _filters = self._build_filters(filters, node)
        if _filters is not None:
            node._filters.append(_filters)

        # 1) add all child columns from one level below
        self._children(node)

        if node.is_root:
            self._root(node, txmin=txmin, txmax=txmax, ctid=ctid)
        else:
            # 2) subquery: these are for children creating their own columns
            if node.relationship.throughs:
                self._through(node)
            else:
                self._non_through(node)
