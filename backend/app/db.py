from contextlib import contextmanager

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


class WorkerLeaseLost(RuntimeError):
    pass


class Database:
    def __init__(self, url: str):
        self.pool = ConnectionPool(
            url, min_size=1, max_size=8, open=False, kwargs={"row_factory": dict_row}, timeout=10
        )

    def open(self):
        self.pool.open(wait=True, timeout=10)

    def close(self):
        self.pool.close()

    @contextmanager
    def transaction(self):
        with self.pool.connection() as conn:
            with conn.transaction():
                yield conn

    def all(self, sql, params=()):
        with self.transaction() as conn:
            return conn.execute(sql, params).fetchall()

    def one(self, sql, params=()):
        with self.transaction() as conn:
            return conn.execute(sql, params).fetchone()
