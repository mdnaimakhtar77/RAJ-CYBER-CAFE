import os
import sqlite3
import secrets
from pathlib import Path
from urllib.parse import urlencode

import requests
from flask import Flask, request, abort, send_from_directory
from twilio.twiml.messaging_response import MessagingResponse
from twilio.request_validator import RequestValidator

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("DATABASE_PATH", ROOT / "orders.db"))
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", ROOT / "uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
SHOP = os.getenv("SHOP_NAME", "RAJ CYBER CAFE")
UPI_ID = os.getenv("UPI_ID", "mdnaim07@fam")
SHOP_ADDRESS = os.getenv("SHOP_ADDRESS", "Harishchandrapur")
SHOP_WHATSAPP = os.getenv("SHOP_WHATSAPP", "8515035840")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
VALIDATE_TWILIO_SIGNATURE = os.getenv("VALIDATE_TWILIO_SIGNATURE", "true").lower() == "true"

PRICES = {"1": 10, "3": 21, "6": 30, "10": 50}


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT UNIQUE NOT NULL,
            phone TEXT NOT NULL,
            media_path TEXT NOT NULL,
            media_type TEXT,
            quantity INTEGER,
            price INTEGER,
            payment_method TEXT,
            utr TEXT,
            status TEXT NOT NULL DEFAULT 'await_qty',
            download_token TEXT UNIQUE NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)


def get_order(phone):
    with db() as con:
        return con.execute(
            "SELECT * FROM orders WHERE phone=? AND status NOT IN ('delivered','cancelled') ORDER BY id DESC LIMIT 1",
            (phone,)
        ).fetchone()


def update_order(order_id, **fields):
    if not fields:
        return
    keys = ", ".join(f"{k}=?" for k in fields)
    values = list(fields.values()) + [order_id]
    with db() as con:
        con.execute(f"UPDATE orders SET {keys} WHERE order_id=?", values)


def twilio_signature_valid():
    if not VALIDATE_TWILIO_SIGNATURE:
        return True
    if not TWILIO_AUTH_TOKEN:
        return False
    validator = RequestValidator(TWILIO_AUTH_TOKEN)
    signature = request.headers.get("X-Twilio-Signature", "")
    return validator.validate(request.url, request.form, signature)


def download_twilio_media(media_url, destination):
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        raise RuntimeError("Twilio credentials are not configured")
    response = requests.get(
        media_url,
        auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
        timeout=30
    )
    response.raise_for_status()
    destination.write_bytes(response.content)
    return response.headers.get("Content-Type", "application/octet-stream")


def send_whatsapp(to, message):
    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM]):
        raise RuntimeError("Twilio WhatsApp sending credentials are not configured")
    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
    response = requests.post(
        url,
        auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
        data={"From": TWILIO_WHATSAPP_FROM, "To": to, "Body": message},
        timeout=30
    )
    response.raise_for_status()


@app.get("/")
def home():
    return (
        f"<h2>{SHOP} WhatsApp Bot</h2>"
        "<p>Bot service is running. Configure the Twilio webhook to /whatsapp.</p>"
    )


