# -*- coding: utf-8 -*-
"""
core/models.py
----------------
الوحدة المنطقية الرئيسية لمعالجة البيانات في منصة "روّاد القرآن":
- CRUD للطلاب والمعلمين والمجموعات
- حساب التقدّم والمزامنة
- النقاط والمكافآت
- الأهداف (Goals)
- دعم تعدد المدارس (Multi-school)
"""

import sqlite3
import math
from contextlib import closing
from datetime import datetime, timedelta, date
from collections import defaultdict
from typing import List, Dict, Tuple, Optional, DefaultDict

from core.db import get_conn, TOTAL_QURAN_PAGES_NOMINAL

# =============================
# الطلاب (Students)
# =============================

def add_student(full_name: str, gender: str, birth_date: str, join_date: str,
                group_id: Optional[int], phone: str = "", email: str = "",
                guardian_name: str = "", school_id: Optional[int] = None) -> int:
    """إضافة طالب جديد ضمن مدرسة معينة (إن وُجدت)."""
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO students(full_name, gender, birth_date, join_date, group_id, phone, email, guardian_name, school_id)
            VALUES(?,?,?,?,?,?,?,?,?)
        """, (full_name.strip(), gender, birth_date, join_date, group_id,
              phone.strip(), email.strip(), guardian_name.strip(), school_id))
        conn.commit()
        return c.lastrowid


def update_student_group(student_id: int, group_id: Optional[int]):
    """تحديث مجموعة الطالب."""
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("UPDATE students SET group_id=? WHERE id=?", (group_id, student_id))
        conn.commit()


def search_students(name: Optional[str], birth_date: Optional[str],
                    group_id: Optional[int] = None, school_id: Optional[int] = None) -> List[Tuple]:
    """البحث عن الطلاب باسم/تاريخ/مجموعة مع دعم المدرسة."""
    query = """
        SELECT id, full_name, gender, birth_date, join_date, IFNULL(group_id,0)
        FROM students WHERE 1=1
    """
    params = []
    if school_id:
        query += " AND IFNULL(school_id,0)=?"
        params.append(school_id)
    if name:
        query += " AND full_name LIKE ? COLLATE NOCASE"
        params.append(f"%{name.strip()}%")
    if birth_date:
        query += " AND birth_date = ?"
        params.append(birth_date)
    if group_id:
        query += " AND IFNULL(group_id,0)=?"
        params.append(group_id)
    query += " ORDER BY full_name COLLATE NOCASE"
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute(query, params)
        return c.fetchall()


def get_student(student_id: int) -> Optional[Tuple]:
    """إرجاع بيانات طالب واحد."""
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT id, full_name, gender, birth_date, join_date, IFNULL(group_id,0)
            FROM students WHERE id=?
        """, (student_id,))
        return c.fetchone()

# =============================
# المعلمون (Teachers)
# =============================

def get_teachers(school_id: Optional[int] = None) -> List[Tuple[int, str, str, str, str, str, str, int]]:
    """جلب جميع المعلمين مع إمكانية تصفية المدرسة."""
    query = """SELECT id, name, gender, COALESCE(birth_date,''), COALESCE(phone,''),
                      COALESCE(email,''), COALESCE(memorization_note,''), COALESCE(is_mujaz,0)
               FROM teachers"""
    params = []
    if school_id:
        query += " WHERE IFNULL(school_id,0)=?"
        params = [school_id]
    query += " ORDER BY name COLLATE NOCASE"
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute(query, params)
        return c.fetchall()

# =============================
# إنشاء/حذف معلم (Teachers CRUD)
# =============================

