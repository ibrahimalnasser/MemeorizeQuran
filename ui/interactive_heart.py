# -*- coding: utf-8 -*-
"""
ui/interactive_heart.py
-----------------------
مكون تفاعلي للقلب يستخدم st.components.v1.html للتواصل ثنائي الاتجاه
"""

import streamlit.components.v1 as components


def render_interactive_heart(svg_content: str, height: int = 600):
    """
    يعرض القلب كمكون HTML مدمج في الصفحة.

    Args:
        svg_content: محتوى SVG الذي تم إنشاؤه بواسطة make_heart_svg
        height: ارتفاع المكون بالبكسل

    Returns:
        None
    """

    # عرض القلب كـ HTML بسيط مع محاذاة للأعلى وتناسب الحجم
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            html, body {{
                margin: 0 !important;
                padding: 0 !important;
                overflow: hidden;
                width: 100%;
                height: 100%;
            }}
            body {{
                display: flex;
                justify-content: center;
                align-items: flex-start;
                padding-top: 0 !important;
            }}
            svg {{
                display: block;
                margin: 0 auto;
                max-width: 100%;
                max-height: 100%;
                width: auto;
                height: auto;
            }}
        </style>
    </head>
    <body>
        {svg_content}
    </body>
    </html>
    """

    return components.html(html_content, height=height, scrolling=False)
