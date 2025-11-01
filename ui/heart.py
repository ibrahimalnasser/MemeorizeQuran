# -*- coding: utf-8 -*-
"""
ui/heart.py
------------
يتضمّن جميع الدوال المسؤولة عن رسم القلب التفاعلي (SVG) المستخدم لتمثيل
تقدّم الحفظ حسب الأجزاء أو السور، مع دعم التكبير وكثافة التسميات
والموضع الخارجي للتسميات.
"""

import math
import streamlit as st

# =============================
# ثابت مسار القلب (Path)
# =============================
HEART_PATH = "M0,-35 C-30,-70 -95,-30 -75,20 C-60,60 0,90 0,90 C0,90 60,60 75,20 C95,-30 30,-70 0,-35 Z"


# =============================
# دالة رسم قطاع (Arc Sector)
# =============================
def _sector_path(start_rad: float, end_rad: float, r: float) -> str:
    """تحسب مسار قطاع دائري على شكل قطعة من القلب."""
    sweep = (end_rad - start_rad) % (2 * math.pi)
    laf = 1 if sweep > math.pi else 0
    x1, y1 = r * math.cos(start_rad), r * math.sin(start_rad)
    x2, y2 = r * math.cos(end_rad), r * math.sin(end_rad)
    return f"M 0,0 L {x1:.2f},{y1:.2f} A {r},{r} 0 {laf} 1 {x2:.2f},{y2:.2f} Z"


