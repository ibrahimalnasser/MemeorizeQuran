# -*- coding: utf-8 -*-
"""
app.py
------
نقطة التشغيل الرئيسية لمنصة حفّاظ القرآن.
تقوم بتهيئة قاعدة البيانات، تسجيل الدخول، وإدارة الصفحات تبعًا لدور المستخدم.
"""

import streamlit as st
from pathlib import Path
from core.db import init_db, ensure_multischool, authenticate_user, authenticate_visitor, get_school_name
from ui.pages import (
    header,
    page_main,
    page_students,
    page_teachers,
    page_groups,
    page_teacher_dashboard,
    page_import_export,
    page_backup,
    page_analytics,
    page_schools,
)


# =========================================================
# صفحة تسجيل الدخول
# =========================================================
def login_page():
    st.title("🔐 تسجيل الدخول إلى منصة حفّاظ القرآن")
    st.caption("اختر طريقة الدخول المناسبة 👇")

    tab1, tab2 = st.tabs(["🔑 دخول الإدارة والمعلمين", "👥 دخول الزوار"])

    # ----------------------------------------
    # تبويب 1: دخول الإدارة / المعلمين
    # ----------------------------------------
    with tab1:
        u = st.text_input("اسم المستخدم", key="login_user")
        p = st.text_input("كلمة المرور", type="password", key="login_pass")

        if st.button("دخول", use_container_width=True, key="login_btn_admin"):
            row = authenticate_user(u.strip(), p.strip())
            if row:
                uid, role, rel_id, sid, uname = row
                st.session_state.update({
                    "user_id": uid,
                    "user_role": role,
                    "user_rel_id": rel_id,
                    "school_id": sid,
                    "username": uname,
                })
                school_label = get_school_name(sid) if sid else "كل المدارس"
                st.success(
                    f"مرحبًا {uname} ({role}) — المدرسة: {school_label}")
                st.rerun()
            else:
                st.error("❌ اسم المستخدم أو كلمة المرور غير صحيحة.")

    # ----------------------------------------
    # تبويب 2: دخول الزوار
    # ----------------------------------------
    with tab2:
        school_name = st.text_input("اسم المدرسة", key="visitor_school")
        vpass = st.text_input(
            "كلمة سر الزوار", type="password", key="visitor_pass")
        if st.button("دخول الزوار", use_container_width=True, key="login_btn_visitor"):
            sch = authenticate_visitor(school_name.strip(), vpass.strip())
            if sch:
                sid, sname = sch
                st.session_state.update({
                    "user_id": None,
                    "user_role": "visitor",
                    "user_rel_id": None,
                    "school_id": sid,
                    "username": f"زائر - {sname}",
                })
                st.success(f"مرحبًا بزائر مدرسة: {sname}")
                st.rerun()
            else:
                st.error("❌ اسم المدرسة أو كلمة السر غير صحيحة.")


# =========================================================
# التطبيق الرئيسي
# =========================================================
def main():
    # إعداد الصفحة
    st.set_page_config(
        page_title="منصة حفّاظ القرآن",
        page_icon="❤️",
        layout="wide",
        initial_sidebar_state="auto",

    )

    # =========================================================
    # التنسيق الجمالي للصفحات
    # =========================================================

    # 1) تحميل خطوط Google (Amiri + Scheherazade New)
    st.markdown("""
    <link href="https://fonts.googleapis.com/css2?family=Amiri:wght@400;700&family=Scheherazade+New:wght@400;700&display=swap" rel="stylesheet">
    """, unsafe_allow_html=True)

    # 2) تحميل ملف CSS (حدّث المسار لو وضعته بمجلد آخر)
    css_path = Path(__file__).parent / "style_islamic.css"
    if css_path.exists():
        with open(css_path, "r", encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    else:
        st.warning(f"⚠️ ملف CSS غير موجود: {css_path}")

    # تهيئة قاعدة البيانات وبنية المدارس
    from core.db import ensure_admin_password_column, ensure_teacher_password_column
    init_db()
    ensure_multischool()
    ensure_admin_password_column()
    ensure_teacher_password_column()

    # رأس الصفحة العام
    header()

    # =====================================================
    # بيانات الجلسة والدخول
    # =====================================================
    role = st.session_state.get("user_role", None)
    sid = st.session_state.get("school_id", None)
    uname = st.session_state.get("username", "مستخدم")

    # إن لم يكن مسجلاً، افتح صفحة تسجيل الدخول
    if not role:
        login_page()
        return

    # =====================================================
    # الشريط الجانبي (Sidebar)
    # =====================================================
    with st.sidebar:
        school_label = get_school_name(sid) if sid else "كل المدارس"
        st.markdown(f"### 👋 مرحبًا {uname}")
        st.caption(f"الدور: **{role}** — المدرسة: **{school_label}**")

        if st.button("🔒 تسجيل الخروج"):
            st.session_state.clear()
            st.rerun()

    # =====================================================
    # توزيع الصفحات حسب الدور
    # =====================================================

    # --------- 1️⃣ سوبر أدمن ---------
    if role == "super_admin":
        tabs = st.tabs([
            "❤️ الواجهة الرئيسية",
            "🏫 المدارس وإدارتها",
            "👨‍🏫 المعلّمون",
            "👥 المجموعات",
            "👦👧 الطلاب",
            "📋 لوحة المعلم",
            "⬆️⬇️ استيراد/تصدير",
            "🗄️ نسخ احتياطي",
            "📈 إحصاءات",
        ])
        with tabs[0]:
            page_main()
        with tabs[1]:
            page_schools()
        with tabs[2]:
            page_teachers()
        with tabs[3]:
            page_groups()
        with tabs[4]:
            page_students()
        with tabs[5]:
            page_teacher_dashboard()
        with tabs[6]:
            page_import_export()
        with tabs[7]:
            page_backup()
        with tabs[8]:
            page_analytics()

    # --------- 2️⃣ أدمن المدرسة ---------
    elif role == "school_admin":
        tabs = st.tabs([
            "❤️ الواجهة الرئيسية",
            "👨‍🏫 المعلّمون",
            "👥 المجموعات",
            "👦👧 الطلاب",
            "📋 لوحة المعلم",
            "📈 إحصاءات",
        ])
        with tabs[0]:
            page_main()
        with tabs[1]:
            page_teachers()
        with tabs[2]:
            page_groups()
        with tabs[3]:
            page_students()
        with tabs[4]:
            page_teacher_dashboard()
        with tabs[5]:
            page_analytics()

    # --------- 3️⃣ المعلّم ---------
    elif role == "teacher":
        tabs = st.tabs([
            "❤️ الواجهة الرئيسية",
            "👦👧 الطلاب",
            "📋 لوحة المعلم",
            "📈 إحصاءات",
        ])
        with tabs[0]:
            page_main()
        with tabs[1]:
            page_students()
        with tabs[2]:
            page_teacher_dashboard()
        with tabs[3]:
            page_analytics()

    # --------- 4️⃣ الزائر ---------
    elif role == "visitor":
        tabs = st.tabs([
            "❤️ الواجهة الرئيسية",
            "📈 إحصاءات",
        ])
        with tabs[0]:
            page_main()
        with tabs[1]:
            page_analytics()

    # --------- 5️⃣ أي دور غير معروف ---------
    else:
        st.error("🚫 الدور غير معروف، الرجاء تسجيل الدخول مجددًا.")
        if st.button("إعادة تسجيل الدخول"):
            st.session_state.clear()
            st.rerun()


# =========================================================
# تشغيل التطبيق
# =========================================================
if __name__ == "__main__":
    main()
