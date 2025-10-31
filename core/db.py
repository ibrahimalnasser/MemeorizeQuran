# -*- coding: utf-8 -*-
"""
core/db.py
-----------
قاعدة بيانات منصة حفّاظ القرآن — نسخة موحدة حديثة
تشمل:
- إنشاء الجداول الأساسية
- دعم تعدد المدارس (multi-school)
- إدارة المستخدمين (super_admin / school_admin / teacher / parent / student / visitor)
- إدارة الطلاب والمعلّمين والمجموعات
- خريطة الصفحة ↔ الآية
"""

import os
import sqlite3
from contextlib import closing
from typing import List, Tuple, Dict, Optional
from collections import defaultdict

# =============================
# ثوابت عامة
# =============================
DB_PATH = "hifz.db"
TOTAL_QURAN_PAGES_NOMINAL = 604


# =========================================================
# دالة الاتصال
# =========================================================
def get_conn() -> sqlite3.Connection:
    """فتح اتصال جديد بقاعدة البيانات مع إعدادات الأداء."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    conn.execute("PRAGMA cache_size=-8000;")
    return conn


# =========================================================
# التحقق من الأعمدة والجداول
# =========================================================
def _table_exists(table: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    ok = c.fetchone() is not None
    conn.close()
    return ok


def _col_exists(table: str, col: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in c.fetchall()]
    conn.close()
    return col in cols


def _add_column_if_missing(table: str, col: str, decl: str):
    if not _col_exists(table, col):
        with closing(sqlite3.connect(DB_PATH, check_same_thread=False)) as conn:
            c = conn.cursor()
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
            conn.commit()


def ensure_admin_password_column():
    """يضيف عمود كلمة مرور الآدمن إلى جدول المدارس إن لم يكن موجودًا"""
    from contextlib import closing
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("PRAGMA table_info(schools)")
        cols = [r[1] for r in c.fetchall()]
        if "admin_password" not in cols:
            c.execute(
                "ALTER TABLE schools ADD COLUMN admin_password TEXT DEFAULT '0000'")
            conn.commit()


def ensure_teacher_password_column():
    """يضيف عمود كلمة المرور إلى جدول المعلمين إن لم يكن موجودًا"""
    from contextlib import closing
    if not _table_exists("teachers"):
        return
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("PRAGMA table_info(teachers)")
        cols = [r[1] for r in c.fetchall()]
        if "password" not in cols:
            c.execute(
                "ALTER TABLE teachers ADD COLUMN password TEXT DEFAULT '123456'")
            conn.commit()


def ensure_goals_columns():
    """يضيف الأعمدة المفقودة إلى جدول الأهداف (goal_type, target, period)"""
    from contextlib import closing
    if not _table_exists("goals"):
        return
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("PRAGMA table_info(goals)")
        cols = [r[1] for r in c.fetchall()]

        if "goal_type" not in cols:
            c.execute("ALTER TABLE goals ADD COLUMN goal_type TEXT")
        if "target" not in cols:
            c.execute("ALTER TABLE goals ADD COLUMN target INTEGER")
        if "period" not in cols:
            c.execute("ALTER TABLE goals ADD COLUMN period TEXT")

        conn.commit()

# =========================================================
# إنشاء الجداول الأساسية
# =========================================================


def init_db():
    """تهيئة قاعدة البيانات وإنشاء جميع الجداول اللازمة إذا لم تكن موجودة."""
    with closing(get_conn()) as conn:
        c = conn.cursor()

        # المدارس
        c.execute("""
        CREATE TABLE IF NOT EXISTS schools (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            admin_name TEXT,
            email TEXT,
            phone TEXT,
            address TEXT,
            visitor_password TEXT DEFAULT '0000'
        )
        """)

        # المستخدمون
        c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT CHECK(role IN ('super_admin','school_admin','teacher','parent','student','visitor')) NOT NULL,
            related_id INTEGER DEFAULT NULL,
            school_id INTEGER DEFAULT NULL
        )
        """)

        # المعلّمون
        c.execute("""
        CREATE TABLE IF NOT EXISTS teachers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            gender TEXT DEFAULT 'ذكر',
            birth_date TEXT,
            phone TEXT,
            email TEXT,
            memorization_note TEXT,
            is_mujaz INTEGER DEFAULT 0,
            password TEXT DEFAULT '123456',
            school_id INTEGER
        )
        """)

        # المجموعات
        c.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            teacher TEXT,
            teacher_id INTEGER,
            school_id INTEGER,
            FOREIGN KEY (teacher_id) REFERENCES teachers (id)
        )
        """)

        # الطلاب
        c.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            gender TEXT DEFAULT 'ذكر',
            birth_date TEXT,
            join_date TEXT,
            group_id INTEGER,
            phone TEXT,
            email TEXT,
            guardian_name TEXT,
            school_id INTEGER,
            FOREIGN KEY (group_id) REFERENCES groups (id)
        )
        """)

        # صفحات الحفظ
        c.execute("""
        CREATE TABLE IF NOT EXISTS student_pages (
            student_id INTEGER,
            page_number INTEGER,
            is_memorized INTEGER,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (student_id, page_number)
        )
        """)

        # مدى الآيات المحفوظة
        c.execute("""
        CREATE TABLE IF NOT EXISTS student_ayah_ranges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            surah_id INTEGER,
            from_ayah INTEGER,
            to_ayah INTEGER,
            is_memorized INTEGER,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            source TEXT DEFAULT 'manual'
        )
        """)

        # الأهداف
        c.execute("""
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            category TEXT,
            periodicity TEXT,
            target_kind TEXT,
            page_from INTEGER,
            page_to INTEGER,
            surah_id INTEGER,
            from_ayah INTEGER,
            to_ayah INTEGER,
            per_session_qty INTEGER,
            start_date TEXT,
            due_date TEXT,
            end_date TEXT,
            status TEXT,
            achieved_at TEXT,
            note TEXT,
            goal_type TEXT,
            target INTEGER,
            period TEXT
        )
        """)

        # المكافآت
        c.execute("""
        CREATE TABLE IF NOT EXISTS rewards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            points INTEGER DEFAULT 0,
            badge TEXT,
            note TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # خريطة الصفحة ↔ الآية
        c.execute("""
        CREATE TABLE IF NOT EXISTS ref_page_ayahs (
            page_number INTEGER,
            surah_id INTEGER,
            ayah INTEGER
        )
        """)

        conn.commit()


# =========================================================
# تهيئة تعدد المدارس والمستخدمين
# =========================================================
def ensure_multischool():
    """يضمن أن كل الجداول تحتوي على school_id وأن المستخدمين والافتراضيات موجودة."""
    with closing(sqlite3.connect(DB_PATH, check_same_thread=False)) as conn:
        c = conn.cursor()

        # أضف school_id للجداول الناقصة
        for t in ("users", "teachers", "groups", "students"):
            _add_column_if_missing(t, "school_id", "INTEGER")

        conn.commit()

        # مدرسة افتراضية
        c.execute("SELECT id FROM schools WHERE name='مدرسة افتراضية' LIMIT 1")
        row = c.fetchone()
        if row is None:
            c.execute("INSERT INTO schools(name, admin_name, visitor_password) VALUES(?,?,?)",
                      ("مدرسة افتراضية", "أدمن افتراضي", "0000"))
            conn.commit()
            default_sid = c.lastrowid
        else:
            default_sid = row[0]

        # تحديث السجلات القديمة بدون school_id
        for t in ("teachers", "groups", "students"):
            if _table_exists(t):
                c.execute(
                    f"UPDATE {t} SET school_id=? WHERE school_id IS NULL OR school_id=''", (default_sid,))
        c.execute("UPDATE users SET school_id=? WHERE (school_id IS NULL OR school_id='') AND (role!='super_admin')",
                  (default_sid,))
        conn.commit()

        # super_admin
        c.execute("SELECT id FROM users WHERE role='super_admin' LIMIT 1")
        if c.fetchone() is None:
            c.execute("""
                INSERT INTO users(username, password, role, related_id, school_id)
                VALUES(?,?,?,?,?)
            """, ("root", "root123", "super_admin", None, None))
            conn.commit()

        # school_admin
        c.execute(
            "SELECT id FROM users WHERE role='school_admin' AND school_id=? LIMIT 1", (default_sid,))
        if c.fetchone() is None:
            c.execute("""
                INSERT INTO users(username, password, role, related_id, school_id)
                VALUES(?,?,?,?,?)
            """, ("admin", "admin123", "school_admin", None, default_sid))
            conn.commit()


# =========================================================
# التحقق من المستخدمين والمدارس
# =========================================================
# =============================
# 🔐 التحقق من المستخدم (تسجيل الدخول)
# =============================
def authenticate_user(username: str, password: str):
    """
    تتحقق هذه الدالة من بيانات تسجيل الدخول.
    يمكن أن يكون المستخدم:
    - super_admin  (مدير النظام الكامل)
    - school_admin (مدير مدرسة)
    - teacher      (معلم مدرسة)
    - visitor      (زائر مدرسة)
    تعيد tuple بشكل: (user_id, role, related_id, school_id, name)
    """
    from contextlib import closing
    from core.db import get_conn

    with closing(get_conn()) as conn:
        c = conn.cursor()

        # ✅ أولاً: تحقق من جدول المستخدمين الرئيسيين (super_admin / school_admin)
        c.execute("""
            SELECT id, role, related_id, school_id, username
            FROM users
            WHERE username=? AND password=?
        """, (username, password))
        row = c.fetchone()

        # ✅ ثانيًا: تحقق من جدول المعلمين (teachers)
        if not row:
            c.execute("""
                SELECT id, 'teacher' AS role, id AS rel_id, school_id, name
                FROM teachers
                WHERE name=? AND password=?
            """, (username, password))
            row = c.fetchone()

        # ✅ ثالثًا: تحقق من الزوار (visitor)
        if not row:
            c.execute("""
                SELECT id, 'visitor' AS role, NULL AS rel_id, id AS school_id, name
                FROM schools
                WHERE visitor_password=? AND (name=? OR ?='')
            """, (password, username, username))
            row = c.fetchone()

        # 🔹 في حال النجاح
        if row:
            return row  # (id, role, rel_id, school_id, name)
        else:
            return None


def authenticate_visitor(school_name: str, vpass: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, name FROM schools WHERE name=? AND visitor_password=? LIMIT 1",
              (school_name, vpass))
    row = c.fetchone()
    conn.close()
    return row


def get_school_name(sid: int) -> str:
    if not sid:
        return ""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name FROM schools WHERE id=?", (sid,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else ""


# =========================================================
# خريطة الصفحة ↔ الآية (للقلب)
# =========================================================
_PAGE_MAP_CACHE: Optional[Dict[int, List[Tuple[int, int]]]] = None


def has_page_ayah_map() -> bool:
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM ref_page_ayahs;")
        return (c.fetchone()[0] or 0) >= 6000


def get_page_map(force_refresh: bool = False) -> Dict[int, List[Tuple[int, int]]]:
    global _PAGE_MAP_CACHE
    if _PAGE_MAP_CACHE is not None and not force_refresh:
        return _PAGE_MAP_CACHE
    mp: Dict[int, List[Tuple[int, int]]] = defaultdict(list)
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute(
            "SELECT page_number, surah_id, ayah FROM ref_page_ayahs ORDER BY page_number, surah_id, ayah")
        for p, s, a in c.fetchall():
            mp[p].append((s, a))
    _PAGE_MAP_CACHE = mp
    return mp


def iso_date(date_str: str) -> bool:
    """يتحقق من أن النص يمثل تاريخًا بصيغة YYYY-MM-DD"""
    from datetime import datetime
    try:
        datetime.strptime(date_str.strip(), "%Y-%m-%d")
        return True
    except Exception:
        return False


def invalidate_page_map_cache():
    """تفريغ ذاكرة الكاش الخاصة بخريطة الصفحة ↔ الآية"""
    global _page_ayah_map_cache
    _page_ayah_map_cache = None


# =========================================================
# مراجع السور والأجزاء الثابتة
# =========================================================

# قائمة السور مع عدد الآيات ورقم أول صفحة
SURAH_DATA = [
    (1, "الفاتحة", 7, 1),
    (2, "البقرة", 286, 2),
    (3, "آل عمران", 200, 50),
    (4, "النساء", 176, 77),
    (5, "المائدة", 120, 106),
    (6, "الأنعام", 165, 128),
    (7, "الأعراف", 206, 151),
    (8, "الأنفال", 75, 177),
    (9, "التوبة", 129, 187),
    (10, "يونس", 109, 208),
    (11, "هود", 123, 221),
    (12, "يوسف", 111, 235),
    (13, "الرعد", 43, 249),
    (14, "إبراهيم", 52, 255),
    (15, "الحجر", 99, 262),
    (16, "النحل", 128, 267),
    (17, "الإسراء", 111, 282),
    (18, "الكهف", 110, 293),
    (19, "مريم", 98, 305),
    (20, "طه", 135, 312),
    (21, "الأنبياء", 112, 322),
    (22, "الحج", 78, 332),
    (23, "المؤمنون", 118, 342),
    (24, "النور", 64, 350),
    (25, "الفرقان", 77, 359),
    (26, "الشعراء", 227, 367),
    (27, "النمل", 93, 377),
    (28, "القصص", 88, 385),
    (29, "العنكبوت", 69, 396),
    (30, "الروم", 60, 404),
    (31, "لقمان", 34, 411),
    (32, "السجدة", 30, 415),
    (33, "الأحزاب", 73, 418),
    (34, "سبأ", 54, 428),
    (35, "فاطر", 45, 434),
    (36, "يس", 83, 440),
    (37, "الصافات", 182, 446),
    (38, "ص", 88, 453),
    (39, "الزمر", 75, 458),
    (40, "غافر", 85, 467),
    (41, "فصلت", 54, 477),
    (42, "الشورى", 53, 483),
    (43, "الزخرف", 89, 489),
    (44, "الدخان", 59, 496),
    (45, "الجاثية", 37, 499),
    (46, "الأحقاف", 35, 502),
    (47, "محمد", 38, 507),
    (48, "الفتح", 29, 511),
    (49, "الحجرات", 18, 515),
    (50, "ق", 45, 518),
    (51, "الذاريات", 60, 520),
    (52, "الطور", 49, 523),
    (53, "النجم", 62, 526),
    (54, "القمر", 55, 528),
    (55, "الرحمن", 78, 531),
    (56, "الواقعة", 96, 534),
    (57, "الحديد", 29, 537),
    (58, "المجادلة", 22, 542),
    (59, "الحشر", 24, 545),
    (60, "الممتحنة", 13, 549),
    (61, "الصف", 14, 551),
    (62, "الجمعة", 11, 553),
    (63, "المنافقون", 11, 554),
    (64, "التغابن", 18, 556),
    (65, "الطلاق", 12, 558),
    (66, "التحريم", 12, 560),
    (67, "الملك", 30, 562),
    (68, "القلم", 52, 564),
    (69, "الحاقة", 52, 566),
    (70, "المعارج", 44, 568),
    (71, "نوح", 28, 570),
    (72, "الجن", 28, 572),
    (73, "المزمل", 20, 574),
    (74, "المدثر", 56, 575),
    (75, "القيامة", 40, 577),
    (76, "الإنسان", 31, 578),
    (77, "المرسلات", 50, 580),
    (78, "النبأ", 40, 582),
    (79, "النازعات", 46, 583),
    (80, "عبس", 42, 585),
    (81, "التكوير", 29, 586),
    (82, "الانفطار", 19, 587),
    (83, "المطففين", 36, 587),
    (84, "الانشقاق", 25, 589),
    (85, "البروج", 22, 590),
    (86, "الطارق", 17, 591),
    (87, "الأعلى", 19, 591),
    (88, "الغاشية", 26, 592),
    (89, "الفجر", 30, 593),
    (90, "البلد", 20, 594),
    (91, "الشمس", 15, 595),
    (92, "الليل", 21, 595),
    (93, "الضحى", 11, 596),
    (94, "الشرح", 8, 596),
    (95, "التين", 8, 597),
    (96, "العلق", 19, 597),
    (97, "القدر", 5, 598),
    (98, "البينة", 8, 598),
    (99, "الزلزلة", 8, 599),
    (100, "العاديات", 11, 599),
    (101, "القارعة", 11, 600),
    (102, "التكاثر", 8, 600),
    (103, "العصر", 3, 601),
    (104, "الهمزة", 9, 601),
    (105, "الفيل", 5, 601),
    (106, "قريش", 4, 602),
    (107, "الماعون", 7, 602),
    (108, "الكوثر", 3, 602),
    (109, "الكافرون", 6, 603),
    (110, "النصر", 3, 603),
    (111, "المسد", 5, 603),
    (112, "الإخلاص", 4, 604),
    (113, "الفلق", 5, 604),
    (114, "الناس", 6, 604),
]

# بداية كل جزء (juz)
JUZ_STARTS = [
    (1, 1), (2, 22), (3, 42), (4, 62), (5, 82), (6, 102),
    (7, 122), (8, 142), (9, 162), (10, 182), (11, 202), (12, 222),
    (13, 242), (14, 262), (15, 282), (16, 302), (17, 322), (18, 342),
    (19, 362), (20, 382), (21, 402), (22, 422), (23, 442), (24, 462),
    (25, 482), (26, 502), (27, 522), (28, 542), (29, 562), (30, 582),
]


def get_surah_refs() -> List[Tuple[int, str, int, int, int]]:
    """إرجاع قائمة السور من المرجع الثابت."""
    out = []
    for i, (sid, name, ayahs, start_page) in enumerate(SURAH_DATA):
        next_start = SURAH_DATA[i + 1][3] if i + \
            1 < len(SURAH_DATA) else TOTAL_QURAN_PAGES_NOMINAL
        end_page = next_start - 1 if next_start > start_page else start_page
        out.append((sid, name, ayahs, start_page, end_page))
    return out


def get_juz_refs() -> List[Tuple[int, int, int]]:
    """إرجاع قائمة الأجزاء."""
    refs = []
    for i, (juz, start) in enumerate(JUZ_STARTS):
        end = JUZ_STARTS[i + 1][1] - 1 if i + \
            1 < len(JUZ_STARTS) else TOTAL_QURAN_PAGES_NOMINAL
        refs.append((juz, start, end))
    return refs