# =============================
# دالة إنشاء SVG كامل للقلب
# =============================
def make_heart_svg(
    segments,
    scale: float = 1.0,
    mode: str = "surah",
    sid: int = 0,
    label_position: str = "outside",
    label_density: str = "medium",
) -> str:
    """
    تُنشئ كود SVG الكامل للقلب حسب المعطيات:
    - segments: قائمة القطاعات (نسبة الإنجاز والاسم والمعرّف)
    - scale: نسبة التكبير
    - mode: "surah" أو "juz"
    - label_position: موضع التسميات (outside / hidden)
    - label_density: كثافة التسميات ("low", "medium", "high", "full")
    """

    # منحنيات القلب الأصلية
    heart_curves = [
        ((0.0, -35.0), (-30.0, -70.0), (-95.0, -30.0), (-75.0, 20.0)),
        ((-75.0, 20.0), (-60.0, 60.0), (0.0, 90.0), (0.0, 90.0)),
        ((0.0, 90.0), (0.0, 90.0), (60.0, 60.0), (75.0, 20.0)),
        ((75.0, 20.0), (95.0, -30.0), (30.0, -70.0), (0.0, -35.0)),
    ]

    # أخذ عينات من منحنى بيزير
    def cubic(p0, p1, p2, p3, t):
        u = 1 - t
        return (
            u * u * u * p0[0] + 3 * u * u * t * p1[0] +
                3 * u * t * t * p2[0] + t * t * t * p3[0],
            u * u * u * p0[1] + 3 * u * u * t * p1[1] +
                3 * u * t * t * p2[1] + t * t * t * p3[1],
        )

    def sample_heart(n_per=140):
        pts = []
        for (p0, p1, p2, p3) in heart_curves:
            for i in range(n_per):
                t = i / float(n_per)
                pts.append(cubic(p0, p1, p2, p3, t))
        pts.append(heart_curves[-1][3])
        return pts

    heart_poly = sample_heart(140)

    # حساب نصف قطر التقاطع مع الحدود (للملصقات)
    def ray_intersect_radius(angle: float) -> float:
        dx, dy = math.cos(angle), math.sin(angle)
        best = None
        for i in range(len(heart_poly) - 1):
            x1, y1 = heart_poly[i]
            x2, y2 = heart_poly[i + 1]
            vx, vy = x2 - x1, y2 - y1
            det = dx * (-vy) - (-vx) * dy
            if abs(det) < 1e-6:
                continue
            r = (x1 * (-vy) - (-vx) * y1) / det
            u = (dx * y1 - dy * x1) / det
            if r >= 0 and 0.0 <= u <= 1.0:
                if best is None or r < best:
                    best = r
        return best if best is not None else 100.0

    # تقسيم الزوايا حسب الأوزان
    total_w = sum(max(0.0001, s.get("weight", 1.0)) for s in segments)
    angles, a = [], -math.pi / 2
    for s in segments:
        frac = max(0.0001, s.get("weight", 1.0)) / total_w
        start, end = a, a + frac * 2 * math.pi
        angles.append((start, end))
        a = end

    R = 100.0
    extra_top = 42 if label_position == "outside" else 12
    top_shift = -int(max(0, extra_top * (1.25 - scale)))
    bottom_pad = int(
        max(0, (scale - 1.0) * (240 if label_position == "outside" else 180)))

    # تنسيق CSS
    css = f"""
    <style>
      .heart-wrap {{
        width:100%;
        margin:{top_shift}px auto {bottom_pad}px auto;
        display:flex; justify-content:center; align-items:flex-start;
        overflow:visible; position:relative; z-index:0; pointer-events:none;
      }}
      .heart-wrap svg {{
        width:100%; height:auto; transform:scale({scale}); transform-origin:50% 50%;
        display:block; overflow:visible; pointer-events:none;
      }}
      .heart-wrap .hit, .heart-wrap a, .heart-wrap text {{ pointer-events:auto; }}
      .heart-wrap .hit {{ cursor:pointer; }}
      .lbl {{ fill:#111; font-family: Tahoma, Arial, sans-serif; pointer-events:none; }}
    </style>
    """

    svg = [
        css,
        '<div class="heart-wrap">',
        '<svg viewBox="-130 -130 260 260" preserveAspectRatio="xMidYMid meet">',
        '<defs>',
        f'<clipPath id="heartClip"><path d="{HEART_PATH}"/></clipPath>',
        '</defs>',
        '<g clip-path="url(#heartClip)">',
    ]

    # الخلفية (قطاعات متناوبة)
    for idx, s in enumerate(segments):
        start, end = angles[idx]
        base_fill = "#eef2f7" if idx % 2 == 0 else "#f6f7fb"
        svg.append(
            f'<path d="{_sector_path(start, end, R)}" fill="{base_fill}" stroke="none"></path>')

    # قطاعات الأهداف (تظهر باللون الذهبي/الأصفر)
    for idx, s in enumerate(segments):
        if s.get("has_goal", False):
            start, end = angles[idx]
            svg.append(
                f'<path d="{_sector_path(start, end, R)}" fill="rgba(255, 193, 7, 0.3)" stroke="#FFC107" stroke-width="2"></path>')

    # القطاعات المملوءة باللون الأحمر حسب الإنجاز
    for idx, s in enumerate(segments):
        start, end = angles[idx]
        ratio = max(0.0, min(1.0, float(s.get("ratio", 0.0))))
        if ratio <= 0:
            continue
        end_prog = start + (end - start) * ratio
        # إذا كان القطاع جزء من هدف ومكتمل، استخدم لون أخضر
        fill_color = "#22c55e" if s.get("has_goal", False) else "#dc2626"
        svg.append(
            f'<path d="{_sector_path(start, end_prog, R)}" fill="{fill_color}"></path>')

    # إضافة روابط النقر (عناصر تفاعلية)
    for idx, s in enumerate(segments):
        start, end = angles[idx]
        seg_id = s.get("id")
        title = s.get("title", "")
        href = f"?page=main&sid={sid if sid else ''}&dlg={mode}&seg={seg_id}"
        svg.append(
            f'<a href="{href}" xlink:href="{href}" target="_top">'
            f'<title>{title}</title>'
            f'<path class="hit" d="{_sector_path(start, end, R)}" fill="rgba(0,0,0,0)"></path></a>'
        )

    svg.append('</g>')

    # التسميات (خارج القلب)
    if label_position == "outside":
        arc_info = []
        for idx, s in enumerate(segments):
            start, end = angles[idx]
            arc_len = (end - start) * R
            arc_info.append((arc_len, idx))
        density_map = {"low": 0.25, "medium": 0.5, "high": 0.75, "full": 1.0}
        frac = density_map.get(label_density, 0.5)
        show_mask = [True] * \
            len(segments) if mode == "juz" else [False] * len(segments)
        if mode == "surah":
            arc_info.sort(reverse=True)
            upto = int(len(segments) * frac)
            for k, (_, idx) in enumerate(arc_info):
                if k < upto:
                    show_mask[idx] = True

        fs_fixed = 4.6
        margin = 5.0
        svg.append('<g>')
        for idx, s in enumerate(segments):
            if not show_mask[idx]:
                continue
            start, end = angles[idx]
            mid = (start + end) / 2.0
            r_edge = ray_intersect_radius(mid)
            r_txt = r_edge + margin
            x_txt = r_txt * math.cos(mid)
            y_txt = r_txt * math.sin(mid)
            # ✅ تحسين: عرض رقم الآية الحقيقي في وضع "سورة معينة (آيات)"
            # ✅ عرض الرقم المناسب حسب الوضع
            if mode == "surah":
                txt = str(s.get("sid", ""))  # رقم الآية
            elif mode == "juz" and "page_no" in s:
                txt = str(s["page_no"])      # رقم الصفحة الحقيقي
            else:
                txt = str(s.get("label", s.get("id", "")))
            svg.append(
                f'<text class="lbl" x="{x_txt:.2f}" y="{y_txt:.2f}" font-size="{fs_fixed}" '
                f'text-anchor="middle" dominant-baseline="middle">{txt}</text>'
            )
        svg.append('</g>')

    # إطار القلب
    svg += [
        f'<path d="{HEART_PATH}" fill="none" stroke="#9ca3af" stroke-width="2.2"></path>',
        '</svg>',
        '</div>',
    ]

    return "\n".join(svg)