def add_teacher(name: str,
                gender: str = "ذكر",
                birth_date: str = "",
                phone: str = "",
                email: str = "",
                memorization_note: str = "",
                is_mujaz: bool = False,
                school_id: Optional[int] = None) -> int:
    """
    إضافة معلم جديد وربطه (اختياريًا) بمدرسة معيّنة.
    يعيد teacher_id.
    """
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO teachers(name, gender, birth_date, phone, email, memorization_note, is_mujaz, school_id)
            VALUES(?,?,?,?,?,?,?,?)
        """, (
            name.strip(),
            gender,
            (birth_date or "").strip(),
            phone.strip(),
            email.strip(),
            (memorization_note or "").strip(),
            1 if is_mujaz else 0,
            school_id
        ))
        conn.commit()
        return c.lastrowid


def delete_teacher(teacher_id: int) -> None:
    """
    حذف معلم بأمان:
    - إزالة أي حساب مستخدم مرتبط به (users.role='teacher' AND related_id=teacher_id)
    - فكّ ارتباطه من المجموعات: تعيين groups.teacher_id=NULL و groups.teacher=''
    - لا يحذف الطلاب؛ فقط يبقيهم ضمن مجموعاتهم
    - ثم حذف سجلّ المعلم من teachers
    """
    with closing(get_conn()) as conn:
        c = conn.cursor()

        # (1) امسح حسابات المستخدمين المرتبطة بهذا المعلّم (إن وُجدت)
        try:
            c.execute("DELETE FROM users WHERE role='teacher' AND related_id=?", (teacher_id,))
        except Exception:
            # في حال لم يكن جدول users موجودًا في نسخة قديمة، تجاهل
            pass

        # (2) اجلب اسم المعرّف النصي للمعلم (لإزالة الاسم النصي من المجموعات أيضًا)
        c.execute("SELECT COALESCE(name,'') FROM teachers WHERE id=?", (teacher_id,))
        row = c.fetchone()
        tname = (row[0] or "").strip() if row else ""

        # (3) فكّ ارتباطه من المجموعات
        c.execute("UPDATE groups SET teacher_id=NULL WHERE teacher_id=?", (teacher_id,))
        # إن كان الاسم محفوظًا نصيًا داخل groups.teacher، أفرغه أيضًا
        if tname:
            c.execute("UPDATE groups SET teacher='' WHERE TRIM(COALESCE(teacher,'')) = ?", (tname,))

        # (4) حذف المعلّم
        c.execute("DELETE FROM teachers WHERE id=?", (teacher_id,))
        conn.commit()


# =============================
# المجموعات (Groups)
# =============================

def get_groups(school_id: Optional[int] = None) -> List[Tuple[int, str, str]]:
    """جلب المجموعات حسب المدرسة (إن وُجدت)."""
    query = "SELECT id, name, IFNULL(teacher,'') FROM groups"
    params = []
    if school_id:
        query += " WHERE IFNULL(school_id,0)=?"
        params = [school_id]
    query += " ORDER BY name"
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute(query, params)
        return c.fetchall()


def get_groups_joined(school_id: Optional[int] = None) -> List[Tuple[int, str, str, int]]:
    """ترجع [(group_id, group_name, teacher_name, teacher_id)]"""
    query = """
        SELECT g.id, g.name,
               COALESCE(NULLIF(TRIM(g.teacher), ''), COALESCE(t.name, '')) AS teacher_name,
               COALESCE(g.teacher_id, 0) AS teacher_id
        FROM groups g
        LEFT JOIN teachers t ON t.id = g.teacher_id
    """
    params = []
    if school_id:
        query += " WHERE IFNULL(g.school_id,0)=?"
        params = [school_id]
    query += " ORDER BY g.name COLLATE NOCASE"
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute(query, params)
        return c.fetchall()


def add_group(name: str, teacher: str = "", school_id: Optional[int] = None) -> int:
    """إضافة مجموعة جديدة مرتبطة بمدرسة."""
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO groups(name, teacher, school_id)
            VALUES(?,?,?)
        """, (name.strip(), teacher.strip(), school_id))
        conn.commit()
        return c.lastrowid

# =============================
# الصفحات والآيات (Pages / Ayahs)
# =============================

def get_pages_for_student(student_id: int) -> Dict[int, int]:
    """جلب حالة حفظ الصفحات لطالب."""
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("SELECT page_number, is_memorized FROM student_pages WHERE student_id=?", (student_id,))
        return {r[0]: r[1] for r in c.fetchall()}


