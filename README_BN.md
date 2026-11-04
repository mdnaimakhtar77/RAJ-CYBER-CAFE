# RAJ CYBER CAFE — WhatsApp Photo Order Bot

এই starter project-এ রয়েছে:
- WhatsApp-এ ছবি এলে Twilio থেকে আসল media download করে server-এ save
- 1 / 3 / 6 / 10 কপির অর্ডার ও দাম
- UPI payment link অথবা দোকানে cash
- UTR সংগ্রহ করে admin review-তে রাখা
- Admin payment approve করলে WhatsApp-এ secure photo download link পাঠানো
- SQLite database-এ order সংরক্ষণ

## গুরুত্বপূর্ণ নিরাপত্তা ও পেমেন্ট নোট
**শুধু 12-digit UTR পেলেই payment verified হয় না।** এই bot UTR-কে `payment_review` অবস্থায় রাখে। আপনার bank/UPI merchant statement দেখে admin-কে payment নিশ্চিত করতে হবে। তারপরই download link যাবে। Automatic verification চাইলে payment gateway-এর verified webhook (যেমন Razorpay/অনুমোদিত provider) integrate করতে হবে।

## 1) Twilio প্রস্তুত করুন
1. Twilio account খুলুন এবং WhatsApp Sandbox বা অনুমোদিত WhatsApp sender চালু করুন।
2. Twilio Console থেকে Account SID ও Auth Token নিন।
3. Sandbox ব্যবহার করলে Twilio-র নির্দেশ অনুযায়ী নিজের WhatsApp নম্বর sandbox-এ join করুন।
4. App-টি public HTTPS hosting-এ deploy করুন। Localhost URL Twilio webhook হিসেবে কাজ করবে না।

## 2) Install
Python 3.10+ লাগবে।

```bash
python -m venv venv
# Windows:
venv\\Scripts\\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements-prod.txt
```

`.env.example` কপি করে `.env` বানান এবং সব credential বসান। `.env` কখনো কাউকে দেবেন না বা GitHub-এ upload করবেন না। Hosting platform-এর Environment Variables-এ এগুলো সেট করাই ভালো।

Local run:
```bash
python app.py
```

Production:
```bash
gunicorn app:app
```

## 3) Twilio webhook
Twilio Console → WhatsApp Sandbox / Sender → **When a message comes in**:
`https://YOUR-DOMAIN/whatsapp`
Method: `POST`

`PUBLIC_BASE_URL`-এ একই public HTTPS base URL দিন, শেষে slash দেবেন না।

## 4) Admin: orders দেখা
```bash
curl -H "X-Admin-Token: YOUR_ADMIN_TOKEN" https://YOUR-DOMAIN/admin/orders
```

## 5) UTR যাচাই করে order approve
প্রথমে bank/UPI statement-এ amount, date, reference মিলিয়ে payment সত্যি এসেছে কি না যাচাই করুন। তারপর:
```bash
curl -X POST -H "X-Admin-Token: YOUR_ADMIN_TOKEN" https://YOUR-DOMAIN/admin/approve/RAJXXXXXXXX
```
এতে WhatsApp-এ download link পাঠানো হবে। ভুল order approve করবেন না।

## 6) Production-এ যাওয়ার আগে
- Hosting-এ persistent disk/volume যুক্ত করুন; `uploads/` এবং SQLite database ephemeral filesystem-এ রাখবেন না।
- HTTPS বাধ্যতামূলক রাখুন।
- Admin token লম্বা ও random রাখুন; কাউকে দেবেন না।
- Privacy/retention policy ঠিক করুন; গ্রাহকের ছবি প্রয়োজনের বেশি দিন রাখবেন না।
- WhatsApp template/24-hour customer service window এবং opt-in নিয়ম Twilio/Meta-র বর্তমান নীতিমালা অনুযায়ী মানুন।
- Passport/ID ছবি সংবেদনশীল হতে পারে—অ্যাক্সেস সীমিত রাখুন এবং কাজ শেষে মুছে দিন।

## বর্তমান সীমাবদ্ধতা
- প্রথম media attachment-টি handle করে।
- Cash order-এ customer shop-এ গিয়ে payment/print নেবে; admin print workflow নেই।
- UPI payment auto-confirm করে না।
- এটা starter implementation; deploy ও live test না করা পর্যন্ত bot চালু হয়েছে বলা যাবে না।


## Admin Dashboard
Deploy করার পর `https://YOUR-DOMAIN/admin` খুলুন। `ADMIN_TOKEN` দিয়ে login করুন। Dashboard থেকে order দেখা যাবে এবং bank/UPI statement-এ payment যাচাই করার পর `Verify & Send Photo` চাপলে গ্রাহককে download link পাঠানো হবে।
