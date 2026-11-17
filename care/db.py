"""每个业务操作使用一条连接；离开事务时提交，异常时回滚。"""
from contextlib import contextmanager
import pyodbc

from .config import CONNECTION_STRING


def connect():
    return pyodbc.connect(CONNECTION_STRING, timeout=10)


@contextmanager
def transaction(restricted=False):
    connection = connect()
    try:
        if restricted:
            connection.execute("EXECUTE AS USER='care_app'")
        yield Repository(connection)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        if restricted:
            connection.execute("REVERT")
        connection.close()


class Repository:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, *params):
        return self.connection.cursor().execute(sql, params)

    def all(self, sql, *params):
        cursor = self.execute(sql, *params)
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def one(self, sql, *params):
        cursor = self.execute(sql, *params)
        row = cursor.fetchone()
        return (
            dict(zip([column[0] for column in cursor.description], row))
            if row
            else None
        )

    def scalar(self, sql, *params):
        return self.execute(sql, *params).fetchval()

    def insert(self, sql, *params):
        cursor = self.execute(
            "SET NOCOUNT ON; " + sql + "; SELECT CAST(SCOPE_IDENTITY() AS int)", *params
        )
        while cursor.description is None:
            cursor.nextset()
        return cursor.fetchval()

    def call(self, name, *params):
        # name 仅由业务代码给定，不接收页面输入。
        cursor = self.execute(f"EXEC {name} " + ",".join("?" for _ in params), *params)
        while cursor.description is None:
            if not cursor.nextset():
                return None
        columns = [column[0] for column in cursor.description]
        row = cursor.fetchone()
        return dict(zip(columns, row)) if row else None

    def batch(self, sql, rows):
        self.connection.cursor().executemany(sql, rows)

    def audit(self, entity, entity_id, action, actor_id, detail):
        self.execute(
            "INSERT audit_log(entity,entity_id,action,actor_id,detail) VALUES(?,?,?,?,?)",
            entity,
            entity_id,
            action,
            actor_id,
            detail,
        )
