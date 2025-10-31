# migrate_add_admin_cols.py
import sqlite3
from contextlib import closing
from core.db import get_conn   # نفس دالتك الموجودة في المشروع

SQLS = [
    "ALTER TABLE schools ADD COLUMN admin_username TEXT",
    "ALTER TABLE schools ADD COLUMN admin_password TEXT",
]

with closing(get_conn()) as conn:
    c = conn.cursor()
    for sql in SQLS:
        try:
            c.execute(sql)
            print("✅ نفِّذت:", sql)
        except sqlite3.OperationalError as e:
            # إذا كانت الأعمدة موجودة مسبقًا سنتجاهل الخطأ
            if "duplicate column name" in str(e).lower():
                print("ℹ️ موجود مسبقًا:", sql)
            else:
                raise
    conn.commit()

# تحقق سريع
c.execute("PRAGMA table_info(schools)")
print("أعمدة schools الآن:")
for row in c.fetchall():
    print(row)