def upsert_page(student_id: int, page_number: int, is_mem: bool):
    """تحديث أو إدراج صفحة."""
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO student_pages(student_id, page_number, is_memorized)
            VALUES(?,?,?)
            ON CONFLICT(student_id, page_number)
            DO UPDATE SET is_memorized=excluded.is_memorized, updated_at=CURRENT_TIMESTAMP
        """, (student_id, page_number, 1 if is_mem else 0))
        conn.commit()


def add_ayah_range(student_id: int, surah_id: int, from_ayah: int, to_ayah: int, is_mem: bool, source: str = "manual"):
    """تسجيل مدى آيات محفوظة."""
    if to_ayah < from_ayah:
        from_ayah, to_ayah = to_ayah, from_ayah
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO student_ayah_ranges(student_id, surah_id, from_ayah, to_ayah, is_memorized, source)
            VALUES(?,?,?,?,?,?)
        """, (student_id, surah_id, from_ayah, to_ayah, 1 if is_mem else 0, source))
        conn.commit()

# =============================
# النقاط والمكافآت
# =============================

def points_summary(student_id: int, join_date_iso: str) -> Tuple[int, int]:
    """مجموع النقاط الكلية ونقاط الشهر الحالي."""
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("SELECT COALESCE(SUM(points),0) FROM rewards WHERE student_id=?", (student_id,))
        total = c.fetchone()[0] or 0
        first_day = date.today().replace(day=1).isoformat()
        today = date.today().isoformat()
        c.execute("""
            SELECT COALESCE(SUM(points),0)
            FROM rewards
            WHERE student_id=? AND DATE(created_at) BETWEEN ? AND ?
        """, (student_id, first_day, today))
        monthly = c.fetchone()[0] or 0
    return int(total), int(monthly)

# =============================
# التقدّم (Progress)
# =============================

def progress_by_juz(student_id: int) -> List[float]:
    from core.db import get_juz_refs
    pages_map = get_pages_for_student(student_id)
    refs = get_juz_refs()
    ratios = []
    for j, sp, ep in refs:
        total = ep - sp + 1
        mem = sum(1 for p, v in pages_map.items() if v == 1 and sp <= p <= ep)
        ratios.append(mem / total if total else 0)
    return ratios


def progress_by_surah(student_id: int) -> Tuple[List[float], List[int], List[str]]:
    from core.db import get_surah_refs
    merged = get_merged_ayahs_for_student(student_id)
    refs = get_surah_refs()
    ratios, weights, names = [], [], []
    for sid, name, ac, sp, ep in refs:
        total_ayahs = ac if ac else 1
        mem_ayahs = sum((t - f + 1) for (f, t) in merged.get(sid, []))
        ratios.append(min(1.0, mem_ayahs / total_ayahs))
        weights.append(max(1, ep - sp + 1))
        names.append(name)
    return ratios, weights, names


def overall_progress(student_id: int) -> Dict[str, float]:
    from core.db import get_surah_refs
    pages_map = get_pages_for_student(student_id)
    total_pages_mem = sum(1 for v in pages_map.values() if v == 1)
    sur_refs = get_surah_refs()
    merged = get_merged_ayahs_for_student(student_id)
    full_surahs = 0
    for sid, name, ac, sp, ep in sur_refs:
        covered = sum((t - f + 1) for (f, t) in merged.get(sid, []))
        if covered >= ac:
            full_surahs += 1
    overall_ratio = total_pages_mem / TOTAL_QURAN_PAGES_NOMINAL
    return {"total_pages_mem": total_pages_mem, "overall_ratio": overall_ratio, "full_surahs": full_surahs}

# =============================
# أدوات إضافية
# =============================

def calc_age(birth_iso: str) -> int:
    try:
        bd = datetime.strptime(birth_iso, "%Y-%m-%d").date()
        t = date.today()
        return t.year - bd.year - ((t.month, t.day) < (bd.month, bd.day))
    except Exception:
        return 0


def estimate_finish_date(student_id: int) -> Optional[str]:
    op = overall_progress(student_id)
    remaining = TOTAL_QURAN_PAGES_NOMINAL - op["total_pages_mem"]
    rate = weekly_rate_pages(student_id, 6)
    if rate <= 0:
        return None
    eta = date.today() + timedelta(days=int(7 * (remaining / rate)))
    return eta.isoformat()

# =============================
# المزامنة (Sync)
# =============================

