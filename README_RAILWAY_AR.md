# بوت Talkin Chat — Railway Music + Gifts

## متغيرات Railway المطلوبة
أضف هذه القيم من صفحة الخدمة في Railway عبر **Variables**، ثم نفّذ Redeploy:

```text
BOT_ID=اسم البوت
BOT_PWD=كلمة السر
BOT_MASTER=اسم الماستر
GROUP_TO_JOIN=أول غرفة يدخلها البوت
```

يدعم الإصدار الحالي أيضًا الأسماء القديمة `BOT_USERNAME` و`BOT_PASSWORD` و`FIRST_ROOM`،
لكن يُفضّل استخدام الأسماء الأربعة أعلاه. لا تضع كلمات السر داخل Git أو داخل Dockerfile.

لا تضع روابط الأغاني أو الهدايا. البوت يستخدم Railway Public Domain تلقائياً.

## أوامر
اغنية اسم الأغنية
تشغيل اسم الأغنية
music اسم الأغنية
gv — قائمة الهدايا
gv@رقم@اسم_المستخدم

فعّل Public Networking في Railway. ملفات الصوت والصور تُخدم من نفس الخدمة.