@app.post("/whatsapp")
def whatsapp():
    if not twilio_signature_valid():
        abort(403)

    phone = request.values.get("From", "").strip()
    body = request.values.get("Body", "").strip().lower()
    try:
        num_media = int(request.values.get("NumMedia", "0"))
    except ValueError:
        num_media = 0

    reply = MessagingResponse()
    msg = reply.message()

    if not phone:
        msg.body("Phone number পাওয়া যায়নি। আবার চেষ্টা করুন।")
        return str(reply)

    # Photo received: save the actual image and create a new order.
    if num_media > 0:
        media_url = request.values.get("MediaUrl0", "")
        media_type = request.values.get("MediaContentType0", "")
        if not media_url:
            msg.body("ছবি পাওয়া যায়নি। দয়া করে আবার ছবি পাঠান।")
            return str(reply)

        order_id = "RAJ" + secrets.token_hex(4).upper()
        extension = ".jpg"
        if "png" in media_type:
            extension = ".png"
        elif "pdf" in media_type:
            extension = ".pdf"
        filename = order_id + extension
        target = UPLOAD_DIR / filename

        try:
            actual_type = download_twilio_media(media_url, target)
        except Exception:
            app.logger.exception("Could not download incoming WhatsApp media")
            msg.body("ছবি ডাউনলোড করা যায়নি। একটু পরে আবার পাঠান।")
            return str(reply)

        token = secrets.token_urlsafe(24)
        with db() as con:
            con.execute(
                """INSERT INTO orders
                (order_id, phone, media_path, media_type, download_token, status)
                VALUES (?, ?, ?, ?, ?, 'await_qty')""",
                (order_id, phone, filename, actual_type or media_type, token)
            )

        msg.body(
            f"📸 ছবি পেয়েছি!\\nঅর্ডার: {order_id}\\n\\n"
            "কত কপি প্রিন্ট করবেন?\\n"
            "1 = 1 কপি = ₹10\\n"
            "3 = 3 কপি = ₹21\\n"
            "6 = 6 কপি = ₹30\\n"
            "10 = 10 কপি = ₹50\\n\\n"
            "শুধু 1 / 3 / 6 / 10 লিখে পাঠান।"
        )
        return str(reply)

    order = get_order(phone)

    if order and order["status"] == "await_qty" and body in PRICES:
        qty = int(body)
        price = PRICES[body]
        update_order(order["order_id"], quantity=qty, price=price, status="await_payment")
        msg.body(
            f"✅ {qty} কপি = ₹{price}\\n\\n"
            "পেমেন্ট কীভাবে করবেন?\\n"
            f"1 = Online UPI\\nUPI ID: {UPI_ID}\\n"
            "2 = দোকানে Cash\\n\\n"
            "1 অথবা 2 লিখে পাঠান।"
        )
        return str(reply)

    if order and order["status"] == "await_payment" and body == "1":
        amount = order["price"]
        note = order["order_id"]
        upi_link = "upi://pay?" + urlencode({
            "pa": UPI_ID, "pn": SHOP, "am": str(amount),
            "tn": note, "cu": "INR"
        })
        update_order(order["order_id"], payment_method="online", status="await_utr")
        msg.body(
            f"💳 Online payment\\nঅর্ডার: {order['order_id']}\\n"
            f"পরিমাণ: ₹{amount}\\nUPI ID: {UPI_ID}\\n\\n"
            f"UPI link: {upi_link}\\n\\n"
            "পেমেন্ট করার পরে 12-digit UTR নম্বর পাঠান। "
            "UTR পাওয়ার পর দোকান থেকে যাচাই করে নিশ্চিত করা হবে।"
        )
        return str(reply)

    if order and order["status"] == "await_payment" and body == "2":
        update_order(order["order_id"], payment_method="cash", status="cash_pending")
        msg.body(
            f"✅ Cash payment বেছে নিয়েছেন।\\nঅর্ডার: {order['order_id']}\\n"
            f"কপি: {order['quantity']}\\nমূল্য: ₹{order['price']}\\n\\n"
            f"দোকানে এসে Cash দিয়ে প্রিন্ট নিয়ে যান।\\n"
            f"{SHOP}\\n{SHOP_ADDRESS}\\nWhatsApp: {SHOP_WHATSAPP}"
        )
        return str(reply)

    if order and order["status"] == "await_utr":
        if body.isdigit() and len(body) == 12:
            update_order(order["order_id"], utr=body, status="payment_review")
            msg.body(
                f"🧾 UTR পেয়েছি: {body}\\nঅর্ডার: {order['order_id']}\\n\\n"
                "পেমেন্ট এখন যাচাই করা হচ্ছে। যাচাই সম্পূর্ণ হলে ডাউনলোড লিংক পাঠানো হবে।"
            )
        else:
            msg.body("দয়া করে সঠিক 12-digit UTR নম্বর পাঠান।")
        return str(reply)

    msg.body(
        f"🙏 {SHOP}\\n"
        "📸 Passport Photo Print Service\\n"
        "1 কপি ₹10 | 3 কপি ₹21 | 6 কপি ₹30 | 10 কপি ₹50\\n\\n"
        "অর্ডার শুরু করতে আপনার ছবি WhatsApp-এ পাঠান।"
    )
    return str(reply)


def require_admin():
    supplied = request.headers.get("X-Admin-Token", "")
    if not ADMIN_TOKEN or not secrets.compare_digest(supplied, ADMIN_TOKEN):
        abort(401)



@app.get("/admin")
def admin_dashboard():
    return send_from_directory(ROOT / "static", "admin.html")


@app.get("/admin/orders")
def admin_orders():
    require_admin()
    with db() as con:
        rows = con.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 100").fetchall()
    return {
        "orders": [
            {k: row[k] for k in row.keys() if k not in ("download_token",)}
            for row in rows
        ]
    }


@app.post("/admin/approve/<order_id>")
def approve_payment(order_id):
    require_admin()
    with db() as con:
        order = con.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)).fetchone()
    if not order:
        abort(404)
    if order["status"] != "payment_review":
        return {"error": "Order is not awaiting payment review", "status": order["status"]}, 409
    if not PUBLIC_BASE_URL:
        return {"error": "Set PUBLIC_BASE_URL in .env first"}, 500

    download_url = f"{PUBLIC_BASE_URL}/download/{order['download_token']}"
    message = (
        f"✅ RAJ CYBER CAFE: পেমেন্ট যাচাই করা হয়েছে।\\n"
        f"অর্ডার: {order_id}\\nআপনার ছবি ডাউনলোড করুন: {download_url}"
    )
    try:
        send_whatsapp(order["phone"], message)
    except Exception as exc:
        app.logger.exception("WhatsApp delivery message failed")
        return {"error": "Could not send WhatsApp message", "detail": str(exc)}, 502

    update_order(order_id, status="delivered")
    return {"ok": True, "order_id": order_id, "download_url": download_url}


@app.get("/download/<token>")
def download_photo(token):
    with db() as con:
        order = con.execute(
            "SELECT * FROM orders WHERE download_token=?", (token,)
        ).fetchone()
    if not order or order["status"] != "delivered":
        abort(404)
    return send_from_directory(
        UPLOAD_DIR, order["media_path"], as_attachment=True
    )


@app.get("/health")
def health():
    return {"ok": True}


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