def get_merged_ayahs_for_student(student_id: int) -> Dict[int, List[Tuple[int, int]]]:
    """إرجاع {surah_id: [(from,to),...]} للآيات المحفوظة."""
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT surah_id, from_ayah, to_ayah, is_memorized
            FROM student_ayah_ranges
            WHERE student_id=?
            ORDER BY surah_id, from_ayah
        """, (student_id,))
        rows = c.fetchall()

    def merge_intervals(ranges):
        merged = []
        for f, t in sorted(ranges):
            if not merged or merged[-1][1] < f - 1:
                merged.append((f, t))
            else:
                merged[-1] = (merged[-1][0], max(merged[-1][1], t))
        return merged

    data = defaultdict(list)
    for sid, f, t, is_mem in rows:
        if f > t:
            f, t = t, f
        if is_mem:
            data[sid].append((f, t))
    return {sid: merge_intervals(lst) for sid, lst in data.items()}

# =============================
# حذف
# =============================

def delete_student(student_id: int):
    with closing(get_conn()) as conn:
        c = conn.cursor()
        for t in ("student_pages", "student_ayah_ranges", "rewards", "goals"):
            c.execute(f"DELETE FROM {t} WHERE student_id=?", (student_id,))
        c.execute("DELETE FROM students WHERE id=?", (student_id,))
        conn.commit()


def delete_group_and_students(group_id: int):
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM students WHERE group_id=?", (group_id,))
        ids = [r[0] for r in c.fetchall()]
        for sid in ids:
            delete_student(sid)
        c.execute("DELETE FROM groups WHERE id=?", (group_id,))
        conn.commit()

# =============================
# أهداف الطالب (Goals)
# =============================

AR_CATEGORY = {"memorization": "الحفظ", "review": "المراجعة", "reading": "القراءة", "listening": "الاستماع"}
AR_PERIODICITY = {"once": "مرّة واحدة", "weekly": "أسبوعي", "monthly": "شهري"}
AR_TARGET_KIND = {"pages": "صفحات", "ayahs": "آيات"}

def _to_code_category(ar): return next((k for k,v in AR_CATEGORY.items() if v==ar), "memorization")
def _to_code_periodicity(ar): return next((k for k,v in AR_PERIODICITY.items() if v==ar), "once")
def _to_code_target_kind(ar): return next((k for k,v in AR_TARGET_KIND.items() if v==ar), "pages")

_GOAL_STATUS_AR = {"pending": "ليس بعد", "done": "تم", "failed": "لم ينجز"}
_GOAL_STATUS_REV = {v: k for k, v in _GOAL_STATUS_AR.items()}

def _goal_status_to_ar(c): return _GOAL_STATUS_AR.get(c, c)
def _goal_status_from_ar(a): return _GOAL_STATUS_REV.get(a, "pending")


def get_active_goals_map(student_id: int) -> Dict[str, set]:
    """
    جلب خريطة الأهداف (pending و done) للطالب.
    يعيد قاموس بمفاتيح 'pages' و 'surahs' تحتوي على مجموعات الأرقام المستهدفة.
    """
    goals_map = {"pages": set(), "surahs": set()}

    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT target_kind, page_from, page_to, surah_id
            FROM goals
            WHERE student_id=? AND status IN ('pending', 'done')
        """, (student_id,))

        for target_kind, page_from, page_to, surah_id in c.fetchall():
            if target_kind == "pages" and page_from and page_to:
                for p in range(page_from, page_to + 1):
                    goals_map["pages"].add(p)
            elif target_kind == "ayahs" and surah_id:
                goals_map["surahs"].add(surah_id)

    return goals_map


