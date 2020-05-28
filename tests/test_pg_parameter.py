import pytest
import psycopg2
import psycopg2.extras
from rdsparamsync import PostgreSQLParameter

@pytest.fixture()
def cursor():
    conn = psycopg2.connect('postgres://localhost:5432')
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    return cur

def setting(cursor, name):
    cursor.execute("SELECT * FROM pg_settings WHERE name = %s", (name,))
    return cursor.fetchone()


def test_vacuum_cost_delay(cursor):
    row = setting(cursor, 'vacuum_cost_delay')
    param = PostgreSQLParameter(row)

    assert param.value() == row['setting']
    assert param.name() == 'vacuum_cost_delay'
    assert param.normalize() == row['setting']
    assert param.unit() == 'MS'
    assert param.is_modifiable() == False


def test_wal_buffers(cursor):
    row = setting(cursor, 'wal_buffers')
    param = PostgreSQLParameter(row)

    assert param.value() == row['setting']
    assert param.normalize() == str(int(row['setting']) * 8)


def test_wal_compression(cursor):
    row = setting(cursor, 'wal_compression')
    param = PostgreSQLParameter(row)

    assert param.value() == row['setting']
    assert param.normalize() == '0' if row['setting'] == 'off' else '1'

def test_eq(cursor):
    row = setting(cursor, 'wal_compression')
    p1 = PostgreSQLParameter(row)
    p2 = PostgreSQLParameter(row)

    assert p1 == p2

    p3 = PostgreSQLParameter(setting(cursor, 'vacuum_cost_delay'))

    assert p1 != p3
