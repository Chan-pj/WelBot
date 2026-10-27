import pymysql
from werkzeug.security import generate_password_hash, check_password_hash
from config import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, DB_PORT

def get_connection():
    return pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        db=DB_NAME,
        port=DB_PORT,
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

def search_welfare(keyword):
    sql = """
        SELECT s.servId, s.servNm, s.jurOrgNm, s.servDgst,
               s.servDtlLink, s.onapPsbltYn,
               d.tgtrDtlCn, d.alwServCn
        FROM servList s
        LEFT JOIN servDetail d ON s.servId = d.servId
        WHERE s.servNm LIKE %s OR s.servDgst LIKE %s
        LIMIT 5
    """
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (f"%{keyword}%", f"%{keyword}%"))
            return cursor.fetchall()

def save_chat(session_id, role, message, user_id):
    sql = "INSERT INTO chat_history (session_id, role, message, user_id, created_at) VALUES (%s, %s, %s, %s, NOW())"
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (session_id, role, message, user_id))
            conn.commit()

def get_chat_history(session_id):
    sql = "SELECT role, message FROM chat_history WHERE session_id = %s ORDER BY created_at ASC"
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (session_id,))
            return cursor.fetchall()

def register_user(username, password, region):
    sql = "INSERT INTO users (username, password, role, region, created_at) VALUES (%s, %s, 1, %s, NOW())"
    with get_connection() as conn:
        with conn.cursor() as cursor:
            try:
                # 비밀번호는 평문 대신 해시로 저장
                cursor.execute(sql, (username, generate_password_hash(password), region))
                conn.commit()
                return True
            except pymysql.err.IntegrityError:
                return False

def login_user(username, password):
    sql = "SELECT id, username, password, role, region FROM users WHERE username=%s"
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (username,))
            user = cursor.fetchone()
    if not user or not check_password_hash(user.pop("password"), password):
        return None
    return user

def get_all_users():
    sql = "SELECT id, username, role, region, created_at FROM users ORDER BY created_at DESC"
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql)
            return cursor.fetchall()

def delete_user(user_id):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM chat_history WHERE user_id = %s", (user_id,))
            cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
            conn.commit()

def get_regions():
    sql = "SELECT DISTINCT ctpvNm, sggNm FROM servList WHERE ctpvNm <> '' AND sggNm IS NOT NULL"
    regions = {}
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql)
            for r in cursor.fetchall():
                regions.setdefault(r["ctpvNm"], [])
                if r["sggNm"].endswith(("시", "군", "구")):
                    regions[r["ctpvNm"]].append(r["sggNm"])
    return {sido: sorted(sggs) for sido, sggs in regions.items()}