def auto_check_goals(student_id: int) -> int:
    """
    فحص تلقائي للأهداف وتحديث حالتها بناءً على الحفظ الفعلي.
    يعيد عدد الأهداف التي تم تحديثها.
    """
    updated_count = 0
    with closing(get_conn()) as conn:
        c = conn.cursor()

        # جلب جميع الأهداف المعلقة (pending)
        c.execute("""
            SELECT id, target_kind, page_from, page_to, surah_id, from_ayah, to_ayah
            FROM goals
            WHERE student_id=? AND status='pending'
        """, (student_id,))

        pending_goals = c.fetchall()

        for goal_row in pending_goals:
            goal_id, target_kind, page_from, page_to, surah_id, from_ayah, to_ayah = goal_row
            is_achieved = False

            # فحص الأهداف المبنية على الصفحات
            if target_kind == "pages" and page_from and page_to:
                c.execute("""
                    SELECT COUNT(*) FROM student_pages
                    WHERE student_id=? AND page_number BETWEEN ? AND ? AND is_memorized=1
                """, (student_id, page_from, page_to))
                memorized_count = c.fetchone()[0]
                target_count = page_to - page_from + 1
                is_achieved = (memorized_count >= target_count)

            # فحص الأهداف المبنية على الآيات
            elif target_kind == "ayahs" and surah_id and from_ayah and to_ayah:
                # جلب جميع الآيات المحفوظة للسورة المحددة
                c.execute("""
                    SELECT from_ayah, to_ayah FROM student_ayah_ranges
                    WHERE student_id=? AND surah_id=? AND is_memorized=1
                """, (student_id, surah_id))

                memorized_ayahs = set()
                for ayah_from, ayah_to in c.fetchall():
                    for ayah in range(ayah_from, ayah_to + 1):
                        memorized_ayahs.add(ayah)

                # فحص إذا كانت جميع الآيات المستهدفة محفوظة
                target_ayahs = set(range(from_ayah, to_ayah + 1))
                is_achieved = target_ayahs.issubset(memorized_ayahs)

            # تحديث الهدف إذا تحقق
            if is_achieved:
                c.execute("""
                    UPDATE goals
                    SET status='done', achieved_at=?
                    WHERE id=?
                """, (datetime.now().isoformat(timespec="seconds"), goal_id))
                updated_count += 1

        conn.commit()

    return updated_count

# =============================
# دوال مساعدة إضافية
# =============================

