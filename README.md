# منصة حفّاظ القرآن 📖
## Quran Memorization Platform

نظام إدارة شامل لمدارس تحفيظ القرآن الكريم مبني على Streamlit

A comprehensive management system for Quran memorization schools built with Streamlit.

---

## المميزات - Features

- 🏫 **إدارة متعددة المدارس** - Multi-school management
- 👥 **إدارة المستخدمين** - User management (Super Admin, School Admin, Teachers, Students, Visitors)
- 📊 **لوحات تحكم وإحصاءات** - Dashboards and analytics
- 📋 **تتبع الحفظ** - Memorization tracking
- 👨‍🏫 **إدارة المعلمين والمجموعات** - Teachers and groups management
- 📈 **تقارير مفصلة** - Detailed reports
- 💾 **نسخ احتياطي** - Backup system
- ⬆️⬇️ **استيراد/تصدير** - Import/Export functionality

---

## التثبيت المحلي - Local Installation

### المتطلبات:
- Python 3.8 أو أحدث

### الخطوات:

1. **استنساخ المشروع:**
   ```bash
   git clone <repository-url>
   cd QuranMemoryVersion2
   ```

2. **تثبيت المتطلبات:**
   ```bash
   pip install -r requirements.txt
   ```

3. **تشغيل التطبيق:**
   ```bash
   streamlit run app.py
   ```

4. **فتح المتصفح:**
   افتح: `http://localhost:8501`

---

## النشر - Deployment

راجع ملف [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) للتفاصيل الكاملة.

**تحذير:** هذا التطبيق يتطلب VPS أو استضافة سحابية. لا يعمل على الاستضافة المشتركة.

---

## البنية - Structure

```
QuranMemoryVersion2/
├── app.py                  # نقطة الدخول الرئيسية
├── core/                   # الوحدات الأساسية
│   ├── db.py              # قاعدة البيانات
│   └── models.py          # نماذج البيانات
├── ui/                     # واجهة المستخدم
│   ├── pages.py           # الصفحات
│   └── heart.py           # عناصر UI
├── style_islamic.css       # التنسيقات
├── hifz.db                # قاعدة البيانات
└── page_ayah_map.csv      # خريطة الصفحات والآيات
```

---

## بيانات الدخول الافتراضية - Default Credentials

⚠️ **مهم: غيّر هذه البيانات بعد أول تسجيل دخول!**

- Super Admin: `admin` / `admin`

---

## الأمان - Security

- ✅ تشفير كلمات المرور
- ✅ أدوار وصلاحيات مختلفة
- ✅ حماية قاعدة البيانات
- ✅ نسخ احتياطي تلقائي

**قبل النشر:**
1. غيّر كلمات المرور الافتراضية
2. فعّل HTTPS
3. راجع إعدادات الأمان في `.htaccess`

---

## الترخيص - License

هذا المشروع مفتوح المصدر للاستخدام التعليمي والخيري.

---

## الدعم - Support

للمشاكل والاستفسارات، يرجى فتح Issue في GitHub.

---

## التحديثات المستقبلية - Future Updates

- [ ] إشعارات البريد الإلكتروني
- [ ] تطبيق الجوال
- [ ] تكامل مع Telegram Bot
- [ ] تصدير إلى PDF
- [ ] لوحة تحكم الأهالي

---

**صنع بـ ❤️ لخدمة القرآن الكريم**
