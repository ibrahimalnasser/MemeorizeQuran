# دليل نشر تطبيق حفّاظ القرآن
## Deployment Guide - Quran Memorization Platform

---

## ⚠️ تحذير مهم - Important Warning

**Netcup Webhosting 2000 (الاستضافة المشتركة) لا تدعم تطبيقات Streamlit**

Netcup Webhosting 2000 (shared hosting) does NOT support Streamlit applications because:
- لا تدعم العمليات المستمرة (No persistent processes)
- لا تدعم WebSocket (No WebSocket support)
- لا تسمح بربط المنافذ (No custom port binding)

---

## الحلول البديلة - Alternative Solutions

### الخيار 1: استخدام Streamlit Community Cloud (مجاني) ✅ موصى به
**FREE and EASIEST option**

#### الخطوات:

1. **رفع المشروع إلى GitHub:**
   ```bash
   cd E:\Projects\Takaful\Hafiz\QuranMemoryVersion2\QuranMemoryVersion2
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin https://github.com/YOUR_USERNAME/quran-hifz.git
   git push -u origin main
   ```

2. **التسجيل في Streamlit Cloud:**
   - اذهب إلى: https://streamlit.io/cloud
   - سجل دخول بحساب GitHub
   - اضغط "New app"
   - اختر repository الخاص بك
   - اختر `app.py` كملف رئيسي
   - اضغط Deploy

3. **الرابط النهائي:**
   سيكون: `https://YOUR_USERNAME-quran-hifz.streamlit.app`

---

### الخيار 2: الترقية إلى Netcup VPS

إذا أردت استخدام Netcup، يجب الترقية إلى VPS (مثل VPS 200 G11)

#### الخطوات على VPS:

1. **الاتصال بالخادم:**
   ```bash
   ssh root@YOUR_VPS_IP
   ```

2. **تثبيت Python:**
   ```bash
   apt update
   apt install python3 python3-pip python3-venv -y
   ```

3. **رفع الملفات:**
   ```bash
   # من جهازك المحلي
   scp -r E:\Projects\Takaful\Hafiz\QuranMemoryVersion2\QuranMemoryVersion2 root@YOUR_VPS_IP:/var/www/quran-hifz/
   ```

4. **تثبيت المتطلبات:**
   ```bash
   cd /var/www/quran-hifz/
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

5. **إنشاء Systemd Service:**
   ```bash
   nano /etc/systemd/system/quran-hifz.service
   ```

   أضف المحتوى التالي:
   ```ini
   [Unit]
   Description=Quran Hifz Streamlit App
   After=network.target

   [Service]
   Type=simple
   User=www-data
   WorkingDirectory=/var/www/quran-hifz
   Environment="PATH=/var/www/quran-hifz/venv/bin"
   ExecStart=/var/www/quran-hifz/venv/bin/streamlit run app.py --server.port=8501 --server.address=0.0.0.0
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```

   ```bash
   systemctl daemon-reload
   systemctl enable quran-hifz
   systemctl start quran-hifz
   ```

6. **إعداد Nginx كـ Reverse Proxy:**
   ```bash
   apt install nginx -y
   nano /etc/nginx/sites-available/quran-hifz
   ```

   أضف:
   ```nginx
   server {
       listen 80;
       server_name your-domain.com;

       location / {
           proxy_pass http://localhost:8501;
           proxy_http_version 1.1;
           proxy_set_header Upgrade $http_upgrade;
           proxy_set_header Connection "upgrade";
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
           proxy_read_timeout 86400;
       }
   }
   ```

   ```bash
   ln -s /etc/nginx/sites-available/quran-hifz /etc/nginx/sites-enabled/
   nginx -t
   systemctl restart nginx
   ```

7. **إعداد SSL (اختياري لكن موصى به):**
   ```bash
   apt install certbot python3-certbot-nginx -y
   certbot --nginx -d your-domain.com
   ```

---

### الخيار 3: منصات سحابية أخرى

#### Railway.app:
1. اذهب إلى: https://railway.app
2. Connect GitHub repository
3. سيكتشف `requirements.txt` تلقائياً
4. أضف متغير بيئة: `PORT=8501`
5. Deploy

#### Render.com:
1. اذهب إلى: https://render.com
2. New Web Service
3. Connect GitHub repo
4. Build command: `pip install -r requirements.txt`
5. Start command: `streamlit run app.py --server.port=$PORT --server.address=0.0.0.0`

---

## ملفات تم إنشاؤها - Created Files

✅ `requirements.txt` - Python dependencies
✅ `.streamlit/config.toml` - Streamlit configuration
✅ `runtime.txt` - Python version specification
✅ `.htaccess` - Apache config (للأمان فقط)
✅ `DEPLOYMENT_GUIDE.md` - هذا الملف

---

## إعدادات الأمان - Security Settings

### قبل النشر:

1. **حماية قاعدة البيانات:**
   - تأكد من أن `hifz.db` غير قابل للوصول من الويب
   - في `.htaccess` تم منع الوصول لملفات `.db`

2. **تغيير كلمات المرور الافتراضية:**
   - افتح `hifz.db` وغيّر كلمات المرور
   - استخدم كلمات مرور قوية

3. **إعداد النسخ الاحتياطي:**
   - جدولة نسخ احتياطي يومي لـ `hifz.db`
   - استخدم خاصية النسخ الاحتياطي في التطبيق

4. **HTTPS:**
   - استخدم SSL/TLS دائماً (Let's Encrypt مجاني)

---

## الدعم الفني - Support

إذا واجهت مشاكل:
1. تحقق من السجلات (logs)
2. تأكد من تثبيت جميع المتطلبات
3. تحقق من الأذونات على ملف `hifz.db`

---

## التوصية النهائية - Final Recommendation

**للاستضافة المجانية والسهلة: استخدم Streamlit Community Cloud** ✅

**للتحكم الكامل والأداء العالي: استخدم Netcup VPS**

**تجنب استخدام: Webhosting 2000 المشترك** ❌ (لن يعمل)
