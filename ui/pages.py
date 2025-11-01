# -*- coding: utf-8 -*-
"""
ui/pages.py
------------
واجهات Streamlit لمنصة حفّاظ القرآن (الإصدار المتعدد المدارس):
- الصفحة الرئيسية (page_main)
- إدارة الطلاب والمعلمين والمجموعات والمدارس
- لوحة المعلم
- الإحصاءات
- النسخ الاحتياطي
"""

from datetime import datetime, timedelta, date
from contextlib import closing
from typing import Optional, List, Tuple, Dict
import streamlit.components.v1 as components
import pandas as pd
import streamlit as st

# من قلب النظام
from core.db import (
    get_conn,
    get_surah_refs,
    get_juz_refs,
    get_school_name,
    has_page_ayah_map,
    invalidate_page_map_cache,
    TOTAL_QURAN_PAGES_NOMINAL,
    iso_date,
)


# من النماذج
from core.models import (
    add_student,
    update_student_group,
    search_students,
    get_student,
    get_groups,
    get_groups_joined,
    get_teachers,
    add_group,
    delete_student,
    delete_group_and_students,
    progress_by_juz,
    progress_by_surah,
    overall_progress,
    get_pages_for_student,
    get_merged_ayahs_for_student,
    sync_bidirectional,
    points_summary,
    add_ayah_range,
    upsert_page,
    estimate_finish_date,
    calc_age,
)

from ui.heart import make_heart_svg


# ================================
# أدوات مساعدة عامة
# ================================
def percent(ratio: float) -> str:
    try:
        return f"{int(round(float(ratio) * 100))}%"
    except Exception:
        return "0%"


def _clear_modal_query_params(keep_sid: Optional[int] = None):
    st.query_params.clear()
    if keep_sid:
        st.query_params.update({"page": "main", "sid": str(keep_sid)})


def _arm_dialog_from_query():
    """تحقق من معاملات الرابط واضبط علم فتح الحوار."""
    qp = st.query_params
    if qp.get("dlg") and qp.get("seg"):
        dlg = qp.get("dlg")
        try:
            seg = int(qp.get("seg"))
        except Exception:
            return
        # اضبط علم الحوار في session_state
        st.session_state["dialog_mode"] = dlg
        st.session_state["dialog_seg"] = seg
        st.session_state["show_dialog"] = True


# ================================
# رأس الصفحة
# ================================
def header():
    st.markdown(
        "<h2 style='text-align:center;'>🌟 منصة حفّاظ القرآن — وَفِي ذَٰلِكَ فَلْيَتَنَافَسِ الْمُتَنَافِسُونَ 🌟</h2>",
        unsafe_allow_html=True,
    )


# ================================
# الحوارات (Dialogs)
# ================================
def open_surah_dialog(student_id: int, surah_no: int):
    """نافذة إدخال مدى آيات سورة محددة."""
    surahs = get_surah_refs()
    options = [(i + 1, row[1], int(row[2])) for i, row in enumerate(surahs)]
    default_index = max(0, min(len(options) - 1, surah_no - 1))

    @st.dialog("إدخال حفظ للسورة")
    def _dlg():
        sel_idx = st.selectbox(
            "السورة",
            list(range(len(options))),
            index=default_index,
            key=f"surah_pick_{student_id}",
            format_func=lambda i: f"{options[i][0]:03d} — {options[i][1]} ({options[i][2]} آية)",
        )
        sel_no, sel_name, sel_ayah_cnt = options[sel_idx]
        st.markdown(
            f"### إدخال حفظ للسورة رقم **{sel_no}** – **{sel_name}** ({sel_ayah_cnt} آية)")
        st.caption(f"أقصى رقم آية في هذه السورة: **{sel_ayah_cnt}**")

        with st.form(f"dlg_add_ayahs_{student_id}_{sel_no}", clear_on_submit=False):
            from_a = st.number_input("من الآية", min_value=1, step=1, value=1)
            to_a = st.number_input("إلى الآية", min_value=1, step=1, value=1)
            op = st.radio("نوع العملية", [
                          "إضافة حفظ", "حذف حفظ"], horizontal=True, index=0)
            colA, colB = st.columns(2)
            submitted = colA.form_submit_button("تسجيل")
            closed = colB.form_submit_button("إغلاق")

            if submitted:
                a, b = int(from_a), int(to_a)
                if a > b:
                    a, b = b, a
                if a < 1 or b > sel_ayah_cnt:
                    st.error(f"المدى غير صالح. عدد الآيات = {sel_ayah_cnt}.")
                    st.stop()
                add_ayah_range(student_id, sel_no, a, b,
                               (op == "إضافة حفظ"), source="manual")
                # فحص وتحديث الأهداف تلقائيًا
                from core.models import auto_check_goals
                goals_updated = auto_check_goals(student_id)
                msg = f"تم تسجيل الآيات {a}–{b} من سورة {sel_name}."
                if goals_updated > 0:
                    msg += f" ✅ تم إنجاز {goals_updated} هدف!"
                st.success(msg)
                _clear_modal_query_params(student_id)
                st.rerun()

            if closed:
                _clear_modal_query_params(student_id)
                st.rerun()

    _dlg()


def open_juz_dialog(student_id: int, jnum: int):
    """نافذة إدخال مدى صفحات جزء محدد."""
    row = [r for r in get_juz_refs() if r[0] == jnum][0]
    _, sp, ep = row

    @st.dialog("إدخال صفحات محفوظة للجزء")
    def _dlg():
        st.markdown(
            f"### إدخال صفحات محفوظة للجزء **{jnum}** (الصفحات {sp}–{ep})")
        with st.form(f"dlg_add_pages_{student_id}_{jnum}", clear_on_submit=False):
            from_p = st.number_input(
                "من الصفحة", min_value=sp, step=1, value=sp)
            to_p = st.number_input(
                "إلى الصفحة", min_value=sp, step=1, value=sp)
            op = st.radio("نوع العملية", [
                          "إضافة حفظ", "حذف حفظ"], horizontal=True, index=0)
            colA, colB = st.columns(2)
            submit = colA.form_submit_button("تسجيل", type="primary")
            close = colB.form_submit_button("إغلاق")

            if close:
                _clear_modal_query_params(student_id)
                st.rerun()

            if submit:
                a, b = int(from_p), int(to_p)
                if a > b or a < sp or b > ep:
                    st.error(f"المدى غير صالح. يجب أن يكون بين {sp} و {ep}.")
                    st.stop()
                is_add = (op == "إضافة حفظ")
                for p in range(a, b + 1):
                    upsert_page(student_id, p, is_add)
                # فحص وتحديث الأهداف تلقائيًا
                from core.models import auto_check_goals
                goals_updated = auto_check_goals(student_id)
                msg = f"تم تسجيل الصفحات {a}–{b}."
                if goals_updated > 0:
                    msg += f" ✅ تم إنجاز {goals_updated} هدف!"
                st.success(msg)
                _clear_modal_query_params(student_id)
                st.rerun()

    _dlg()


def generate_printable_report_html(student_id: int) -> tuple[str, bytes]:
    st_info = get_student(student_id)
    if not st_info:
        raise ValueError("Student not found")

    sid, name, gender, bd, jd, gid = st_info
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    date_tag = datetime.now().strftime("%Y%m%d_%H%M")

    overall = overall_progress(student_id)
    juz_ratios = progress_by_juz(student_id)
    sur_ratios, _, sur_names = progress_by_surah(student_id)
    total_pts, monthly_pts = points_summary(sid, jd)

    html = f"""<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="utf-8">
    <title>تقرير حفظ القرآن - {name}</title>
    <style>
    @page {{ size:A4; margin:1.6cm; }}
    body {{ font-family:'Tahoma','Arial',sans-serif; color:#111; }}
    h1,h2,h3{{ margin:0.2em 0; }} .muted{{ color:#666; font-size:12px; }}
    .section{{ margin-top:16px; }} .card{{ border:1px solid #ddd; border-radius:8px; padding:12px; margin-top:8px; }}
    table{{ width:100%; border-collapse:collapse; }} th,td{{ border:1px solid #eee; padding:6px 8px; font-size:12px; }}
    th{{ background:#f6f6f6; text-align:center; }} td{{ text-align:center; }}
    .progress-bar{{ width:100%; background:#f1f5f9; border-radius:5px; height:10px; }}
    .progress-bar div{{ background:#dc2626; height:10px; border-radius:5px; }}
    @media print {{ header, footer {{ display:none; }} }}
    </style></head><body>
    <h1 style="text-align:center;">تقرير متابعة حفظ القرآن</h1>
    <div class="muted" style="text-align:center;">تاريخ الإنشاء: {now}</div>

    <div class="section card"><h2>بيانات الطالب</h2>
    <div><strong>الاسم:</strong> {name} ({gender})</div>
    <div><strong>تاريخ الميلاد:</strong> {bd}</div>
    <div><strong>تاريخ الانضمام:</strong> {jd}</div>
    <div><strong>المعرّف:</strong> {sid}</div>
    </div>

    <div class="section card"><h2>ملخص التقدّم</h2>
    <div><strong>عدد الصفحات المحفوظة:</strong> {overall['total_pages_mem']} / {TOTAL_QURAN_PAGES_NOMINAL}</div>
    <div><strong>نسبة التقدّم الكلية:</strong> {int(round(overall['overall_ratio']*100))}%</div>
    <div><strong>عدد السور المكتملة:</strong> {overall['full_surahs']} / 114</div>
    <hr style="border:none;border-top:1px solid #eee;margin:10px 0;">
    <div><strong>مجموع النقاط:</strong> {total_pts}</div>
    <div><strong>نقاط هذا الشهر:</strong> {monthly_pts}</div>
    </div>

    <div class="section card"><h2>التقدّم حسب الأجزاء (30)</h2>
    <table><thead><tr><th>الجزء</th><th>النسبة</th><th>تقدّم</th></tr></thead><tbody>
    """
    for i, r in enumerate(juz_ratios):
        pct = int(round(r * 100))
        html += f"<tr><td>{i+1}</td><td>{pct}%</td><td><div class='progress-bar'><div style='width:{pct}%;'></div></div></td></tr>"

    html += """
    </tbody></table></div>
    <div class="section card"><h2>التقدّم حسب السور (114)</h2>
    <table><thead><tr><th>رقم</th><th>السورة</th><th>النسبة</th><th>تقدّم</th></tr></thead><tbody>
    """
    for i, r in enumerate(sur_ratios):
        pct = int(round(r * 100))
        html += f"<tr><td>{i+1}</td><td>{sur_names[i]}</td><td>{pct}%</td><td><div class='progress-bar'><div style='width:{pct}%;'></div></div></td></tr>"

    html += "</tbody></table></div></body></html>"

    safe_name = name.replace(" ", "_")
    filename = f"report_{safe_name}_{date_tag}.html"
    return filename, html.encode("utf-8")


