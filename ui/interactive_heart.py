# -*- coding: utf-8 -*-
"""
ui/interactive_heart.py
-----------------------
مكون تفاعلي للقلب يستخدم st.components.v1.html للتواصل ثنائي الاتجاه
"""

import streamlit.components.v1 as components


def render_interactive_heart(svg_content: str, height: int = 600) -> dict:
    """
    يعرض القلب كمكون تفاعلي يرسل أحداث النقر إلى Streamlit بدون إعادة تحميل الصفحة.

    Args:
        svg_content: محتوى SVG الذي تم إنشاؤه بواسطة make_heart_svg
        height: ارتفاع المكون بالبكسل

    Returns:
        dict: معلومات النقر (mode, seg) أو None
    """

    # إضافة JavaScript للتواصل مع Streamlit
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ margin: 0; padding: 0; overflow: hidden; }}
        </style>
    </head>
    <body>
        {svg_content}
        <script>
            // التعامل مع نقرات قطاعات القلب
            document.addEventListener('click', function(event) {{
                const target = event.target.closest('.heart-segment');
                if (target) {{
                    const mode = target.getAttribute('data-mode');
                    const seg = target.getAttribute('data-seg');
                    if (mode && seg) {{
                        // إرسال البيانات إلى Streamlit
                        window.parent.postMessage({{
                            type: 'streamlit:setComponentValue',
                            data: {{ mode: mode, seg: parseInt(seg) }}
                        }}, '*');
                    }}
                }}
            }});
        </script>
    </body>
    </html>
    """

    return components.html(html_content, height=height, scrolling=False)
