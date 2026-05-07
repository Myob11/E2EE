import threading
import time
from services.auth_service.main import get_db_conn


CONN = None


def setup_test_data():
    conn = get_db_conn()
    with conn:
        with conn.cursor() as cur:
            # create a test user and device
            cur.execute("INSERT INTO users (user_id, username, password) VALUES ('test_user_x', 'test_user_x', 'x') ON CONFLICT DO NOTHING")
            cur.execute("INSERT INTO devices (user_id, device_id, identity_key, signed_prekey, one_time_prekeys) VALUES ('test_user_x', 'dev1', 'idk', 'spk', '[]'::jsonb) ON CONFLICT (user_id, device_id) DO NOTHING")
            # clear any existing prekeys
            cur.execute("DELETE FROM one_time_prekeys WHERE user_id = %s AND device_id = %s", ('test_user_x', 'dev1'))
            # insert 5 prekeys
            for i in range(5):
                cur.execute("INSERT INTO one_time_prekeys (user_id, device_id, prekey) VALUES (%s, %s, %s)", ('test_user_x', 'dev1', f'pk{i}'))
    conn.close()


results = []
lock = threading.Lock()


def consume_once():
    conn = get_db_conn()
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH sel AS (
                    SELECT id, prekey FROM one_time_prekeys
                    WHERE user_id = %s AND device_id = %s
                    ORDER BY id
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                DELETE FROM one_time_prekeys WHERE id IN (SELECT id FROM sel) RETURNING prekey
                """,
                ('test_user_x', 'dev1'),
            )
            row = cur.fetchone()
            if row:
                try:
                    pk = row['prekey']
                except Exception:
                    pk = row[0]
                with lock:
                    results.append(pk)
    conn.close()


def test_concurrent_consumption():
    setup_test_data()
    threads = []
    for _ in range(10):
        t = threading.Thread(target=consume_once)
        threads.append(t)
        t.start()
    for t in threads:
        t.join()

    # results should be unique and at most 5
    assert len(results) <= 5
    assert len(set(results)) == len(results)