def pages_memorized_between(student_id: int, start: date, end: date) -> int:
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT COUNT(*) FROM student_pages
            WHERE student_id=? AND is_memorized=1
              AND DATE(updated_at) BETWEEN ? AND ?
        """, (student_id, start.isoformat(), end.isoformat()))
        return c.fetchone()[0]


def weekly_rate_pages(student_id: int, weeks: int = 4) -> float:
    end = date.today()
    start = end - timedelta(days=7*weeks)
    pages = pages_memorized_between(student_id, start, end)
    return pages / max(1, weeks)

# =============================
# 🧠 المزامنة بين الصفحات والآيات (Sync Bidirectional)
# =============================

def _merge_consecutive(nums: List[int]) -> List[Tuple[int, int]]:
    """دمج الأرقام المتتالية في مديات."""
    if not nums:
        return []
    nums = sorted(set(nums))
    start = end = nums[0]
    merged = []
    for n in nums[1:]:
        if n == end + 1:
            end = n
        else:
            merged.append((start, end))
            start = end = n
    merged.append((start, end))
    return merged


def sync_pages_from_surah(student_id: int) -> int:
    """مزامنة الصفحات من جدول الآيات (ayah_ranges)."""
    from core.db import get_page_map, has_page_ayah_map
    if not has_page_ayah_map():
        return 0

    merged = get_merged_ayahs_for_student(student_id)
    ayahs_by_surah = {sid: set() for sid in merged}
    for sid, ranges in merged.items():
        for a, b in ranges:
            ayahs_by_surah[sid].update(range(a, b + 1))

    page_map = get_page_map()
    to_upsert = []
    for p, pairs in page_map.items():
        if all(ay in ayahs_by_surah.get(sid, set()) for sid, ay in pairs):
            to_upsert.append((student_id, p, 1))

    if not to_upsert:
        return 0

    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.executemany("""
            INSERT INTO student_pages(student_id, page_number, is_memorized)
            VALUES(?,?,?)
            ON CONFLICT(student_id, page_number)
            DO UPDATE SET is_memorized=excluded.is_memorized,
                          updated_at=CURRENT_TIMESTAMP
        """, to_upsert)
        conn.commit()

    return len(to_upsert)


def sync_surah_from_pages(student_id: int) -> int:
    """مزامنة الآيات من جدول الصفحات (pages)."""
    from core.db import get_page_map, has_page_ayah_map
    if not has_page_ayah_map():
        return 0

    page_map = get_page_map()
    pages = {p for p, v in get_pages_for_student(student_id).items() if v == 1}
    ayahs = defaultdict(list)

    for p in pages:
        for sid, ay in page_map.get(p, []):
            ayahs[sid].append(ay)

    rows = []
    for sid, ays in ayahs.items():
        for a, b in _merge_consecutive(ays):
            rows.append((student_id, sid, a, b, 1, "page"))

    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM student_ayah_ranges WHERE student_id=? AND source='page'", (student_id,))
        if rows:
            c.executemany("""
                INSERT INTO student_ayah_ranges(student_id, surah_id, from_ayah, to_ayah, is_memorized, source)
                VALUES(?,?,?,?,?,?)
            """, rows)
        conn.commit()

    return len(rows)


def sync_bidirectional(student_id: int, max_passes: int = 5) -> Tuple[int, int]:
    """
    المزامنة الثنائية الاتجاه:
    - من الآيات إلى الصفحات
    - من الصفحات إلى الآيات
    تعيد (عدد الصفحات المحدثة، عدد السور المحدثة)
    """
    total_pages = 0
    total_surahs = 0
    for _ in range(max_passes):
        a = sync_pages_from_surah(student_id)
        b = sync_surah_from_pages(student_id)
        total_pages += a
        total_surahs += b
        if a == 0 and b == 0:
            break
    return total_pages, total_surahs


from datetime import date
from contextlib import closing
from core.db import get_conn

def _top5_month_points(group_id=None):
    """
    تُرجع أفضل 5 طلاب في النقاط هذا الشهر.
    يمكن تحديد group_id لتصفية النتائج على مجموعة معينة.
    """
    start = date.today().replace(day=1).isoformat()
    end = date.today().isoformat()
    with closing(get_conn()) as conn:
        c = conn.cursor()
        if group_id:
            c.execute("""
                SELECT s.full_name, g.name, SUM(r.points) AS pts
                FROM rewards r
                JOIN students s ON s.id = r.student_id
                LEFT JOIN groups g ON s.group_id = g.id
                WHERE DATE(r.created_at) BETWEEN ? AND ? AND s.group_id=?
                GROUP BY s.id
                ORDER BY pts DESC
                LIMIT 5
            """, (start, end, group_id))
        else:
            c.execute("""
                SELECT s.full_name, g.name, SUM(r.points) AS pts
                FROM rewards r
                JOIN students s ON s.id = r.student_id
                LEFT JOIN groups g ON s.group_id = g.id
                WHERE DATE(r.created_at) BETWEEN ? AND ?
                GROUP BY s.id
                ORDER BY pts DESC
                LIMIT 5
            """, (start, end))
        return c.fetchall()


def _top5_month_pages(group_id=None):
    """
    تُرجع أفضل 5 طلاب حسب عدد الصفحات المحفوظة هذا الشهر.
    """
    start = date.today().replace(day=1).isoformat()
    end = date.today().isoformat()
    with closing(get_conn()) as conn:
        c = conn.cursor()
        if group_id:
            c.execute("""
                SELECT s.full_name, g.name, COUNT(sp.page_number) AS pages
                FROM student_pages sp
                JOIN students s ON s.id = sp.student_id
                LEFT JOIN groups g ON s.group_id = g.id
                WHERE sp.is_memorized=1 AND DATE(sp.updated_at) BETWEEN ? AND ? AND s.group_id=?
                GROUP BY s.id
                ORDER BY pages DESC
                LIMIT 5
            """, (start, end, group_id))
        else:
            c.execute("""
                SELECT s.full_name, g.name, COUNT(sp.page_number) AS pages
                FROM student_pages sp
                JOIN students s ON s.id = sp.student_id
                LEFT JOIN groups g ON s.group_id = g.id
                WHERE sp.is_memorized=1 AND DATE(sp.updated_at) BETWEEN ? AND ?
                GROUP BY s.id
                ORDER BY pages DESC
                LIMIT 5
            """, (start, end))
        return c.fetchall()


def _render_podium(rows, unit_label="نقطة"):
    """
    عرض أفضل 3 طلاب بطريقة جميلة تشبه منصة التتويج.
    rows = [(student_name, group_name, value), ...]
    """
    import streamlit as st

    st.markdown("#### 🥇🥈🥉 منصة التتويج")
    for i, (name, gname, value) in enumerate(rows):
        medal = "🥇" if i == 0 else ("🥈" if i == 1 else ("🥉" if i == 2 else "🏅"))
        st.write(f"{medal} **{name}** ({gname}) — {value} {unit_label}")