# ================================
# (تكملة) الصفحة الرئيسية — إعدادات القلب + الرسم + بقية الأقسام
# ================================
def page_main():
    st.markdown(
        """
        <p style='text-align:center; color:#777; font-size:17px; font-family:"Amiri", "Scheherazade New", serif;'>
        🌿 قال رسول الله <span style='color:#006B3C;'>ﷺ</span>:
        «خيركم من تعلم القرآن وعلّمه» 🌿
        </p>
        """,
        unsafe_allow_html=True
    )

    st.subheader("❤️ الواجهة الرئيسية")
    st.markdown(
        "<style>.sticky-card{position:sticky;top:72px;}</style>", unsafe_allow_html=True)

    # تثبيت الطالب من رابط الصفحة إن وجد + تهيئة الحوارات من الرابط
    qp = st.query_params
    if qp.get("sid"):
        try:
            st.session_state["main_selected_student_id"] = int(qp.get("sid"))
        except Exception:
            pass
    _arm_dialog_from_query()

    # ========== البحث + النتائج ==========
    default_open = (not st.session_state.get("selected_student_id")
                    and not st.session_state.get("main_selected_student_id"))

    with st.expander("🔎 البحث والتصفية (مع النتائج)", expanded=default_open):
        col_name, col_birth, col_group = st.columns([2, 2, 1.6])

        with col_name:
            q_name = st.text_input("بحث بالاسم", key="q_name_main").strip()

        with col_birth:
            q_bd = st.text_input(
                "بحث بتاريخ الميلاد (YYYY-MM-DD)", key="q_bd_main").strip()

        with col_group:
            groups = get_groups()
            groups_opts = ["كل المجموعات"] + [g[1] for g in groups]
            gfilter = st.selectbox(
                "المجموعة", groups_opts, index=0, key="q_group_main")
            gid_filter = None if gfilter == "كل المجموعات" else next(
                (g[0] for g in groups if g[1] == gfilter), None)

        # 🧠 استدعاء المدرسة من الجلسة
        school_id = st.session_state.get("school_id", None)

        results = []
        if q_name or q_bd or gid_filter:
            if q_bd and not iso_date(q_bd):
                st.error("صيغة تاريخ الميلاد غير صحيحة.")
            else:
                # ✅ تمرير school_id إلى البحث
                results = search_students(
                    q_name or None, q_bd or None, gid_filter, school_id)

        st.markdown("---")
        st.markdown(f"**📋 نتائج البحث: ({len(results)})**")

        if not results:
            st.info("لم يتم العثور على طلاب يطابقون معايير البحث.")
        else:
            for sid_, name_, gender_, bd_, jd_, gid_ in results:
                icon = "👧" if gender_ == "أنثى" else "👦"
                gname = next((g[1] for g in get_groups()
                             if g[0] == gid_), "بدون مجموعة")
                if st.button(f"اختيار: {icon} {name_} | {bd_} | مجموعة: {gname}", key=f"main_pick_{sid_}"):
                    st.session_state["selected_student_id"] = sid_
                    st.session_state["main_selected_student_id"] = sid_
                    st.query_params.update({"page": "main", "sid": str(sid_)})
                    st.rerun()

    # ========== الطالب المختار ==========
    selected_student_id = (
        st.session_state.get("selected_student_id")
        or st.session_state.get("main_selected_student_id")
    )
    if not selected_student_id:
        st.info("اختر طالبًا لعرض التقدّم والقلب التفاعلي.")
        return

    s = get_student(selected_student_id)
    if not s:
        st.error("الطالب غير موجود.")
        return

    sid, name, gender, bd, jd, gid = s

    # بطاقة الاسم + بيانات أسفلها
    st.markdown(
        """
        <style>
          .student-name{ text-align:center; font-size:44px; font-weight:900; margin:6px 0 2px 0; letter-spacing:.3px; }
          .student-meta{ text-align:center; color:#475569; font-size:14px; margin-bottom:12px; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    icon = "👧" if gender == "أنثى" else "👦"
    gname = next((g[1] for g in get_groups() if g[0] == gid), "بدون مجموعة")
    st.markdown(
        f"<div class='student-name'>{icon} {name}</div>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='student-meta'>الجنس: {gender} — تاريخ الميلاد: {bd} — الانضمام: {jd} — المجموعة: {gname}</div>",
        unsafe_allow_html=True,
    )

    # ملخّص النقاط والتقدّم
    overall = overall_progress(sid)
    total_pts, monthly_pts = points_summary(sid, jd)

    st.markdown(
        """
        <style>
          div[data-testid="stMetric"] { text-align:center; direction: rtl; }
          div[data-testid="stMetric"] [data-testid="stMetricLabel"]{
            display:flex; justify-content:center; gap:.4rem;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )
    cA, cB = st.columns(2)
    with cA:
        st.metric("🏅 مجموع النقاط", total_pts)
    with cB:
        st.metric("🗓️ نقاط هذا الشهر", monthly_pts)

    st.progress(
        min(1.0, overall["overall_ratio"]),
        text=f"إجمالي التقدّم: {percent(overall['overall_ratio'])} ({overall['total_pages_mem']}/{TOTAL_QURAN_PAGES_NOMINAL} صفحة)",
    )

    # ❤️ عرض القلب وبقية التفاصيل
    st.markdown("---")
    st.caption(
        "يمكنك الآن استعراض الحفظ عبر القلب التفاعلي أو إضافة أهداف ومكافآت من الأسفل.")

    # ---------- إعدادات عرض القلب ----------
    with st.expander("❤️ القلب التفاعلي (الإعدادات + الرسم)", expanded=False):
        left, right = st.columns([3, 2])

        with left:
            MODES = ["حسب السور (114)", "حسب الأجزاء (30)",
                     "جزء معيّن (صفحات)", "سورة معيّنة (آيات)"]
            default_mode = st.session_state.get("ui_view_mode", MODES[0])
            mode = st.radio(
                "طريقة العرض:",
                MODES,
                horizontal=True,
                index=MODES.index(default_mode),
                key="ui_view_mode",
            )

            prev_mode = st.session_state.get("ui_prev_mode", default_mode)
            if mode != prev_mode:
                for k in ("ui_juz_one", "ui_surah_one_idx"):
                    if k in st.session_state:
                        del st.session_state[k]
                st.session_state["ui_prev_mode"] = mode

            if mode == "جزء معيّن (صفحات)":
                default_juz = st.session_state.get("ui_juz_one", 1)
                st.selectbox("اختر الجزء", list(range(1, 31)),
                             index=default_juz - 1, key="ui_juz_one")

            elif mode == "سورة معيّنة (آيات)":
                sur_refs = get_surah_refs()

                def _fmt(idx):
                    sid_, name_, ac_, *_ = sur_refs[idx]
                    return f"{sid_:03d} — {name_} ({ac_} آية)"

                default_sur_idx = st.session_state.get("ui_surah_one_idx", 0)
                st.selectbox(
                    "اختر السورة",
                    list(range(len(sur_refs))),
                    index=default_sur_idx,
                    format_func=_fmt,
                    key="ui_surah_one_idx",
                )

            if st.button("🔄 مزامنة الحفظ", key=f"ui_sync_{sid}"):
                pages_added, surahs_added = sync_bidirectional(
                    sid, max_passes=5)
                st.success(
                    f"تمت المزامنة للطالب #{sid}: صفحات مُضافة/محدَّثة = {pages_added}، سور مُضافة/محدَّثة = {surahs_added}"
                )
                st.query_params.update({"page": "main", "sid": str(sid)})
                st.rerun()

        with right:
            st.markdown(
                "<div style='text-align:right;'>**التكبير**</div>", unsafe_allow_html=True)
            zoom = st.slider(
                "التكبير",
                0.7,
                1.6,
                st.session_state.get("ui_zoom", 1.2),
                0.05,
                format="%.2f",
                label_visibility="collapsed",
                key="ui_zoom",
            )

            c1, c2 = st.columns(2)
            with c1:
                lp = st.selectbox("موضع التسميات", [
                                  "خارج القلب", "مخفية"], index=0, key="ui_label_pos")
            with c2:
                ld = st.selectbox("كثافة التسميات", [
                                  "منخفض", "متوسط", "عالٍ", "كامل"], index=1, key="ui_label_density")

        label_position = "outside" if st.session_state.get(
            "ui_label_pos", "خارج القلب") == "خارج القلب" else "hidden"
        label_density = {"منخفض": "low", "متوسط": "medium", "عالٍ": "high", "كامل": "full"}[
            st.session_state.get("ui_label_density", "متوسط")
        ]

        # CSS لوضع القلب خلف عناصر التحكم
        top_shift = -220 - int(60 * (zoom - 1.0))
        st.markdown(
            f"""
            <style>
              [data-testid="stRadio"],
              [data-testid="stSelectbox"],
              [data-testid="stSlider"],
              button, [data-testid="stButton"] {{
                position: relative !important; z-index: 20 !important;
              }}
              .heart-wrap {{
                position: relative !important; z-index: 0 !important;
                margin-top: {top_shift}px !important; pointer-events: none;
              }}
              .heart-wrap .hit, .heart-wrap a, .heart-wrap text {{
                pointer-events: auto;
              }}
            </style>
            """,
            unsafe_allow_html=True,
        )

        # ---------- رسم القلب حسب الوضع ----------
        # جلب الأهداف النشطة للطالب
        from core.models import get_active_goals_map
        active_goals = get_active_goals_map(sid)

        if mode == "حسب السور (114)":
            ratios, weights, names = progress_by_surah(sid)
            merged_ayahs = get_merged_ayahs_for_student(sid)
            segs = []
            for i in range(114):
                surah_no = i + 1
                ranges = merged_ayahs.get(surah_no, [])
                if ranges:
                    ranges_txt = "؛ ".join(f"{a}–{b}" for a, b in ranges)
                    mem_ayahs = sum(b - a + 1 for a, b in ranges)
                    ayat_part = f"الآيات المحفوظة: {ranges_txt} (المجموع {mem_ayahs})"
                else:
                    ayat_part = "الآيات المحفوظة: لا يوجد"

                # فحص إذا كانت السورة جزء من هدف نشط
                has_goal = surah_no in active_goals["surahs"]
                goal_marker = " 🎯" if has_goal else ""

                title = f"{names[i]} (السورة رقم {surah_no}) — {ayat_part} — إنجاز: {percent(ratios[i])}{goal_marker}"
                segs.append(
                    {"id": surah_no, "sid": surah_no, "label": surah_no, "title": title,
                     "ratio": float(ratios[i]), "weight": float(max(1, weights[i])), "has_goal": has_goal}
                )
            svg = make_heart_svg(segs, scale=zoom, mode="surah", sid=sid,
                                 label_position=label_position, label_density=label_density)
            st.markdown(svg, unsafe_allow_html=True)

        elif mode == "حسب الأجزاء (30)":
            ratios = progress_by_juz(sid)
            refs = get_juz_refs()
            pages_map = get_pages_for_student(sid)

            def _merge_seq(nums: List[int]) -> List[Tuple[int, int]]:
                if not nums:
                    return []
                nums = sorted(set(nums))
                s = e = nums[0]
                out = []
                for x in nums[1:]:
                    if x == e + 1:
                        e = x
                    else:
                        out.append((s, e))
                        s = e = x
                out.append((s, e))
                return out

            def page_ranges_str(pages: List[int]) -> str:
                if not pages:
                    return "لم يبدأ بعد"
                rng = _merge_seq(pages)
                parts = [f"{a}" if a == b else f"{a}–{b}" for a, b in rng]
                return "؛ ".join(parts) + f" (المجموع: {len(pages)})"

            segs = []
            for i in range(30):
                jnum, sp, ep = refs[i]
                saved_pages = [p for p, v in pages_map.items()
                               if v == 1 and sp <= p <= ep]
                saved_range = page_ranges_str(saved_pages)

                # فحص إذا كان أي صفحة في الجزء جزء من هدف نشط
                has_goal = any(p in active_goals["pages"] for p in range(sp, ep + 1))
                goal_marker = " 🎯" if has_goal else ""

                title = f"الجزء {jnum} — الصفحات {sp}–{ep} — الصفحات المحفوظة: {saved_range} — إنجاز: {percent(ratios[i])}{goal_marker}"
                segs.append({"id": jnum, "label": jnum, "title": title,
                            "ratio": float(ratios[i]), "weight": 1.0, "has_goal": has_goal})

            svg = make_heart_svg(segs, scale=zoom, mode="juz", sid=sid,
                                 label_position=label_position, label_density=label_density)
            st.markdown(svg, unsafe_allow_html=True)

        elif mode == "جزء معيّن (صفحات)":
            refs = get_juz_refs()
            jnum = st.session_state.get("ui_juz_one", 1)
            sp, ep = next((sp, ep) for (j, sp, ep) in refs if j == jnum)
            pages_map = get_pages_for_student(sid)

            segs = []
            rel = 0
            for p in range(sp, ep + 1):
                rel += 1
                is_mem = 1.0 if pages_map.get(p) == 1 else 0.0
                has_goal = p in active_goals["pages"]
                goal_marker = " 🎯" if has_goal else ""
                title = f"الجزء {jnum} — الصفحة {p}{goal_marker}"
                segs.append({"id": jnum, "label": rel,
                            "title": title, "ratio": is_mem, "weight": 1.0, "has_goal": has_goal})

            svg = make_heart_svg(segs, scale=zoom, mode="juz", sid=sid,
                                 label_position=label_position, label_density=label_density)
            st.markdown(svg, unsafe_allow_html=True)

        elif mode == "سورة معيّنة (آيات)":
            sur_refs = get_surah_refs()
            sur_idx = st.session_state.get("ui_surah_one_idx", 0)
            surah_no, sname, ayah_cnt, *_ = sur_refs[sur_idx]

            merged = get_merged_ayahs_for_student(sid)
            mem_set = set()
            for a, b in merged.get(surah_no, []):
                mem_set.update(range(a, b + 1))

            # فحص إذا كانت السورة جزء من هدف نشط
            has_goal = surah_no in active_goals["surahs"]

            segs = []
            for a in range(1, ayah_cnt + 1):
                goal_marker = " 🎯" if has_goal else ""
                segs.append(
                    {"id": surah_no, "sid": a, "title": f"{sname} — آية {a}{goal_marker}",
                     "ratio": 1.0 if a in mem_set else 0.0, "weight": 1.0, "has_goal": has_goal}
                )

            svg = make_heart_svg(segs, scale=zoom, mode="surah", sid=sid,
                                 label_position=label_position, label_density=label_density)
            st.markdown(svg, unsafe_allow_html=True)
        else:
            st.info("اختر وضع العرض المطلوب.")

    # ---------- فتح الحوارات الناتجة عن النقر ----------
    if st.session_state.get("show_dialog", False):
        dlg = st.session_state.get("dialog_mode")
        seg = st.session_state.get("dialog_seg")

        # مسح علم الحوار لتجنب فتحه مرة أخرى
        st.session_state["show_dialog"] = False

        # مسح معاملات الرابط لتنظيف الرابط
        st.query_params.clear()
        st.query_params.update({"page": "main", "sid": str(sid)})

        # فتح الحوار المناسب
        if dlg == "surah":
            open_surah_dialog(sid, seg)
        else:
            open_juz_dialog(sid, seg)

    # ---------- الأهداف ----------
    with st.expander("🎯 أهداف الطالب"):
        st.markdown("### ➕ إضافة هدف")
        colX1, colX2, colX3 = st.columns(3)
        with colX1:
            from core.models import AR_CATEGORY, AR_PERIODICITY, AR_TARGET_KIND, _to_code_target_kind, _to_code_periodicity
            ar_category = st.selectbox("تصنيف الهدف", list(
                AR_CATEGORY.values()), index=0, key=f"g_ar_category_{sid}")
            ar_period = st.selectbox("دورية الهدف", list(
                AR_PERIODICITY.values()), index=0, key=f"g_ar_period_{sid}")
        with colX2:
            ar_kind = st.selectbox("نوع الهدف", list(
                AR_TARGET_KIND.values()), index=0, key=f"g_ar_kind_{sid}")
            per_qty = st.number_input(
                "كمية الجلسة الواحدة (للتكراري)", min_value=0, step=1, value=0, key=f"g_perqty_{sid}")
        with colX3:
            note_txt = st.text_input("ملاحظة (اختياري)", key=f"g_note_{sid}")

        code_kind = _to_code_target_kind(ar_kind)
        code_period = _to_code_periodicity(ar_period)

        # حقول الهدف حسب نوعه
        if code_period == "once":
            if code_kind == "pages":
                p_from = st.number_input(
                    "من الصفحة", min_value=1, max_value=TOTAL_QURAN_PAGES_NOMINAL, step=1, value=1, key=f"g_once_p_from_{sid}")
                p_to = st.number_input(
                    "إلى الصفحة", min_value=1, max_value=TOTAL_QURAN_PAGES_NOMINAL, step=1, value=1, key=f"g_once_p_to_{sid}")
                surah_id = from_ayah = to_ayah = None
            else:
                surah_refs = get_surah_refs()

                def _fmt_surah(i: int) -> str:
                    sid_, name_, ac_, *_ = surah_refs[i]
                    return f"{sid_:03d} — {name_} ({ac_} آية)"
                sel_idx = st.selectbox("السورة", list(
                    range(len(surah_refs))), format_func=_fmt_surah, key=f"g_once_surah_idx_{sid}")
                sel_sid, _, sel_ac, *_ = surah_refs[sel_idx]
                surah_id = sel_sid
                from_ayah = st.number_input("من الآية", min_value=1, max_value=int(
                    sel_ac), step=1, value=1, key=f"g_once_a_from_{sid}")
                to_ayah = st.number_input("إلى الآية", min_value=1, max_value=int(
                    sel_ac), step=1, value=1, key=f"g_once_a_to_{sid}")
                p_from = p_to = None

            due_date = st.date_input(
                "تاريخ الإنجاز", value=date.today(), key=f"g_once_due_{sid}").isoformat()
            start_date = date.today().isoformat()
            end_date = None

        else:
            start_date = st.date_input(
                "تاريخ البداية", value=date.today(), key=f"g_rec_start_{sid}").isoformat()
            end_date = st.date_input("تاريخ النهاية", value=date.today(
            ) + timedelta(days=30), key=f"g_rec_end_{sid}").isoformat()
            due_date = None
            if code_kind == "pages":
                p_from = st.number_input("بداية القسم (صفحة)", min_value=1,
                                         max_value=TOTAL_QURAN_PAGES_NOMINAL, step=1, value=1, key=f"g_rec_p_from_{sid}")
                p_to = st.number_input("نهاية القسم (صفحة)", min_value=1,
                                       max_value=TOTAL_QURAN_PAGES_NOMINAL, step=1, value=20, key=f"g_rec_p_to_{sid}")
                surah_id = from_ayah = to_ayah = None
            else:
                surah_refs = get_surah_refs()

                def _fmt_surah(i: int) -> str:
                    sid_, name_, ac_, *_ = surah_refs[i]
                    return f"{sid_:03d} — {name_} ({ac_} آية)"
                sel_idx = st.selectbox("السورة (لنطاق التكرار)", list(
                    range(len(surah_refs))), format_func=_fmt_surah, key=f"g_rec_surah_idx_{sid}")
                sel_sid, _, sel_ac, *_ = surah_refs[sel_idx]
                surah_id = sel_sid
                from_ayah = st.number_input("من الآية (بداية القسم)", min_value=1, max_value=int(
                    sel_ac), step=1, value=1, key=f"g_rec_a_from_{sid}")
                to_ayah = st.number_input("إلى الآية (نهاية القسم)", min_value=1, max_value=int(
                    sel_ac), step=1, value=min(20, int(sel_ac)), key=f"g_rec_a_to_{sid}")
                p_from = p_to = None

        if st.button("حفظ الهدف", key=f"g_save_btn_{sid}"):
            try:
                with closing(get_conn()) as conn:
                    c = conn.cursor()
                    c.execute(
                        """
                        INSERT INTO goals(
                            student_id, category, periodicity, target_kind,
                            page_from, page_to, surah_id, from_ayah, to_ayah,
                            per_session_qty, start_date, due_date, end_date,
                            status, note, goal_type, target, period
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            sid,
                            # نعيد استخدام المحولات العربية من models
                            __import__("core.models").models._to_code_category(
                                ar_category),
                            code_period,
                            code_kind,
                            int(p_from) if p_from else None,
                            int(p_to) if p_to else None,
                            int(surah_id) if surah_id else None,
                            int(from_ayah) if from_ayah else None,
                            int(to_ayah) if to_ayah else None,
                            int(per_qty or 0),
                            start_date,
                            due_date,
                            end_date,
                            "pending",
                            (note_txt or "").strip(),
                            ("pages" if code_kind == "pages" else "surah"),
                            (
                                (int(p_to or 0) - int(p_from or 0) + 1)
                                if code_kind == "pages" and p_from and p_to
                                else (
                                    int(to_ayah or 0) - int(from_ayah or 0) + 1
                                    if code_kind == "ayahs" and from_ayah and to_ayah
                                    else 0
                                )
                            ),
                            ("weekly" if code_period == "weekly" else "monthly"),
                        ),
                    )
                    conn.commit()
                st.success("✅ تمت إضافة الهدف بنجاح.")
                st.rerun()
            except Exception as e:
                st.error(f"تعذّر حفظ الهدف: {e}")

        # جدول الأهداف الحالية
        st.markdown("---")
        st.markdown("### 📋 جدول الأهداف الحالية")
        with closing(get_conn()) as conn:
            c = conn.cursor()
            c.execute(
                """
                SELECT id, category, periodicity, target_kind,
                       COALESCE(page_from,''), COALESCE(page_to,''),
                       COALESCE(surah_id,''), COALESCE(from_ayah,''), COALESCE(to_ayah,''),
                       COALESCE(per_session_qty,0),
                       COALESCE(start_date,''), COALESCE(due_date,''), COALESCE(end_date,''),
                       status, COALESCE(achieved_at,''), COALESCE(note,'')
                FROM goals
                WHERE student_id=?
                ORDER BY id DESC
                """,
                (sid,),
            )
            rows = c.fetchall()

        from core.models import AR_CATEGORY, AR_PERIODICITY, AR_TARGET_KIND, _goal_status_to_ar, _goal_status_from_ar
        view = []
        for (
            gid, cat, per, kind, pf, pt, su, fa, ta, perqty,
            sdt, due, edt, stat, ach, note,
        ) in rows:
            view.append(
                {
                    "ID": gid,
                    "التصنيف": AR_CATEGORY.get(cat, cat),
                    "الدورية": AR_PERIODICITY.get(per, per),
                    "النوع": AR_TARGET_KIND.get(kind, kind),
                    "من صفحة": pf,
                    "إلى صفحة": pt,
                    "سورة": su,
                    "من آية": fa,
                    "إلى آية": ta,
                    "كمية/جلسة": perqty,
                    "بداية": sdt,
                    "الإنجاز": due,
                    "نهاية": edt,
                    "الحالة": _goal_status_to_ar(stat),
                    "تم عند": ach,
                    "ملاحظة": note,
                }
            )

        dfG = pd.DataFrame(view)
        if not dfG.empty:
            # زر الفحص التلقائي للأهداف
            col_check, col_spacer = st.columns([1, 3])
            with col_check:
                if st.button("🔍 فحص الأهداف تلقائيًا", key=f"auto_check_goals_{sid}"):
                    from core.models import auto_check_goals
                    updated = auto_check_goals(sid)
                    if updated > 0:
                        st.success(f"✅ تم إنجاز {updated} هدف!")
                        st.rerun()
                    else:
                        st.info("لا توجد أهداف جديدة مكتملة.")

            edited = st.data_editor(
                dfG,
                use_container_width=True,
                num_rows="fixed",
                column_config={
                    "الحالة": st.column_config.SelectboxColumn(
                        options=["ليس بعد", "تم", "لم ينجز"]
                    )
                },
                disabled=[c for c in dfG.columns if c not in (
                    "الحالة", "ملاحظة")],
                key=f"goals_editor_{sid}",
            )

            if st.button("💾 حفظ حالة الأهداف", key=f"g_save_status_btn_{sid}"):
                try:
                    with closing(get_conn()) as conn:
                        c = conn.cursor()
                        for _, row in edited.iterrows():
                            gid = int(row["ID"])
                            new_status = _goal_status_from_ar(row["الحالة"])
                            note = (row.get("ملاحظة", "") or "").strip()
                            ach = (
                                datetime.now().isoformat(timespec="seconds")
                                if new_status == "done"
                                else None
                            )
                            c.execute(
                                """
                                UPDATE goals SET status=?, achieved_at=?, note=?
                                WHERE id=?
                                """,
                                (new_status, ach, note, gid),
                            )
                        conn.commit()
                    st.success("✅ تم حفظ الحالات.")
                    st.rerun()
                except Exception as e:
                    st.error(f"تعذّر الحفظ: {e}")
        else:
            st.caption("لا توجد أهداف بعد.")

    # ---------- المكافآت ----------
    with st.expander("🏅 المكافآت"):
        st.markdown("**سجل المكافآت للطالب/الطالبة**")
        with closing(get_conn()) as conn:
            c = conn.cursor()
            c.execute(
                "SELECT id, points, badge, note, created_at FROM rewards WHERE student_id=? ORDER BY id DESC",
                (sid,),
            )
            dfR = pd.DataFrame(
                c.fetchall(), columns=["ID", "النقاط", "الوسام", "ملاحظة", "التاريخ"]
            )
        st.dataframe(dfR, use_container_width=True, height=220)

        with st.form(f"main_reward_add_{sid}", clear_on_submit=True):
            pts = st.number_input(
                "نقاط", min_value=0, step=1, value=10, key=f"main_reward_points_{sid}")
            badge = st.text_input("اسم الوسام (اختياري)",
                                  value="مثابر", key=f"main_reward_badge_{sid}")
            note = st.text_input("ملاحظة", value="",
                                 key=f"main_reward_note_{sid}")
            if st.form_submit_button("منح مكافأة"):
                with closing(get_conn()) as conn:
                    c = conn.cursor()
                    c.execute(
                        "INSERT INTO rewards(student_id, points, badge, note) VALUES(?,?,?,?)",
                        (sid, int(pts), badge.strip(), note.strip()),
                    )
                    conn.commit()
                st.success("✅ تم منح المكافأة.")
                st.rerun()

    # ---------- التقرير المطبوع ----------
    if st.session_state.get("main_report_student") != sid:
        st.session_state["main_report_bytes"] = None
        st.session_state["main_report_fname"] = None
        st.session_state["main_report_student"] = sid

    with st.expander("🧾 تقرير مطبوع", expanded=False):
        if st.button("توليد تقرير مطبوع للطالب/الطالبة", key=f"main_report_btn_{sid}"):
            try:
                fname, html_bytes = generate_printable_report_html(sid)
                st.session_state["main_report_bytes"] = html_bytes
                st.session_state["main_report_fname"] = fname
                st.success("تم توليد التقرير بنجاح.")
            except Exception as e:
                st.error(f"تعذّر توليد التقرير: {e}")

        rb = st.session_state.get("main_report_bytes")
        rf = st.session_state.get("main_report_fname")
        if rb and rf:
            st.download_button(
                "⬇️ تنزيل التقرير",
                data=rb,
                file_name=rf,
                mime="text/html",
                key=f"main_report_download_{sid}",
            )
            st.components.v1.html(rb.decode("utf-8"),
                                  height=420, scrolling=True)
        else:
            st.caption("لم يتم توليد التقرير بعد.")

# =============================
# صفحة الطلاب (منسقة + اسم المدرسة)
# =============================


def page_students():
    st.markdown(
        """
        <p style='text-align:center; color:#777; font-size:17px; font-family:"Amiri", "Scheherazade New", serif;'>
        🌿 قال رسول الله <span style='color:#006B3C;'>ﷺ</span>:
        «خيركم من تعلم القرآن وعلّمه» 🌿
        </p>
        """,
        unsafe_allow_html=True
    )
    st.subheader("👦👧 الطلاب")

    # ------------------------------------------------------
    # 🔹 تحديد الصلاحية والمدرسة
    # ------------------------------------------------------
    role = st.session_state.get("user_role", "guest")
    school_id = st.session_state.get("school_id", None)
    teacher_id = st.session_state.get("user_rel_id", None)

    # ------------------------------------------------------
    # 📋 جدول الطلاب
    # ------------------------------------------------------
    with st.expander("📋 جدول الطلاب", expanded=True):
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            q_name = st.text_input(
                "🔎 بحث بالاسم", key="stud_filter_name").strip()
        with col2:
            # === جلب المجموعات حسب الصلاحية ===
            with closing(get_conn()) as conn:
                c = conn.cursor()
                if role == "super_admin":
                    c.execute(
                        "SELECT id, name FROM groups ORDER BY name COLLATE NOCASE")
                elif role == "school_admin":
                    c.execute(
                        "SELECT id, name FROM groups WHERE school_id=? ORDER BY name COLLATE NOCASE", (school_id,))
                elif role == "teacher":
                    c.execute(
                        "SELECT id, name FROM groups WHERE school_id=? AND teacher_id=? ORDER BY name COLLATE NOCASE", (school_id, teacher_id))
                else:
                    c.execute(
                        "SELECT id, name FROM groups WHERE school_id=? ORDER BY name COLLATE NOCASE", (school_id,))
                groups = c.fetchall()

            group_opts = ["الكل"] + [g[1] for g in groups]
            g_filter = st.selectbox(
                "المجموعة", group_opts, index=0, key="stud_filter_group")

        with col3:
            gender_filter = st.selectbox(
                "الجنس", ["الكل", "ذكر", "أنثى"], index=0, key="stud_filter_gender")

        # === جلب بيانات الطلاب مع اسم المدرسة ===
        with closing(get_conn()) as conn:
            c = conn.cursor()
            base_query = """
                SELECT s.id, s.full_name, IFNULL(g.name,'بدون مجموعة') AS gname,
                       s.gender, s.birth_date, COALESCE(s.phone,''), COALESCE(s.email,''),
                       COALESCE(s.guardian_name,''), COALESCE(sc.name,'') AS school_name
                FROM students s
                LEFT JOIN groups g ON g.id = s.group_id
                LEFT JOIN schools sc ON s.school_id = sc.id
                WHERE 1=1
            """
            params = []

            # فلترة حسب الصلاحية
            if role == "school_admin":
                base_query += " AND s.school_id=?"
                params.append(school_id)
            elif role == "teacher":
                base_query += " AND s.school_id=? AND g.teacher_id=?"
                params.extend([school_id, teacher_id])
            elif role not in ("super_admin", "school_admin", "teacher"):
                base_query += " AND s.school_id=?"
                params.append(school_id)

            # فلترة حسب المجموعة (اختيار المستخدم)
            if g_filter != "الكل":
                base_query += " AND IFNULL(g.name,'بدون مجموعة') = ?"
                params.append(g_filter)

            base_query += " ORDER BY s.full_name COLLATE NOCASE"
            c.execute(base_query, params)
            rows = c.fetchall()

        # تجهيز الجدول
        records = []
        for sid, fullname, gname, gender, bd, phone, email, guardian, sname in rows:
            age = calc_age(bd)
            records.append((sid, fullname, gname, gender, age,
                           phone, email, guardian, sname))

        df = pd.DataFrame(records, columns=[
            "ID", "الاسم", "المجموعة", "الجنس", "العمر", "الهاتف", "الإيميل", "وليّ الأمر", "المدرسة"
        ])

        # تطبيق الفلاتر
        if q_name:
            df = df[df["الاسم"].str.contains(q_name, case=False, na=False)]
        if g_filter != "الكل":
            df = df[df["المجموعة"] == g_filter]
        if gender_filter != "الكل":
            df = df[df["الجنس"] == gender_filter]

        # عرض الجدول القابل للتحرير
        g_opts = ["بدون مجموعة"] + [g[1] for g in groups]
        edited = st.data_editor(
            df,
            use_container_width=True,
            num_rows="fixed",
            column_config={
                "المجموعة": st.column_config.SelectboxColumn(options=g_opts),
                "الجنس": st.column_config.SelectboxColumn(options=["ذكر", "أنثى"]),
            },
            disabled=["ID", "العمر", "المدرسة"],
            key="stud_editor",
        )

        # حفظ التعديلات
        if st.button("💾 حفظ التعديلات", type="primary", key="stud_save_btn"):
            gmap = {g[1]: g[0] for g in groups}
            with closing(get_conn()) as conn:
                c = conn.cursor()
                for _, row in edited.iterrows():
                    sid = int(row["ID"])
                    full_name = row["الاسم"].strip()
                    gender = row["الجنس"]
                    gname = row["المجموعة"]
                    gid = None if gname in (
                        "بدون مجموعة", "") else gmap.get(gname)
                    phone = (row["الهاتف"] or "").strip()
                    email = (row["الإيميل"] or "").strip()
                    guardian = (row["وليّ الأمر"] or "").strip()
                    c.execute("""
                        UPDATE students
                        SET full_name=?, gender=?, group_id=?, phone=?, email=?, guardian_name=?
                        WHERE id=?
                    """, (full_name, gender, gid, phone, email, guardian, sid))
                conn.commit()
            st.success("✅ تم حفظ التعديلات بنجاح.")
            st.rerun()

    # ------------------------------------------------------
    # ➕ إضافة طالب / طالبة
    # ------------------------------------------------------
    with st.expander("➕ إضافة طالب/طالبة", expanded=False):
        school_name = get_school_name(school_id) if school_id else "—"

        with st.form("stud_add_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("الاسم (إجباري)", key="stud_add_name")
                gender = st.radio(
                    "الجنس", ["ذكر", "أنثى"], horizontal=True, key="stud_add_gender")
                bd = st.date_input("تاريخ الميلاد", value=date(
                    2015, 1, 1), key="stud_add_birth")
                jd = st.date_input(
                    "تاريخ الانضمام", value=date.today(), key="stud_add_join")
            with col2:
                phone = st.text_input("رقم الهاتف", key="stud_add_phone")
                email = st.text_input("الإيميل", key="stud_add_email")
                guardian = st.text_input(
                    "اسم وليّ الأمر", key="stud_add_guardian")
                gsel = st.selectbox("المجموعة", [
                                    "(بدون مجموعة)"] + [g[1] for g in groups], index=0, key="stud_add_group")
                st.text_input("المدرسة", school_name,
                              disabled=True, key="stud_add_school")

            if st.form_submit_button("حفظ الطالب/الطالبة", type="primary", key="stud_add_btn"):
                if not name.strip():
                    st.error("⚠️ الاسم إجباري.")
                else:
                    gid = None if gsel == "(بدون مجموعة)" else [
                        g[0] for g in groups if g[1] == gsel][0]
                    sid = add_student(name, gender, bd.isoformat(), jd.isoformat(), gid,
                                      phone=phone, email=email, guardian_name=guardian)
                    # تحديث عمود المدرسة بعد الإضافة
                    with closing(get_conn()) as conn:
                        c = conn.cursor()
                        c.execute(
                            "UPDATE students SET school_id=? WHERE id=?", (school_id, sid))
                        conn.commit()
                    st.success(
                        f"✅ تمت إضافة الطالب/الطالبة #{sid} في مدرسة {school_name}.")
                    st.rerun()

    # ------------------------------------------------------
    # 🗑️ حذف طالب
    # ------------------------------------------------------
    with st.expander("🗑️ حذف طالب", expanded=False):
        if df.empty:
            st.info("لا توجد بيانات حالياً.")
        else:
            opt_map = {f"{r['الاسم']} (ID:{r['ID']})": int(
                r["ID"]) for _, r in df.iterrows()}
            pick = st.selectbox("اختر طالبًا", list(
                opt_map.keys()), key="stud_delete_select")
            sid = opt_map[pick]
            if st.button("🗑️ حذف الطالب", type="secondary", key=f"stud_delete_btn_{sid}"):
                @st.dialog("تأكيد حذف الطالب")
                def _confirm_delete():
                    st.error("⚠️ هل أنت متأكد من حذف هذا الطالب نهائيًا؟")
                    c1, c2 = st.columns(2)
                    if c1.button("نعم، حذف نهائي", type="primary", key=f"stud_yes_{sid}"):
                        delete_student(sid)
                        st.success("✅ تم حذف الطالب.")
                        st.rerun()
                    if c2.button("إلغاء", key=f"stud_no_{sid}"):
                        st.rerun()
                _confirm_delete()


# ================================
# صفحة المعلمين
# ================================
# =============================
# 👨‍🏫 صفحة المعلمين (Teachers)
# =============================


def page_teachers():
    st.markdown(
        """
        <p style='text-align:center; color:#777; font-size:17px; font-family:"Amiri", "Scheherazade New", serif;'>
        🌿 قال رسول الله <span style='color:#006B3C;'>ﷺ</span>:
        «خيركم من تعلم القرآن وعلّمه» 🌿
        </p>
        """,
        unsafe_allow_html=True
    )
    st.subheader("👨‍🏫 المعلمون")

    role = st.session_state.get("user_role", "")
    school_id = st.session_state.get("school_id", None)

    # 🔒 صلاحيات الوصول
    if role not in ["super_admin", "school_admin"]:
        st.error("🚫 لا تملك صلاحية الوصول إلى صفحة المعلمين.")
        return

    # --------------------------------------------------------
    # 🔹 جدول المعلمين
    # --------------------------------------------------------
    with st.expander("📋 جدول المعلمين", expanded=True):
        st.text_input("🔍 بحث باسم المعلم", key="teacher_search",
                      placeholder="اكتب جزءًا من الاسم...")

        with closing(get_conn()) as conn:
            c = conn.cursor()

            # إذا كان سوبر أدمن يرى كل المعلمين
            if role == "super_admin":
                c.execute("""
                    SELECT t.id, t.name, t.gender, COALESCE(t.birth_date,''), COALESCE(t.phone,''), 
                           COALESCE(t.email,''), COALESCE(t.memorization_note,''), COALESCE(t.is_mujaz,0),
                           COALESCE(t.password,''), COALESCE(s.name, '')
                    FROM teachers t
                    LEFT JOIN schools s ON s.id = t.school_id
                    ORDER BY t.name COLLATE NOCASE
                """)
            else:
                # أما أدمن المدرسة فيرى فقط معلمي مدرسته
                c.execute("""
                    SELECT t.id, t.name, t.gender, COALESCE(t.birth_date,''), COALESCE(t.phone,''), 
                           COALESCE(t.email,''), COALESCE(t.memorization_note,''), COALESCE(t.is_mujaz,0),
                           COALESCE(t.password,''), COALESCE(s.name, '')
                    FROM teachers t
                    LEFT JOIN schools s ON s.id = t.school_id
                    WHERE t.school_id=?
                    ORDER BY t.name COLLATE NOCASE
                """, (school_id,))
            rows = c.fetchall()

        df = pd.DataFrame(rows, columns=[
            "ID", "الاسم", "الجنس", "تاريخ الميلاد", "الهاتف", "الإيميل",
            "ملاحظة الحفظ", "مجاز؟", "كلمة السر", "المدرسة"
        ])

        edited = st.data_editor(
            df,
            use_container_width=True,
            num_rows="fixed",
            key="teachers_editor"
        )

        if st.button("💾 حفظ التعديلات", type="primary", key="teachers_save"):
            with closing(get_conn()) as conn:
                c = conn.cursor()
                for _, r in edited.iterrows():
                    c.execute("""
                        UPDATE teachers
                        SET name=?, gender=?, birth_date=?, phone=?, email=?, 
                            memorization_note=?, is_mujaz=?, password=?
                        WHERE id=?
                    """, (
                        r["الاسم"], r["الجنس"], r["تاريخ الميلاد"], r["الهاتف"], r["الإيميل"],
                        r["ملاحظة الحفظ"], r["مجاز؟"], r["كلمة السر"], int(
                            r["ID"])
                    ))
                conn.commit()
            st.success("✅ تم حفظ جميع التعديلات بنجاح.")
            st.rerun()

    # --------------------------------------------------------
    # ➕ إضافة معلم جديد
    # --------------------------------------------------------
    with st.expander("➕ إضافة معلم", expanded=False):
        with closing(get_conn()) as conn:
            c = conn.cursor()
            c.execute("SELECT id, name FROM schools ORDER BY name COLLATE NOCASE")
            schools = c.fetchall()

        with st.form("add_teacher_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input(
                    "👤 اسم المعلم (إجباري)", key="add_teacher_name")
                gender = st.radio(
                    "الجنس", ["ذكر", "أنثى"], horizontal=True, key="add_teacher_gender")
                birth = st.text_input(
                    "📅 تاريخ الميلاد (YYYY-MM-DD)", value="", key="add_teacher_birth")
                note = st.text_input(
                    "🧠 ملاحظة الحفظ (مثال: 30 جزء / 16 جزء / 50 سورة)", key="add_teacher_note")
                is_mujaz = st.checkbox("📜 مجاز؟", key="add_teacher_is_mujaz")
            with col2:
                password = st.text_input(
                    "🔑 كلمة السر (إجباري)", type="password", key="add_teacher_pass")
                phone = st.text_input("📞 رقم الهاتف", key="add_teacher_phone")
                email = st.text_input("✉️ الإيميل", key="add_teacher_email")

                # إذا كان سوبر أدمن فقط، يمكنه اختيار المدرسة
                school_choice = None
                if role == "super_admin":
                    school_choice = st.selectbox(
                        "🏫 اختر المدرسة", [s[1] for s in schools], key="add_teacher_school")

            submitted = st.form_submit_button("➕ إضافة معلم", type="primary")

            if submitted:
                if not name.strip() or not password.strip():
                    st.error("⚠️ يجب إدخال اسم المعلم وكلمة السر.")
                else:
                    with closing(get_conn()) as conn:
                        c = conn.cursor()
                        # المدرسة التي سيتم ربط المعلم بها
                        target_school_id = school_id
                        if role == "super_admin" and school_choice:
                            c.execute(
                                "SELECT id FROM schools WHERE name=?", (school_choice,))
                            s = c.fetchone()
                            if s:
                                target_school_id = s[0]

                        c.execute("""
                            INSERT INTO teachers(name, gender, birth_date, phone, email, 
                                memorization_note, is_mujaz, password, school_id)
                            VALUES(?,?,?,?,?,?,?,?,?)
                        """, (
                            name.strip(), gender.strip(), birth.strip(), phone.strip(),
                            email.strip(), note.strip(), 1 if is_mujaz else 0,
                            password.strip(), target_school_id
                        ))
                        conn.commit()
                    st.success(f"✅ تمت إضافة المعلم '{name}' بنجاح.")
                    st.rerun()

    # --------------------------------------------------------
    # 🗑️ حذف معلم
    # --------------------------------------------------------
    with st.expander("🗑️ حذف معلم", expanded=False):
        with closing(get_conn()) as conn:
            c = conn.cursor()
            if role == "super_admin":
                c.execute(
                    "SELECT id, name FROM teachers ORDER BY name COLLATE NOCASE")
            else:
                c.execute(
                    "SELECT id, name FROM teachers WHERE school_id=? ORDER BY name COLLATE NOCASE", (school_id,))
            teachers = c.fetchall()

        if not teachers:
            st.info("❕ لا يوجد معلمون حاليًا.")
        else:
            tmap = {f"{t[1]} (ID:{t[0]})": t[0] for t in teachers}
            selected = st.selectbox("اختر معلمًا للحذف", list(
                tmap.keys()), key="delete_teacher_select")
            tid = tmap[selected]
            if st.button("🗑️ حذف المعلم", type="primary", key=f"delete_teacher_btn_{tid}"):
                @st.dialog("تأكيد حذف المعلم")
                def _confirm_delete_teacher():
                    st.error("⚠️ هل أنت متأكد من حذف هذا المعلم وجميع بياناته؟")
                    c1, c2 = st.columns(2)
                    if c1.button("نعم، حذف نهائي", type="primary", key=f"yes_{tid}"):
                        with closing(get_conn()) as conn:
                            c = conn.cursor()
                            c.execute(
                                "DELETE FROM teachers WHERE id=?", (tid,))
                            conn.commit()
                        st.success("✅ تم حذف المعلم بنجاح.")
                        st.rerun()
                    if c2.button("إلغاء", key=f"no_{tid}"):
                        st.rerun()
                _confirm_delete_teacher()


# ================================
# صفحة المجموعات
# ================================
# =============================
# صفحة المجموعات (الفصول) — مع المدرسة والمعلم
# =============================
def page_groups():
    st.markdown(
        """
        <p style='text-align:center; color:#777; font-size:17px; font-family:"Amiri", "Scheherazade New", serif;'>
        🌿 قال رسول الله <span style='color:#006B3C;'>ﷺ</span>:
        «خيركم من تعلم القرآن وعلّمه» 🌿
        </p>
        """,
        unsafe_allow_html=True
    )
    st.subheader("👥 المجموعات (الفصول)")

    # ------------------------------------------------------
    # 🔹 تحديد صلاحية المستخدم والمدرسة
    # ------------------------------------------------------
    role = st.session_state.get("user_role", "guest")
    school_id = st.session_state.get("school_id", None)
    teacher_id = st.session_state.get("user_rel_id", None)

    # ------------------------------------------------------
    # 📋 جدول المجموعات
    # ------------------------------------------------------
    with st.expander("📋 جدول المجموعات", expanded=True):
        q_name = st.text_input("🔎 بحث باسم المجموعة",
                               key="group_filter_name").strip()

        # جلب البيانات حسب الدور
        with closing(get_conn()) as conn:
            c = conn.cursor()
            if role == "super_admin":
                c.execute("""
                    SELECT g.id, g.name, COALESCE(t.name, '—') AS teacher, 
                           COALESCE(sc.name, '') AS school_name
                    FROM groups g
                    LEFT JOIN teachers t ON g.teacher_id = t.id
                    LEFT JOIN schools sc ON g.school_id = sc.id
                    ORDER BY g.name COLLATE NOCASE
                """)
            elif role == "school_admin":
                c.execute("""
                    SELECT g.id, g.name, COALESCE(t.name, '—') AS teacher, 
                           COALESCE(sc.name, '') AS school_name
                    FROM groups g
                    LEFT JOIN teachers t ON g.teacher_id = t.id
                    LEFT JOIN schools sc ON g.school_id = sc.id
                    WHERE g.school_id=?
                    ORDER BY g.name COLLATE NOCASE
                """, (school_id,))
            elif role == "teacher":
                c.execute("""
                    SELECT g.id, g.name, COALESCE(t.name, '—') AS teacher, 
                           COALESCE(sc.name, '') AS school_name
                    FROM groups g
                    LEFT JOIN teachers t ON g.teacher_id = t.id
                    LEFT JOIN schools sc ON g.school_id = sc.id
                    WHERE g.school_id=? AND g.teacher_id=?
                    ORDER BY g.name COLLATE NOCASE
                """, (school_id, teacher_id))
            else:
                c.execute("""
                    SELECT g.id, g.name, COALESCE(t.name, '—') AS teacher, 
                           COALESCE(sc.name, '') AS school_name
                    FROM groups g
                    LEFT JOIN teachers t ON g.teacher_id = t.id
                    LEFT JOIN schools sc ON g.school_id = sc.id
                    WHERE g.school_id=?
                    ORDER BY g.name COLLATE NOCASE
                """, (school_id,))
            groups = c.fetchall()

        df = pd.DataFrame(
            groups, columns=["ID", "اسم المجموعة", "المعلم", "المدرسة"])

        if q_name:
            df = df[df["اسم المجموعة"].str.contains(
                q_name, case=False, na=False)]

        # جلب قائمة المعلمين للاستخدام في القائمة المنسدلة
        with closing(get_conn()) as conn:
            c = conn.cursor()
            if role == "super_admin":
                c.execute(
                    "SELECT id, name FROM teachers ORDER BY name COLLATE NOCASE")
            else:
                c.execute(
                    "SELECT id, name FROM teachers WHERE school_id=? ORDER BY name COLLATE NOCASE", (school_id,))
            teachers = c.fetchall()

        t_opts = ["(بدون معلم)"] + [t[1] for t in teachers]
        t_map = {t[1]: t[0] for t in teachers}

        edited = st.data_editor(
            df,
            use_container_width=True,
            num_rows="fixed",
            column_config={
                "المعلم": st.column_config.SelectboxColumn(options=t_opts)
            },
            disabled=["ID", "المدرسة"],
            key="groups_editor"
        )

        if st.button("💾 حفظ تعديلات المجموعات", type="primary", key="groups_save_btn"):
            with closing(get_conn()) as conn:
                c = conn.cursor()
                for _, r in edited.iterrows():
                    gid = int(r["ID"])
                    name = r["اسم المجموعة"].strip()
                    tname = r["المعلم"]
                    tid = None if tname == "(بدون معلم)" else t_map.get(tname)
                    c.execute(
                        "UPDATE groups SET name=?, teacher_id=? WHERE id=?", (name, tid, gid))
                conn.commit()
            st.success("✅ تم حفظ التعديلات بنجاح.")
            st.rerun()

    # ------------------------------------------------------
    # ➕ إضافة مجموعة جديدة
    # ------------------------------------------------------
    with st.expander("➕ إضافة مجموعة", expanded=False):
        school_name = get_school_name(school_id) if school_id else "—"

        with st.form("add_group_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                gname = st.text_input(
                    "اسم المجموعة (إجباري)", key="add_group_name")
                teacher_name = st.selectbox(
                    "المعلم", ["(بدون معلم)"] + [t[1] for t in teachers], key="add_group_teacher")
            with col2:
                st.text_input("المدرسة", school_name,
                              disabled=True, key="add_group_school")

            if st.form_submit_button("➕ إضافة مجموعة", type="primary", key="add_group_btn"):
                if not gname.strip():
                    st.error("⚠️ اسم المجموعة إجباري.")
                else:
                    tid = None if teacher_name == "(بدون معلم)" else t_map.get(
                        teacher_name)
                    with closing(get_conn()) as conn:
                        c = conn.cursor()
                        c.execute("INSERT INTO groups(name, teacher_id, school_id) VALUES(?,?,?)",
                                  (gname.strip(), tid, school_id))
                        conn.commit()
                    st.success(
                        f"✅ تمت إضافة المجموعة '{gname}' إلى مدرسة {school_name}.")
                    st.rerun()

    # ------------------------------------------------------
    # 🗑️ حذف مجموعة
    # ------------------------------------------------------
    with st.expander("🗑️ حذف مجموعة", expanded=False):
        if df.empty:
            st.info("لا توجد مجموعات حالياً.")
        else:
            opt_map = {f"{r['اسم المجموعة']} (ID:{r['ID']})": int(
                r["ID"]) for _, r in df.iterrows()}
            pick = st.selectbox("اختر مجموعة", list(
                opt_map.keys()), key="group_delete_select")
            gid = opt_map[pick]
            if st.button("🗑️ حذف المجموعة", type="primary", key=f"group_delete_btn_{gid}"):
                @st.dialog("تأكيد حذف المجموعة")
                def _confirm_delete_group():
                    st.error(
                        "⚠️ هل أنت متأكد من حذف هذه المجموعة؟ سيُحذف معها جميع طلابها.")
                    c1, c2 = st.columns(2)
                    if c1.button("نعم، حذف نهائي", type="primary", key=f"group_yes_{gid}"):
                        delete_group_and_students(gid)
                        st.success("✅ تم حذف المجموعة وجميع طلابها.")
                        st.rerun()
                    if c2.button("إلغاء", key=f"group_no_{gid}"):
                        st.rerun()
                _confirm_delete_group()


# ================================
# صفحة المدارس (خاصة بـ super_admin)
# ================================
def page_schools():
    st.markdown(
        """
        <p style='text-align:center; color:#777; font-size:17px; font-family:"Amiri", "Scheherazade New", serif;'>
        🌿 قال رسول الله <span style='color:#006B3C;'>ﷺ</span>:
        «خيركم من تعلم القرآن وعلّمه» 🌿
        </p>
        """,
        unsafe_allow_html=True
    )
    st.subheader("🏫 إدارة المدارس")

    # =====================================================
    # 📋 جدول المدارس
    # =====================================================
    with st.expander("📋 جدول المدارس", expanded=True):
        st.caption("🖊️ يمكنك تعديل بيانات المدارس مباشرة من هذا الجدول:")

        with closing(get_conn()) as conn:
            c = conn.cursor()
            c.execute("""
                SELECT 
                    id,
                    name AS المدرسة,
                    COALESCE(visitor_password, '') AS كلمة_سر_الزوار,
                    COALESCE(admin_name, '') AS اسم_المدير,
                    COALESCE(admin_username, '') AS اسم_الآدمن,
                    COALESCE(admin_password, '') AS كلمة_سر_الآدمن,
                    COALESCE(email, '') AS الإيميل,
                    COALESCE(phone, '') AS الهاتف,
                    COALESCE(address, '') AS العنوان
                FROM schools
                ORDER BY name COLLATE NOCASE
            """)
            rows = c.fetchall()

        df = pd.DataFrame(rows, columns=[
            "ID", "المدرسة", "كلمة سر الزوار", "اسم المدير",
            "اسم الآدمن", "كلمة سر الآدمن", "الإيميل", "الهاتف", "العنوان"
        ])

        edited = st.data_editor(
            df,
            use_container_width=True,
            num_rows="fixed",
            key="school_editor",
        )

        if st.button("💾 حفظ تعديلات المدارس", type="primary", key="school_save_btn"):
            with closing(get_conn()) as conn:
                c = conn.cursor()
                for _, r in edited.iterrows():
                    c.execute("""
                        UPDATE schools
                        SET name=?, visitor_password=?, admin_name=?, admin_username=?, admin_password=?, 
                            email=?, phone=?, address=?
                        WHERE id=?
                    """, (
                        r["المدرسة"], r["كلمة سر الزوار"], r["اسم المدير"],
                        r["اسم الآدمن"], r["كلمة سر الآدمن"],
                        r["الإيميل"], r["الهاتف"], r["العنوان"], int(r["ID"])
                    ))
                conn.commit()
            st.success("✅ تم حفظ جميع التعديلات بنجاح.")
            st.rerun()

    # =====================================================
    # ➕ إضافة مدرسة جديدة
    # =====================================================
    with st.expander("➕ إضافة مدرسة جديدة", expanded=False):
        st.caption(
            "🧩 أضف مدرسة جديدة مع بيانات المدير والآدمن وكلمة السر الخاصة به.")

        with st.form("add_school_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("🏫 اسم المدرسة", key="add_school_name")
                principal = st.text_input(
                    "👨‍💼 اسم المدير", key="add_school_principal")
                admin_username = st.text_input(
                    "👤 اسم الآدمن", key="add_school_admin")
                email = st.text_input("✉️ الإيميل", key="add_school_email")
            with col2:
                visitor_password = st.text_input(
                    "🔑 كلمة سر الزوار", value="0000", key="add_school_vpass")
                address = st.text_input("📍 العنوان", key="add_school_address")
                admin_password = st.text_input(
                    "🔐 كلمة سر الآدمن", value="admin123", key="add_school_apass")
                phone = st.text_input("📞 الهاتف", key="add_school_phone")

            submitted = st.form_submit_button(
                "➕ إضافة مدرسة", type="primary", key="school_add_btn")
            if submitted:
                if not name.strip() or not admin_username.strip():
                    st.error("⚠️ يجب إدخال اسم المدرسة واسم الأدمن.")
                else:
                    with closing(get_conn()) as conn:
                        c = conn.cursor()
                        # 1️⃣ إضافة المدرسة
                        c.execute("""
                            INSERT INTO schools(name, admin_name, admin_username, admin_password, email, phone, address, visitor_password)
                            VALUES(?,?,?,?,?,?,?,?)
                        """, (
                            name.strip(), principal.strip(), admin_username.strip(), admin_password.strip(),
                            email.strip(), phone.strip(), address.strip(), visitor_password.strip()
                        ))
                        conn.commit()
                        school_id = c.lastrowid

                        # 2️⃣ إنشاء مستخدم الأدمن تلقائيًا في جدول users
                        c.execute("""
                            INSERT INTO users(username, password, role, related_id, school_id)
                            VALUES(?,?,?,?,?)
                        """, (admin_username.strip(), admin_password.strip(), "school_admin", None, school_id))
                        conn.commit()

                    st.success(
                        f"✅ تمت إضافة المدرسة '{name}' وربط الأدمن '{admin_username}' بكلمة السر '{admin_password}'.")
                    st.rerun()

    # =====================================================
    # 🗑️ حذف مدرسة
    # =====================================================
    with st.expander("🗑️ حذف مدرسة", expanded=False):
        st.caption(
            "⚠️ سيتم حذف جميع البيانات التابعة للمدرسة (المعلمين، المجموعات، الطلاب).")

        with closing(get_conn()) as conn:
            c = conn.cursor()
            c.execute("SELECT id, name FROM schools ORDER BY name COLLATE NOCASE")
            schools = c.fetchall()

        if not schools:
            st.info("❕ لا توجد مدارس حالياً.")
        else:
            opt_map = {f"{s[1]} (ID:{s[0]})": s[0] for s in schools}
            pick = st.selectbox("اختر مدرسة للحذف", list(
                opt_map.keys()), key="school_delete_select")
            sid = opt_map[pick]

            if st.button("🗑️ حذف المدرسة", type="primary", key=f"school_delete_btn_{sid}"):
                @st.dialog("تأكيد حذف المدرسة")
                def _confirm_delete_school():
                    st.error("⚠️ هل أنت متأكد من حذف هذه المدرسة وجميع بياناتها؟")
                    c1, c2 = st.columns(2)
                    if c1.button("نعم، حذف نهائي", type="primary", key=f"school_yes_{sid}"):

                        with closing(get_conn()) as conn:
                            c = conn.cursor()
                            c.execute(
                                "DELETE FROM users WHERE school_id=?", (sid,))
                            c.execute(
                                "DELETE FROM teachers WHERE school_id=?", (sid,))
                            c.execute(
                                "DELETE FROM groups WHERE school_id=?", (sid,))
                            c.execute(
                                "DELETE FROM students WHERE school_id=?", (sid,))
                            c.execute("DELETE FROM schools WHERE id=?", (sid,))
                            conn.commit()

                        st.success("✅ تم حذف المدرسة وكل بياناتها.")
                        st.rerun()

                    if c2.button("إلغاء", key=f"school_no_{sid}"):
                        st.rerun()

                _confirm_delete_school()


def page_backup():
    st.markdown(
        """
        <p style='text-align:center; color:#777; font-size:17px; font-family:"Amiri", "Scheherazade New", serif;'>
        🌿 قال رسول الله <span style='color:#006B3C;'>ﷺ</span>:
        «خيركم من تعلم القرآن وعلّمه» 🌿
        </p>
        """,
        unsafe_allow_html=True
    )
    st.subheader("🗄️ النسخ الاحتياطي")
    from core.db import DB_PATH
    import os
    if os.path.exists(DB_PATH):
        with open(DB_PATH, "rb") as f:
            data = f.read()
        st.download_button("⬇️ تنزيل قاعدة البيانات", data=data,
                           file_name="hifz_backup.db", mime="application/octet-stream")
    else:
        st.info("لا يوجد ملف قاعدة بيانات بعد.")


# ================================
# صفحة لوحة المعلّم (محدَّثة للنظام متعدد المدارس)
# ================================
def page_teacher_dashboard():
    st.markdown(
        """
        <p style='text-align:center; color:#777; font-size:17px; font-family:"Amiri", "Scheherazade New", serif;'>
        🌿 قال رسول الله <span style='color:#006B3C;'>ﷺ</span>:
        «خيركم من تعلم القرآن وعلّمه» 🌿
        </p>
        """,
        unsafe_allow_html=True
    )
    """
    لوحة المعلم — تتيح متابعة:
      • أحدث عمليات الحفظ (صفحات / آيات)
      • تنبيهات الخمول (طلاب لم يسجّلوا حفظًا)
      • الأهداف المتأخرة
    تتوافق مع:
      - super_admin: يرى كل المدارس
      - school_admin: يرى طلاب مدرسته
      - teacher: يرى فقط طلاب مجموعاته
    """
    st.subheader("📋 لوحة المعلم")

    role = st.session_state.get("user_role", "guest")
    school_id = st.session_state.get("school_id", None)
    teacher_id = st.session_state.get("user_rel_id", None)

    # إعداد المتغيرات العامة للواجهة
    ss = st.session_state
    ss.setdefault("td_limit", 25)
    ss.setdefault("td_idle_days", 7)

    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        limit = st.number_input(
            "🔢 عدد الصفوف المعروضة", 5, 100, ss["td_limit"], step=5, key="td_limit_in")
        ss["td_limit"] = limit
    with c2:
        idle_days = st.number_input(
            "⏳ عدد أيام الخمول", 1, 60, ss["td_idle_days"], step=1, key="td_idle_days_in")
        ss["td_idle_days"] = idle_days
    with c3:
        st.caption("تصفية تلقائية حسب صلاحيات المستخدم.")

    # 1️⃣ أحدث عمليات الحفظ (صفحات)
    with st.expander("🧾 أحدث عمليات الحفظ (صفحات)"):
        query = """
            SELECT p.updated_at, s.full_name, p.page_number, p.is_memorized, g.name AS group_name, t.name AS teacher_name
            FROM student_pages p
            JOIN students s ON s.id = p.student_id
            LEFT JOIN groups g ON g.id = s.group_id
            LEFT JOIN teachers t ON t.id = g.teacher_id
        """
        where, params = [], []
        if role == "school_admin":
            where.append("g.school_id=?")
            params.append(school_id)
        elif role == "teacher":
            where.append("g.teacher_id=? AND g.school_id=?")
            params.extend([teacher_id, school_id])

        if where:
            query += " WHERE " + " AND ".join(where)
        query += " ORDER BY p.updated_at DESC LIMIT ?"
        params.append(limit)

        with closing(get_conn()) as conn:
            c = conn.cursor()
            c.execute(query, params)
            rows = c.fetchall()

        if rows:
            df = pd.DataFrame(
                rows, columns=["التاريخ", "الطالب", "الصفحة", "محفوظ؟", "المجموعة", "المعلم"])
            df["محفوظ؟"] = df["محفوظ؟"].map({1: "✅ نعم", 0: "❌ لا"})
            st.dataframe(df, use_container_width=True)
        else:
            st.info("لا توجد بيانات صفحات حتى الآن.")

    # 2️⃣ أحدث عمليات الحفظ (آيات)
    with st.expander("📖 أحدث عمليات الحفظ (آيات)"):
        query = """
            SELECT r.updated_at, s.full_name, r.surah_id, r.from_ayah, r.to_ayah, r.is_memorized, g.name AS group_name, t.name AS teacher_name
            FROM student_ayah_ranges r
            JOIN students s ON s.id = r.student_id
            LEFT JOIN groups g ON g.id = s.group_id
            LEFT JOIN teachers t ON t.id = g.teacher_id
        """
        where, params = [], []
        if role == "school_admin":
            where.append("g.school_id=?")
            params.append(school_id)
        elif role == "teacher":
            where.append("g.teacher_id=? AND g.school_id=?")
            params.extend([teacher_id, school_id])

        if where:
            query += " WHERE " + " AND ".join(where)
        query += " ORDER BY r.updated_at DESC LIMIT ?"
        params.append(limit)

        with closing(get_conn()) as conn:
            c = conn.cursor()
            c.execute(query, params)
            rows = c.fetchall()

        if rows:
            df = pd.DataFrame(rows, columns=[
                              "التاريخ", "الطالب", "السورة", "من آية", "إلى آية", "محفوظ؟", "المجموعة", "المعلم"])
            df["محفوظ؟"] = df["محفوظ؟"].map({1: "✅ نعم", 0: "❌ لا"})
            st.dataframe(df, use_container_width=True)
        else:
            st.info("لا توجد بيانات آيات حتى الآن.")

    # 3️⃣ تنبيهات الخمول
    with st.expander("⏰ تنبيهات الخمول"):
        days = int(ss["td_idle_days"])
        threshold = (datetime.now() - timedelta(days=days)
                     ).strftime("%Y-%m-%d %H:%M:%S")

        query = f"""
        WITH last_pages AS (
            SELECT student_id, MAX(updated_at) AS lastp
            FROM student_pages GROUP BY student_id
        ),
        last_ranges AS (
            SELECT student_id, MAX(updated_at) AS lastr
            FROM student_ayah_ranges GROUP BY student_id
        ),
        base AS (
            SELECT
                s.id AS sid,
                s.full_name AS sname,
                g.name AS group_name,
                t.name AS teacher_name,
                CASE
                    WHEN last_pages.lastp IS NULL THEN last_ranges.lastr
                    WHEN last_ranges.lastr IS NULL THEN last_pages.lastp
                    WHEN last_pages.lastp >= last_ranges.lastr THEN last_pages.lastp
                    ELSE last_ranges.lastr
                END AS last_act
            FROM students s
            LEFT JOIN groups g ON g.id = s.group_id
            LEFT JOIN teachers t ON t.id = g.teacher_id
            LEFT JOIN last_pages ON last_pages.student_id = s.id
            LEFT JOIN last_ranges ON last_ranges.student_id = s.id
        )
        SELECT sid, sname, group_name, teacher_name, last_act
        FROM base
        """

        where, params = [], []
        if role == "school_admin":
            where.append(
                "group_name IN (SELECT name FROM groups WHERE school_id=?)")
            params.append(school_id)
        elif role == "teacher":
            where.append(
                "teacher_name IN (SELECT name FROM teachers WHERE id=? AND school_id=?)")
            params.extend([teacher_id, school_id])

        if where:
            query += " WHERE " + " AND ".join(where)
        query += " AND (last_act IS NULL OR last_act < ?) ORDER BY last_act ASC"
        params.append(threshold)

        with closing(get_conn()) as conn:
            c = conn.cursor()
            # إصلاح مشكلة WHERE/AND في الاستعلام
            fixed_query = query.strip()
            if "WHERE" not in fixed_query.upper():
                # إذا لم تحتوي الجملة على WHERE ولكن تحتوي على AND، نضيف WHERE 1=1
                fixed_query = fixed_query.replace("AND", "WHERE 1=1 AND", 1)
            elif fixed_query.strip().upper().startswith("AND"):
                # إذا بدأت الجملة بـ AND فقط، نضيف WHERE 1=1 قبلها
                fixed_query = "WHERE 1=1 " + fixed_query
            c.execute(fixed_query, params)
            rows = c.fetchall()

        if rows:
            df = pd.DataFrame(
                rows, columns=["ID الطالب", "الطالب", "المجموعة", "المعلم", "آخر نشاط"])
            st.dataframe(df, use_container_width=True)
        else:
            st.success("✅ لا يوجد طلاب خاملون حالياً!")

    # 4️⃣ الأهداف المتأخرة
    with st.expander("⚠️ الأهداف المتأخرة"):
        now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        query = """
        SELECT s.full_name, g.name AS group_name, t.name AS teacher_name,
               go.category, go.periodicity, go.target_kind,
               go.page_from, go.page_to, go.surah_id, go.from_ayah, go.to_ayah,
               go.due_date, go.end_date, go.status
        FROM goals go
        JOIN students s ON s.id = go.student_id
        LEFT JOIN groups g ON g.id = s.group_id
        LEFT JOIN teachers t ON t.id = g.teacher_id
        WHERE (go.status <> 'done')
          AND (
            (go.periodicity='once' AND go.due_date IS NOT NULL AND go.due_date < ?)
            OR
            (go.periodicity IN ('weekly','biweekly','monthly') AND go.end_date IS NOT NULL AND go.end_date < ?)
          )
        """
        params = [now_iso, now_iso]

        if role == "school_admin":
            query += " AND g.school_id=?"
            params.append(school_id)
        elif role == "teacher":
            query += " AND g.teacher_id=? AND g.school_id=?"
            params.extend([teacher_id, school_id])

        query += " ORDER BY go.end_date DESC LIMIT ?"
        params.append(limit)

        with closing(get_conn()) as conn:
            c = conn.cursor()
            c.execute(query, params)
            rows = c.fetchall()

        if rows:
            df = pd.DataFrame(rows, columns=[
                "الطالب", "المجموعة", "المعلم", "التصنيف", "الدورية", "النوع",
                "من صفحة", "إلى صفحة", "السورة", "من آية", "إلى آية",
                "تاريخ الإنجاز", "نهاية المدة", "الحالة"
            ])
            st.dataframe(df, use_container_width=True)
        else:
            st.success("✅ لا توجد أهداف متأخرة حالياً.")


def page_analytics():
    html = ""
    st.markdown(
        """
        <p style='text-align:center; color:#777; font-size:17px; font-family:"Amiri", "Scheherazade New", serif;'>
        🌿 قال رسول الله <span style='color:#006B3C;'>ﷺ</span>:
        «خيركم من تعلم القرآن وعلّمه» 🌿
        </p>
        """,
        unsafe_allow_html=True
    )
    with st.expander("🏆 منصة التتويج الشهرية", expanded=False):
        # st.subheader("🏆 منصة التتويج الشهرية")

        # ========================================
        # صلاحيات المستخدم
        # ========================================
        role = st.session_state.get("user_role", "")
        school_id = st.session_state.get("school_id", None)
        rel_id = st.session_state.get("user_rel_id", None)

        # ========================================
        # اختيار المدرسة
        # ========================================
        with closing(get_conn()) as conn:
            c = conn.cursor()
            if role == "super_admin":
                c.execute(
                    "SELECT id, name FROM schools ORDER BY name COLLATE NOCASE")
                schools = c.fetchall()
                school_map = {f"{s[1]} (ID:{s[0]})": s[0] for s in schools}
                pick_school = st.selectbox("🏫 اختر مدرسة", list(
                    school_map.keys()), key="an_school_pick")
                school_id = school_map[pick_school]
            else:
                c.execute("SELECT name FROM schools WHERE id=?", (school_id,))
                row = c.fetchone()
                school_name = row[0] if row else "مدرستي"
                st.markdown(f"### 🏫 {school_name}")

        # ========================================
        # نوع التتويج + النطاق
        # ========================================
        c1, c2 = st.columns(2)
        with c1:
            metric = st.radio("📊 نوع التتويج", [
                              "النقاط هذا الشهر", "الصفحات هذا الشهر"], horizontal=True)
        with c2:
            scope = st.radio(
                "🔍 النطاق", ["على مستوى المدرسة", "على مستوى مجموعة"], horizontal=True)

        sel_gid = None
        groups = []
        with closing(get_conn()) as conn:
            c = conn.cursor()
            if scope == "على مستوى مجموعة":
                if role == "teacher":
                    c.execute(
                        "SELECT id, name FROM groups WHERE teacher_id=? AND school_id=?", (rel_id, school_id))
                else:
                    c.execute(
                        "SELECT id, name FROM groups WHERE school_id=?", (school_id,))
                groups = c.fetchall()

        if scope == "على مستوى مجموعة" and groups:
            pick_group = st.selectbox(
                "📘 اختر مجموعة", ["(اختر)"] + [g[1] for g in groups])
            if pick_group != "(اختر)":
                sel_gid = next((g[0]
                               for g in groups if g[1] == pick_group), None)

        # ========================================
        # تحديد الفترة الزمنية
        # ========================================
        start = date.today().replace(day=1).isoformat()
        end = date.today().isoformat()

        # ========================================
        # جلب البيانات
        # ========================================
        with closing(get_conn()) as conn:
            c = conn.cursor()
            if metric == "النقاط هذا الشهر":
                query = """
                    SELECT s.full_name, g.name, SUM(r.points) AS total
                    FROM rewards r
                    JOIN students s ON s.id = r.student_id
                    LEFT JOIN groups g ON g.id = s.group_id
                    WHERE DATE(r.created_at) BETWEEN ? AND ?
                """
            else:
                query = """
                    SELECT s.full_name, g.name, COUNT(sp.page_number) AS total
                    FROM student_pages sp
                    JOIN students s ON s.id = sp.student_id
                    LEFT JOIN groups g ON g.id = s.group_id
                    WHERE sp.is_memorized=1 AND DATE(sp.updated_at) BETWEEN ? AND ?
                """

            params = [start, end]
            if sel_gid:
                query += " AND s.group_id=?"
                params.append(sel_gid)
            else:
                query += " AND s.school_id=?"
                params.append(school_id)

            query += " GROUP BY s.id ORDER BY total DESC LIMIT 5"
            c.execute(query, params)
            rows = c.fetchall()

        # ========================================
        # عرض النتائج
        # ========================================
        st.markdown("### 🏅 أبطال هذا الشهر")

        if not rows:
            st.info("لا توجد بيانات كافية لهذا الشهر.")
            return

        medals = ["👑", "🥈", "🥉", "🏅", "🎖️"]
        colors = ["#FFD54F", "#C0C0C0", "#CD7F32", "#90CAF9", "#CE93D8"]

        # ترتيب العرض: الخامس، الثالث، الأول، الثاني، الرابع
        order = [4, 2, 0, 1, 3] if len(rows) >= 5 else list(range(len(rows)))
        rows = [rows[i] for i in order]
        medals = [medals[i] for i in order]
        colors = [colors[i] for i in order]

        # حساب ارتفاع نسبي
        values = [r[2] for r in rows]
        max_val = max(values) if values else 1
        min_height = 150
        max_height = 350

        # ========================================
        # بناء HTML ديناميكي
        # ========================================
        html = """
        <style>
        .podium-container {
            display: flex;
            justify-content: center;
            align-items: flex-end;
            gap: 20px;
            margin-top: 40px;
            flex-wrap: nowrap;
        }
        .card {
            text-align: center;
            color: black;
            border-radius: 25px;
            width: 170px;
            box-shadow: 0 5px 12px rgba(0,0,0,0.25);
            transition: all 0.3s ease;
            display: flex;
            flex-direction: column;
            justify-content: flex-end;
            padding-bottom: 20px;
        }
        .card:hover {
            transform: translateY(-5px) scale(1.03);
            box-shadow: 0 8px 16px rgba(0,0,0,0.35);
        }
        .rank { font-size: 32px; margin-bottom: 8px; }
        .name { font-size: 20px; font-weight: bold; margin-bottom: 4px; }
        .group { font-size: 14px; color: #333; margin-bottom: 4px; }
        .value { font-size: 16px; font-weight: bold; margin-top: 6px; }
        </style>
        <div class="podium-container">
        """

        for i, (name, group, total) in enumerate(rows):
            height = min_height + \
                int((total / max_val) * (max_height - min_height))
            html += f"""
            <div class="card" style="background:{colors[i % len(colors)]}; height:{height}px;">
                <div class="rank">{medals[i]}</div>
                <div class="name">{name}</div>
                <div class="group">{group or ''}</div>
                <div class="value">{total} {'نقطة' if metric == 'النقاط هذا الشهر' else 'صفحة'}</div>
            </div>
            """

        html += "</div>"
        components.html(html, height=500, scrolling=False)

    # ------------------------------------
    # (ب) توزيع الطلاب على مستوى المدرسة أو المجموعة
    # ------------------------------------
    with st.expander("👥 توزيع الطلاب", expanded=False):
        role = st.session_state.get("user_role", "")
        school_id = st.session_state.get("school_id", None)
        rel_id = st.session_state.get("user_rel_id", None)

        scope = st.radio("النطاق", [
                         "على مستوى المدرسة", "مجموعة محددة"], horizontal=True, key="dist_scope_school")
        sel_gid = None

        with closing(get_conn()) as conn:
            c = conn.cursor()
            if scope == "مجموعة محددة":
                if role == "teacher":
                    c.execute(
                        "SELECT id, name FROM groups WHERE teacher_id=? ORDER BY name COLLATE NOCASE", (rel_id,))
                else:
                    c.execute(
                        "SELECT id, name FROM groups WHERE school_id=? ORDER BY name COLLATE NOCASE", (school_id,))
                groups = c.fetchall()
                pick = st.selectbox("اختر مجموعة", [
                                    "(اختر)"] + [g[1] for g in groups], key="dist_group_pick_school")
                if pick != "(اختر)":
                    sel_gid = next((g[0]
                                   for g in groups if g[1] == pick), None)

            grp_counts = []
            if sel_gid:
                # إحصاءات المجموعة المحددة
                c.execute("""
                    SELECT g.name, COUNT(s.id)
                    FROM groups g
                    LEFT JOIN students s ON s.group_id = g.id
                    WHERE g.id=?
                    GROUP BY g.name
                """, (sel_gid,))
            else:
                # إحصاءات المدرسة كاملة
                if role == "super_admin":
                    c.execute("""
                        SELECT sc.name, COUNT(st.id)
                        FROM schools sc
                        LEFT JOIN students st ON st.school_id = sc.id
                        GROUP BY sc.name
                    """)
                else:
                    c.execute("""
                        SELECT g.name, COUNT(s.id)
                        FROM groups g
                        LEFT JOIN students s ON s.group_id = g.id
                        WHERE g.school_id=?
                        GROUP BY g.name
                    """, (school_id,))
            grp_counts = c.fetchall()

        if grp_counts:
            df = pd.DataFrame(grp_counts, columns=["الاسم", "عدد الطلاب"])
            st.bar_chart(df.set_index("الاسم"))
        else:
            st.info("لا توجد بيانات لعرض توزيع الطلاب.")

    # ------------------------------------
    # (ج) تقدير تاريخ الختم
    # ------------------------------------
    with st.expander("📅 تقدير تاريخ الختم", expanded=False):
        role = st.session_state.get("user_role", "")
        school_id = st.session_state.get("school_id", None)
        rel_id = st.session_state.get("user_rel_id", None)

        with closing(get_conn()) as conn:
            c = conn.cursor()
            if role == "super_admin":
                c.execute(
                    "SELECT id, full_name FROM students ORDER BY full_name COLLATE NOCASE")
            elif role == "school_admin":
                c.execute(
                    "SELECT id, full_name FROM students WHERE school_id=? ORDER BY full_name COLLATE NOCASE", (school_id,))
            elif role == "teacher":
                c.execute("""
                    SELECT s.id, s.full_name
                    FROM students s
                    JOIN groups g ON s.group_id=g.id
                    WHERE g.teacher_id=? ORDER BY s.full_name COLLATE NOCASE
                """, (rel_id,))
            else:
                c.execute(
                    "SELECT id, full_name FROM students WHERE school_id=? ORDER BY full_name COLLATE NOCASE", (school_id,))
            all_students = c.fetchall()

        if all_students:
            pick = st.selectbox("اختر طالبًا", [
                                f"{s[1]} (#{s[0]})" for s in all_students], key="analytics_school_pick_student")
            try:
                sid = int(pick.split("#")[-1].strip(")"))
            except Exception:
                sid = all_students[0][0]
            eta = estimate_finish_date(sid)
            if eta:
                st.success(f"تقدير تاريخ الختم: {eta}")
            else:
                st.info("لا يمكن التقدير حاليًا (معدل إنجاز غير كافٍ).")
        else:
            st.info("لا يوجد طلاب بعد.")


def page_import_export():
    st.markdown(
        """
        <p style='text-align:center; color:#777; font-size:17px; font-family:"Amiri", "Scheherazade New", serif;'>
        🌿 قال رسول الله <span style='color:#006B3C;'>ﷺ</span>:
        «خيركم من تعلم القرآن وعلّمه» 🌿
        </p>
        """,
        unsafe_allow_html=True
    )
    """واجهة صفحة الاستيراد والتصدير (CSV)"""
    import io
    import csv

    st.subheader("⬆️⬇️ الاستيراد والتصدير (CSV)")

    role = st.session_state.get("user_role", "")
    school_id = st.session_state.get("school_id", None)

    # =======================
    # 🧩 استيراد الطلاب
    # =======================
    st.markdown("### 📤 استيراد الطلاب من ملف CSV")
    st.caption(
        "صيغة الأعمدة: name,gender,birth,join,group,phone,email,guardian"
        " — يمكن ترك group فارغة وسيُضاف الطالب بدون مجموعة."
    )

    up = st.file_uploader("📤 رفع ملف CSV لإضافة طلاب", type=[
                          "csv"], key="import_students_csv")
    if up is not None:
        data = up.read().decode("utf-8", errors="ignore").splitlines()
        r = csv.DictReader(data)
        added = 0
        groups = {g[1]: g[0] for g in get_groups()}
        for row in r:
            try:
                name = row.get("name", "").strip()
                gender = row.get("gender", "ذكر").strip()
                birth = row.get("birth", "")
                join = row.get("join", "")
                gname = row.get("group", "").strip()
                phone = row.get("phone", "").strip()
                email = row.get("email", "").strip()
                guardian = row.get("guardian", "").strip()
                gid = groups.get(gname) if gname else None
                if name and iso_date(birth) and iso_date(join):
                    add_student(
                        full_name=name,
                        gender=gender,
                        birth_date=birth,
                        join_date=join,
                        group_id=gid,
                        phone=phone,
                        email=email,
                        guardian_name=guardian,
                    )
                    added += 1
            except Exception:
                continue
        st.success(f"✅ تمت إضافة {added} طالب/طالبة بنجاح.")

    # =======================
    # 🧭 استيراد خريطة الصفحة والآية
    # =======================
    st.markdown("---")
    st.markdown("### 📘 استيراد خريطة الصفحة ← الآية")
    st.caption("صيغة CSV: page,surah,ayah (كل سطر يمثل آية واحدة).")

    up_map = st.file_uploader("رفع CSV للمرجع page→ayah", type=[
                              "csv"], key="import_map_csv")
    if up_map is not None:
        cnt = _import_page_ayahs_csv(up_map.read())
        st.success(f"✅ تم استيراد {cnt} صفًا إلى ref_page_ayahs.")
    st.info("حالة الخريطة: " +
            ("متوفّرة ✅" if has_page_ayah_map() else "غير متوفّرة ❌"))

    # =======================
    # 📤 تصدير بيانات الطلاب
    # =======================
    st.markdown("---")
    st.markdown("### ⬇️ تصدير بيانات الطلاب")
    if st.button("📥 تصدير بيانات الطلاب (CSV)", key="export_students_btn"):
        with closing(get_conn()) as conn:
            c = conn.cursor()
            if role == "super_admin":
                c.execute(
                    "SELECT id, full_name, gender, birth_date, join_date, IFNULL(group_id,''), "
                    "phone, email, guardian_name, IFNULL(school_id,'') "
                    "FROM students ORDER BY id"
                )
            else:
                c.execute(
                    "SELECT id, full_name, gender, birth_date, join_date, IFNULL(group_id,''), "
                    "phone, email, guardian_name, school_id "
                    "FROM students WHERE school_id=? ORDER BY id",
                    (school_id,),
                )
            rows = c.fetchall()

        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(
            [
                "id",
                "name",
                "gender",
                "birth",
                "join",
                "group_id",
                "phone",
                "email",
                "guardian",
                "school_id",
            ]
        )
        w.writerows(rows)
        st.download_button(
            "⬇️ تنزيل students.csv",
            data=out.getvalue(),
            file_name="students.csv",
            mime="text/csv",
        )

    # =======================
    # 📜 تصدير سجل الصفحات
    # =======================
    st.markdown("---")
    st.markdown("### ⬇️ تصدير سجل الصفحات")
    if st.button("📥 تصدير سجل الصفحات (CSV)", key="export_pages_btn"):
        with closing(get_conn()) as conn:
            c = conn.cursor()
            if role == "super_admin":
                c.execute(
                    "SELECT student_id, page_number, is_memorized, updated_at FROM student_pages")
            else:
                c.execute(
                    """SELECT p.student_id, p.page_number, p.is_memorized, p.updated_at
                       FROM student_pages p
                       JOIN students s ON s.id = p.student_id
                       WHERE s.school_id=?""",
                    (school_id,),
                )
            rows = c.fetchall()

        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(["student_id", "page", "is_mem", "updated_at"])
        w.writerows(rows)
        st.download_button(
            "⬇️ تنزيل pages.csv",
            data=out.getvalue(),
            file_name="pages.csv",
            mime="text/csv",
        )

    # =======================
    # 👨‍🏫 تصدير بيانات المعلّمين
    # =======================
    st.markdown("---")
    st.markdown("### ⬇️ تصدير بيانات المعلّمين")
    if st.button("📥 تصدير بيانات المعلّمين (CSV)", key="export_teachers_btn"):
        with closing(get_conn()) as conn:
            c = conn.cursor()
            if role == "super_admin":
                c.execute(
                    "SELECT id, full_name, gender, birth_date, phone, email, memorization_note, school_id "
                    "FROM teachers ORDER BY id"
                )
            else:
                c.execute(
                    "SELECT id, full_name, gender, birth_date, phone, email, memorization_note, school_id "
                    "FROM teachers WHERE school_id=? ORDER BY id",
                    (school_id,),
                )
            rows = c.fetchall()

        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(["id", "name", "gender", "birth", "phone",
                   "email", "memorization_note", "school_id"])
        w.writerows(rows)
        st.download_button(
            "⬇️ تنزيل teachers.csv",
            data=out.getvalue(),
            file_name="teachers.csv",
            mime="text/csv",
        )

    # =======================
    # 👥 تصدير بيانات المجموعات
    # =======================
    st.markdown("---")
    st.markdown("### ⬇️ تصدير بيانات المجموعات (الفصول)")
    if st.button("📥 تصدير بيانات المجموعات (CSV)", key="export_groups_btn"):
        with closing(get_conn()) as conn:
            c = conn.cursor()
            if role == "super_admin":
                c.execute(
                    "SELECT id, name, teacher_id, school_id FROM groups ORDER BY id")
            else:
                c.execute(
                    "SELECT id, name, teacher_id, school_id FROM groups WHERE school_id=?", (school_id,))
            rows = c.fetchall()

        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(["id", "name", "teacher_id", "school_id"])
        w.writerows(rows)
        st.download_button(
            "⬇️ تنزيل groups.csv",
            data=out.getvalue(),
            file_name="groups.csv",
            mime="text/csv",
        )
