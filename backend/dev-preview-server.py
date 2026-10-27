#!/usr/bin/env python3
"""Development-only Codespaces server: frontend + persistent SQLite API.
Not the production Ghestine/SQL Server backend. No real SMS, OCR, or bank inquiry.
"""
from __future__ import annotations
import argparse, base64, hashlib, hmac, json, os, re, secrets, sqlite3, sys, time, traceback, uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from getpass import getpass
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
DATA_DIR = Path(os.environ.get("DIGIBILEPAY_DATA_DIR", ROOT / "data")).resolve()
DB_PATH = Path(os.environ.get("DIGIBILEPAY_DB_PATH", DATA_DIR / "digibilepay-preview.sqlite3")).resolve()
OTP_TTL, CAPTCHA_TTL, TICKET_TTL = 120, 300, 900
# Deliberately fixed only in this development-preview server; never use for production.
DEV_FIXED_OTP = "123456"
ROLES = ("SuperAdmin", "Admin", "Customer", "Merchant", "Agent")
ROLE_CLAIM = "http://schemas.microsoft.com/ws/2008/06/identity/claims/role"

class ApiError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message
        super().__init__(message)

@contextmanager
def connect_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=15000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def now(): return int(time.time())
def iso_now(): return datetime.now(timezone.utc).isoformat()
def b64url(raw): return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
def json64(obj): return b64url(json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))

def normalize_digits(value):
    text = str(value or "")
    fa, ar = "۰۱۲۳۴۵۶۷۸۹", "٠١٢٣٤٥٦٧٨٩"
    return "".join(str(fa.index(c)) if c in fa else str(ar.index(c)) if c in ar else c for c in text)

def normalize_phone(value):
    phone = re.sub(r"[\s()\-]", "", normalize_digits(value))
    if phone.startswith("+98"): phone = "0" + phone[3:]
    elif phone.startswith("0098"): phone = "0" + phone[4:]
    elif phone.startswith("98") and len(phone) == 12: phone = "0" + phone[2:]
    return phone if re.fullmatch(r"09\d{9}", phone) else ""

def password_hash(password, rounds=240_000):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    return "pbkdf2_sha256:{}:{}:{}".format(rounds, salt.hex(), digest.hex())

def password_ok(password, stored):
    try:
        algo, rounds, salt_hex, digest_hex = stored.split(":", 3)
        if algo != "pbkdf2_sha256": return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(rounds))
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False

def app_secret():
    with connect_db() as c:
        row = c.execute("SELECT value FROM app_settings WHERE key='jwt_secret'").fetchone()
        if row: return row["value"].encode()
        value = secrets.token_hex(48)
        c.execute("INSERT INTO app_settings(key,value) VALUES('jwt_secret',?)", (value,))
        return value.encode()

def digest(value):
    return hmac.new(app_secret(), str(value).encode("utf-8"), hashlib.sha256).hexdigest()

def issue_token(user):
    timestamp = now()
    roles = [user["role"]] + (["Admin"] if user["role"] == "SuperAdmin" else [])
    payload = {"sub": user["id"], "name": user["full_name"], "fullName": user["full_name"],
               "role": user["role"], "roles": roles, ROLE_CLAIM: roles,
               "iat": timestamp, "exp": timestamp + 7200,
               "iss": "digibilepay-codespaces-dev", "aud": "digibilepay-codespaces-dev"}
    unsigned = json64({"alg": "HS256", "typ": "JWT"}) + "." + json64(payload)
    return unsigned + "." + b64url(hmac.new(app_secret(), unsigned.encode("ascii"), hashlib.sha256).digest())

def auth_user(handler):
    header = handler.headers.get("Authorization", "")
    if not header.lower().startswith("bearer "): raise ApiError(401, "ابتدا وارد شوید.")
    try:
        first, middle, signature = header[7:].strip().split(".")
        unsigned = first + "." + middle
        expected = b64url(hmac.new(app_secret(), unsigned.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(expected, signature): raise ValueError()
        payload = json.loads(base64.urlsafe_b64decode(middle + "=" * (-len(middle) % 4)))
        if int(payload.get("exp", 0)) <= now(): raise ValueError()
    except Exception:
        raise ApiError(401, "نشست معتبر نیست یا منقضی شده است.")
    with connect_db() as c:
        user = c.execute("SELECT * FROM app_users WHERE id=? AND is_active=1", (payload.get("sub"),)).fetchone()
    if not user: raise ApiError(401, "حساب فعال پیدا نشد.")
    return user

def require_admin(handler):
    user = auth_user(handler)
    if user["role"] not in ("Admin", "SuperAdmin"): raise ApiError(403, "این بخش فقط برای مدیران است.")
    return user

def safe_user(user):
    return {"id": user["id"], "fullName": user["full_name"], "name": user["full_name"],
            "phoneNumber": user["phone"], "email": user["email"], "nationalCode": user["national_code"],
            "role": user["role"], "roles": [user["role"]], "isActive": bool(user["is_active"]),
            "mustChangePassword": bool(user["must_change_password"]), "createdAt": user["created_at"]}

def add_user(conn, full_name, phone, stored_hash, role="Customer", email=None, national_code=None):
    if role not in ROLES: raise ApiError(400, "نقش کاربر معتبر نیست.")
    if not full_name.strip(): raise ApiError(400, "نام و نام خانوادگی الزامی است.")
    if not phone: raise ApiError(400, "شماره موبایل معتبر نیست.")
    if conn.execute("SELECT 1 FROM app_users WHERE phone=?", (phone,)).fetchone():
        raise ApiError(409, "کاربری با این شماره از قبل ثبت شده است.")
    uid = str(uuid.uuid4())
    conn.execute("""INSERT INTO app_users(id,full_name,phone,email,national_code,password_hash,role,is_active,must_change_password,created_at)
                    VALUES(?,?,?,?,?,?,?,1,0,?)""",
                 (uid, full_name.strip(), phone, (email or "").strip() or None,
                  (national_code or "").strip() or None, stored_hash, role, iso_now()))
    return conn.execute("SELECT * FROM app_users WHERE id=?", (uid,)).fetchone()

def find_user(conn, login):
    return conn.execute("SELECT * FROM app_users WHERE phone=? OR lower(email)=lower(?) LIMIT 1",
                        (normalize_phone(login) or login.strip(), login.strip())).fetchone()

def seed_products(conn):
    items = [
        ("beta", "طرح بتا بانک رفاه", "beta",
         "طرح آزمایشی استعلام تسهیلات بانک رفاه؛ در محیط پیش‌نمایش، استعلام واقعی بانک وصل نیست.",
         "جدید", 0, 0, 30, [],
         {"kind":"beta","steps":["عضویت و تأیید موبایل","ثبت کد ملی و رضایت استعلام","استعلام مبلغ و جدول اقساط از بانک","بارگذاری مدارک و بررسی کارشناس"],
          "minAge":18,"maxAge":70,"minIncome":0,"kyc":1,"minScore":0,"maxActive":1},
         [{"name":"کارت ملی","required":True},{"name":"مدارک تعیین‌شده توسط طرح","required":True}], 0),
        ("p3", "اقساط ۳ ماهه", "p3", "برای خریدهای کوچک و روزمره", "بدون پیش‌پرداخت", 1000000, 20000000, 30,
         [{"months":3,"feePercent":2,"downPaymentPercent":0}],
         {"minAge":22,"maxAge":60,"minIncome":6,"kyc":1,"minScore":50,"maxActive":3},
         [{"name":"کارت ملی","required":True},{"name":"شناسنامه","required":True}], 1),
        ("p6", "اقساط ۶ ماهه", "p6", "متعادل‌ترین انتخاب برای موبایل و لوازم خانگی", "پرطرفدار", 1000000, 30000000, 30,
         [{"months":4,"feePercent":2.3,"downPaymentPercent":5},{"months":6,"feePercent":2.5,"downPaymentPercent":10}],
         {"minAge":22,"maxAge":60,"minIncome":6,"kyc":1,"minScore":50,"maxActive":3},
         [{"name":"کارت ملی","required":True},{"name":"شناسنامه","required":True},{"name":"فیش حقوقی","required":True},{"name":"گواهی اشتغال","required":False}], 2),
        ("p9", "اقساط ۹ ماهه", "p9", "برای خریدهای بزرگ‌تر با قسط سبک‌تر", "", 3000000, 40000000, 30,
         [{"months":9,"feePercent":2.5,"downPaymentPercent":15}],
         {"minAge":22,"maxAge":60,"minIncome":8,"kyc":1,"minScore":55,"maxActive":2},
         [{"name":"کارت ملی","required":True},{"name":"شناسنامه","required":True},{"name":"فیش حقوقی","required":True},{"name":"گواهی اشتغال","required":True}], 3),
    ]
    for x in items:
        conn.execute("""INSERT OR IGNORE INTO loan_products
            (id,name,slug,description,badge,min_amount,max_amount,interval_days,tiers_json,conditions_json,documents_json,is_active,sort_order,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (x[0],x[1],x[2],x[3],x[4],x[5],x[6],x[7],json.dumps(x[8],ensure_ascii=False),
             json.dumps(x[9],ensure_ascii=False),json.dumps(x[10],ensure_ascii=False),1,x[11],iso_now()))

def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with connect_db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS app_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS tenants(id TEXT PRIMARY KEY,domain TEXT NOT NULL UNIQUE,name TEXT NOT NULL,brand_primary TEXT NOT NULL,brand_accent TEXT NOT NULL,logo_text TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS app_users(id TEXT PRIMARY KEY,full_name TEXT NOT NULL,phone TEXT NOT NULL UNIQUE,email TEXT,national_code TEXT,password_hash TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN ('SuperAdmin','Admin','Customer','Merchant','Agent')),is_active INTEGER NOT NULL DEFAULT 1,must_change_password INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS loan_products(id TEXT PRIMARY KEY,name TEXT NOT NULL,slug TEXT NOT NULL UNIQUE,description TEXT NOT NULL DEFAULT '',badge TEXT NOT NULL DEFAULT '',min_amount INTEGER NOT NULL DEFAULT 1000000,max_amount INTEGER NOT NULL DEFAULT 20000000,interval_days INTEGER NOT NULL DEFAULT 30,tiers_json TEXT NOT NULL DEFAULT '[]',conditions_json TEXT NOT NULL DEFAULT '{}',documents_json TEXT NOT NULL DEFAULT '[]',is_active INTEGER NOT NULL DEFAULT 1,sort_order INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS captchas(id TEXT PRIMARY KEY,answer_hash TEXT NOT NULL,expires_at INTEGER NOT NULL,attempts INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS otp_challenges(phone TEXT NOT NULL,purpose TEXT NOT NULL,code_hash TEXT NOT NULL,pending_json TEXT,created_at INTEGER NOT NULL,expires_at INTEGER NOT NULL,resend_at INTEGER NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(phone,purpose));
        CREATE TABLE IF NOT EXISTS otp_tickets(ticket TEXT PRIMARY KEY,phone TEXT NOT NULL,expires_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS beta_inquiries(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,national_code TEXT NOT NULL,consent INTEGER NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS preview_records(
            resource TEXT NOT NULL,id TEXT NOT NULL,data_json TEXT NOT NULL,
            created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
            PRIMARY KEY(resource,id));
        CREATE INDEX IF NOT EXISTS ix_preview_records_resource_updated
            ON preview_records(resource,updated_at DESC);
        CREATE TABLE IF NOT EXISTS preview_audit(
            id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, actor_id TEXT NOT NULL,
            action TEXT NOT NULL, entity TEXT NOT NULL, entity_id TEXT NOT NULL,
            detail_json TEXT NOT NULL, prev_hash TEXT NOT NULL, entry_hash TEXT NOT NULL);
        """)
        if not c.execute("SELECT 1 FROM tenants LIMIT 1").fetchone():
            c.execute("INSERT INTO tenants VALUES(?,?,?,?,?,?)",("default","localhost","دیجی‌بایل پی","#3b1f6b","#f5a400","د"))
        if not c.execute("SELECT 1 FROM app_settings WHERE key='jwt_secret'").fetchone():
            c.execute("INSERT INTO app_settings(key,value) VALUES('jwt_secret',?)",(secrets.token_hex(48),))
        seed_products(c)

def product_json(row):
    conditions = json.loads(row["conditions_json"])
    return {"id":row["id"],"code":row["slug"],"slug":row["slug"],"name":row["name"],"title":row["name"],
            "description":row["description"],"badge":row["badge"],"minAmount":row["min_amount"],
            "maxAmount":row["max_amount"],"intervalDays":row["interval_days"],"tiers":json.loads(row["tiers_json"]),
            "conditions":conditions,"kind":conditions.get("kind",""),"steps":conditions.get("steps",[]),
            "documents":json.loads(row["documents_json"]),
            "isActive":bool(row["is_active"]),"sortOrder":row["sort_order"]}

def read_json(handler):
    try: length = int(handler.headers.get("Content-Length","0"))
    except ValueError: raise ApiError(400,"طول درخواست معتبر نیست.")
    if length > 1_000_000: raise ApiError(413,"اندازه درخواست بیش از حد مجاز است.")
    try:
        value = json.loads(handler.rfile.read(length).decode("utf-8") if length else "{}")
        if not isinstance(value,(dict,list)): raise ValueError()
        return value
    except (UnicodeDecodeError,json.JSONDecodeError,ValueError):
        raise ApiError(400,"بدنه درخواست باید JSON معتبر باشد.")

def validate_captcha(cid, answer):
    if not cid or not answer: return False
    with connect_db() as c:
        row = c.execute("SELECT * FROM captchas WHERE id=?",(cid,)).fetchone()
        if not row or row["expires_at"] < now() or row["attempts"] >= 5:
            if row: c.execute("DELETE FROM captchas WHERE id=?",(cid,))
            return False
        if hmac.compare_digest(row["answer_hash"],digest(normalize_digits(answer).strip())):
            c.execute("DELETE FROM captchas WHERE id=?",(cid,))
            return True
        c.execute("UPDATE captchas SET attempts=attempts+1 WHERE id=?",(cid,))
        return False

def create_captcha():
    cid, answer = secrets.token_urlsafe(18), str(secrets.randbelow(90000)+10000)
    with connect_db() as c:
        c.execute("INSERT INTO captchas(id,answer_hash,expires_at) VALUES(?,?,?)",(cid,digest(answer),now()+CAPTCHA_TTL))
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="170" height="56" viewBox="0 0 170 56">'
           '<rect width="170" height="56" rx="12" fill="#241047"/>'
           '<path d="M8 12 L160 42 M4 43 L155 8" stroke="#9c80c8" stroke-width="1" opacity=".5"/>'
           '<text x="20" y="38" font-family="monospace" font-size="30" fill="#ffffff" letter-spacing="6">'+answer+"</text></svg>")
    return {"id":cid,"image":"data:image/svg+xml;charset=utf-8,"+quote(svg,safe="")}

def create_otp(phone,purpose,pending=None):
    code, timestamp = DEV_FIXED_OTP, now()
    pending_json = json.dumps(pending,ensure_ascii=False) if pending else None
    with connect_db() as c:
        old = c.execute("SELECT resend_at FROM otp_challenges WHERE phone=? AND purpose=?",(phone,purpose)).fetchone()
        if old and old["resend_at"] > timestamp: raise ApiError(429,"برای ارسال دوباره کد کمی صبر کنید.")
        c.execute("""INSERT INTO otp_challenges(phone,purpose,code_hash,pending_json,created_at,expires_at,resend_at,attempts)
          VALUES(?,?,?,?,?,?,?,0) ON CONFLICT(phone,purpose) DO UPDATE SET code_hash=excluded.code_hash,pending_json=excluded.pending_json,created_at=excluded.created_at,expires_at=excluded.expires_at,resend_at=excluded.resend_at,attempts=0""",
          (phone,purpose,digest(code),pending_json,timestamp,timestamp+OTP_TTL,timestamp+60))
    print("[DEV ONLY] OTP purpose={} phone=***{} code={}".format(purpose,phone[-4:],code),flush=True)
    return {"ok":True,"message":"کد توسعه در ترمینال Codespaces چاپ شد.","expiresIn":OTP_TTL,"resendIn":60}

def verify_otp(phone,purpose,code):
    invalid = False
    with connect_db() as c:
        row = c.execute("SELECT * FROM otp_challenges WHERE phone=? AND purpose=?",(phone,purpose)).fetchone()
        if not row or row["expires_at"] < now(): raise ApiError(400,"کد تأیید وجود ندارد یا منقضی شده است.")
        if row["attempts"] >= 5: raise ApiError(429,"تعداد تلاش مجاز تمام شده است.")
        # The development preview deliberately accepts the documented fixed test OTP.
        # Keep all normal challenge checks above (matching phone/purpose, expiry, attempt limit).
        supplied = normalize_digits(code).strip()
        if not (hmac.compare_digest(row["code_hash"],digest(supplied))
                or hmac.compare_digest(supplied,DEV_FIXED_OTP)):
            c.execute("UPDATE otp_challenges SET attempts=attempts+1 WHERE phone=? AND purpose=?",(phone,purpose))
            invalid = True
    # Raise after the transaction commits so a failed attempt is counted.
    if invalid: raise ApiError(400,"کد تأیید نادرست است.")
    return row

def create_ticket(phone):
    ticket = secrets.token_urlsafe(36)
    with connect_db() as c: c.execute("INSERT INTO otp_tickets VALUES(?,?,?)",(ticket,phone,now()+TICKET_TTL))
    return ticket

def read_multipart(handler):
    try: length = int(handler.headers.get("Content-Length","0"))
    except ValueError: raise ApiError(400,"طول درخواست معتبر نیست.")
    if length > 7_000_000: raise ApiError(413,"اندازه فایل بیش از حد مجاز است.")
    content_type = handler.headers.get("Content-Type","")
    match = re.search(r'boundary=(?:"([^"]+)"|([^;]+))',content_type,re.I)
    if not match: raise ApiError(400,"فرمت بارگذاری فایل معتبر نیست.")
    boundary = (match.group(1) or match.group(2)).strip().encode()
    raw = handler.rfile.read(length) if length else b""
    result = {}
    for part in raw.split(b"--"+boundary):
        part = part.strip(b"\r\n-")
        if not part or b"\r\n\r\n" not in part: continue
        head, data = part.split(b"\r\n\r\n",1)
        disp = re.search(br'content-disposition:\s*form-data;\s*name="([^"]+)"(?:;\s*filename="([^"]*)")?',head,re.I)
        if not disp: continue
        name = disp.group(1).decode("utf-8","replace")
        filename = disp.group(2).decode("utf-8","replace") if disp.group(2) is not None else None
        data = data.rstrip(b"\r\n")
        if filename is None:
            result[name] = data.decode("utf-8","replace")
        else:
            if len(data) > 6_000_000: raise ApiError(413,"حجم هر فایل حداکثر ۶ مگابایت است.")
            ct = re.search(br'content-type:\s*([^\r\n]+)',head,re.I)
            media = ct.group(1).decode("ascii","replace").strip() if ct else "application/octet-stream"
            result[name] = {"filename":Path(filename).name[:180],"contentType":media,
                            "size":len(data),"contentBase64":base64.b64encode(data).decode("ascii")}
    return result

def read_request_body(handler):
    if handler.headers.get("Content-Type","").lower().startswith("multipart/form-data"):
        return read_multipart(handler)
    return read_json(handler)

def record_list(resource):
    with connect_db() as c:
        rows=c.execute("SELECT data_json FROM preview_records WHERE resource=? ORDER BY updated_at DESC,id",(resource,)).fetchall()
    result=[]
    for row in rows:
        try: result.append(json.loads(row["data_json"]))
        except json.JSONDecodeError: continue
    return result

def record_get(resource, ident):
    with connect_db() as c:
        row=c.execute("SELECT data_json FROM preview_records WHERE resource=? AND id=?",(resource,str(ident))).fetchone()
    if not row: return None
    try: return json.loads(row["data_json"])
    except json.JSONDecodeError: return None

def audit_preview(actor_id, action, entity, entity_id="", detail=None):
    event={"at":iso_now(),"actorId":str(actor_id or "preview-system"),"action":str(action),
           "entity":str(entity),"entityId":str(entity_id),"detail":detail or {}}
    encoded=json.dumps(event,ensure_ascii=False,sort_keys=True,separators=(",",":"))
    with connect_db() as c:
        prev=c.execute("SELECT entry_hash FROM preview_audit ORDER BY id DESC LIMIT 1").fetchone()
        prev_hash=prev["entry_hash"] if prev else "0"*64
        entry_hash=hashlib.sha256((prev_hash+encoded).encode("utf-8")).hexdigest()
        c.execute("""INSERT INTO preview_audit(at,actor_id,action,entity,entity_id,detail_json,prev_hash,entry_hash)
          VALUES(?,?,?,?,?,?,?,?)""",(event["at"],event["actorId"],event["action"],event["entity"],
          event["entityId"],json.dumps(event["detail"],ensure_ascii=False),prev_hash,entry_hash))

def save_record(resource, body, ident=None, actor_id="preview-system", action="save"):
    if not isinstance(body,dict): raise ApiError(400,"بدنه باید یک شیء JSON باشد.")
    record_id=str(ident or body.get("id") or uuid.uuid4())
    current=record_get(resource,record_id) or {}
    data=dict(current); data.update(body); data["id"]=record_id
    data.setdefault("createdAt",iso_now()); data["updatedAt"]=iso_now()
    encoded=json.dumps(data,ensure_ascii=False,separators=(",",":"))
    with connect_db() as c:
        c.execute("""INSERT INTO preview_records(resource,id,data_json,created_at,updated_at) VALUES(?,?,?,?,?)
          ON CONFLICT(resource,id) DO UPDATE SET data_json=excluded.data_json,updated_at=excluded.updated_at""",
          (resource,record_id,encoded,data["createdAt"],data["updatedAt"]))
    audit_preview(actor_id,action,resource,record_id,{"keys":sorted(k for k in body if k not in ("fileData","contentBase64"))})
    return data

def delete_record(resource, ident, actor_id="preview-system"):
    existed=record_get(resource,ident)
    if existed is None: raise ApiError(404,"رکورد پیدا نشد.")
    with connect_db() as c: c.execute("DELETE FROM preview_records WHERE resource=? AND id=?",(resource,str(ident)))
    audit_preview(actor_id,"delete",resource,ident,{})
    return True

def public_record(item):
    if item is None: return None
    return {k:v for k,v in item.items() if k not in ("fileData","contentBase64")}

def user_can_read(user, item):
    owner=str(item.get("userId") or item.get("user_id") or "")
    return not owner or owner in (str(user["id"]),str(user["phone"]))

def preview_admin_get(handler, path, query):
    user=require_admin(handler)
    p=path.lower()
    if p=="/api/v1/admin/app-settings":
        with connect_db() as c: rows=c.execute("SELECT key,value FROM app_settings WHERE key!='jwt_secret' ORDER BY key").fetchall()
        return {r["key"]:r["value"] for r in rows}
    if p=="/api/v1/admin/audit/verify":
        with connect_db() as c: rows=c.execute("SELECT * FROM preview_audit ORDER BY id").fetchall()
        previous="0"*64
        for row in rows:
            event={"at":row["at"],"actorId":row["actor_id"],"action":row["action"],"entity":row["entity"],
                   "entityId":row["entity_id"],"detail":json.loads(row["detail_json"] or "{}")}
            encoded=json.dumps(event,ensure_ascii=False,sort_keys=True,separators=(",",":"))
            expected=hashlib.sha256((previous+encoded).encode("utf-8")).hexdigest()
            if row["prev_hash"]!=previous or row["entry_hash"]!=expected:
                return {"ok":False,"checkedCount":row["id"]-1,"brokenAt":row["id"]}
            previous=row["entry_hash"]
        return {"ok":True,"checkedCount":len(rows)}
    if p=="/api/v1/admin/audit":
        take=max(1,min(500,int((query.get("take") or ["200"])[0] or 200)))
        with connect_db() as c: rows=c.execute("SELECT * FROM preview_audit ORDER BY id DESC LIMIT ?",(take,)).fetchall()
        return {"data":[{"id":r["id"],"at":r["at"],"actorId":r["actor_id"],"action":r["action"],
                "entity":r["entity"],"entityId":r["entity_id"],"detail":json.loads(r["detail_json"] or "{}"),
                "hash":r["entry_hash"]} for r in rows]}
    if p=="/api/v1/admin/ledger/trial-balance":
        accounts=record_list("ledger-accounts")
        entries=record_list("ledger-entries")
        balances=[]
        for account in accounts:
            debit=credit=0
            for entry in entries:
                for line in entry.get("lines",[]) or []:
                    if str(line.get("accountId"))==str(account.get("id")) or str(line.get("accountId"))==str(account.get("code")):
                        debit+=int(line.get("debit") or 0); credit+=int(line.get("credit") or 0)
            balances.append({"accountId":account.get("id"),"code":account.get("code"),"name":account.get("name"),
                             "debit":debit,"credit":credit,"balance":debit-credit})
        return {"data":balances}
    if p=="/api/v1/admin/loan-products/labels":
        with connect_db() as c: rows=c.execute("SELECT id,name,slug FROM loan_products ORDER BY sort_order,name").fetchall()
        return {"data":[{"id":r["id"],"value":r["id"],"name":r["name"],"label":r["name"],"slug":r["slug"]} for r in rows]}
    match=re.fullmatch(r"/api/v1/admin/loan-products/([^/]+)/contracts",path,re.I)
    if match:
        item=record_get("loan-product-contracts",match.group(1))
        return {"data":(item or {}).get("rows",[])}
    match=re.fullmatch(r"/api/v1/admin/virtual-cards/([^/]+)/transactions",path,re.I)
    if match: return {"data":record_list("card-transactions:"+match.group(1))}
    match=re.fullmatch(r"/api/v1/admin/contracts/([^/]+)/html",path,re.I)
    if match:
        item=record_get("contracts",match.group(1))
        if not item: raise ApiError(404,"قرارداد پیدا نشد.")
        return str(item.get("html") or ("<h1>"+str(item.get("title") or item.get("number") or "قرارداد")+"</h1><p>این متن فقط رکورد پیش‌نمایش است و نسخه قانونی امضاشده محسوب نمی‌شود.</p>"))
    match=re.fullmatch(r"/api/v1/admin/contracts/([^/]+)/events",path,re.I)
    if match:
        item=record_get("contracts",match.group(1))
        if not item: raise ApiError(404,"قرارداد پیدا نشد.")
        return {"data":item.get("events",[])}
    match=re.fullmatch(r"/api/v1/admin/backups/([^/]+)",path,re.I)
    if match:
        item=record_get("backups",match.group(1))
        if not item: raise ApiError(404,"نسخه پشتیبان پیدا نشد.")
        return json.dumps(item.get("snapshot",{}),ensure_ascii=False,indent=2).encode("utf-8")
    match=re.fullmatch(r"/api/v1/admin/(contract-templates|contract-variables|contracts|counterparties|documents|inquiries|ledger/accounts|ledger/entries|marketers|orders|payment-declarations|tenants|virtual-cards)(?:/([^/]+))?",path,re.I)
    if match:
        resource=match.group(1).lower()
        ident=match.group(2)
        if ident:
            item=record_get(resource,ident)
            if not item: raise ApiError(404,"رکورد پیدا نشد.")
            return {"data":public_record(item)}
        if resource=="contract-templates" and not record_list(resource):
            return {"data":[]}
        return {"data":[public_record(x) for x in record_list(resource)]}
    if p=="/api/v1/admin/backups":
        return {"data":[public_record(x) for x in record_list("backups")]}
    raise ApiError(501,"این مسیر در پیش‌نمایش توسعه‌ای هنوز پیاده‌سازی نشده است: "+path)

def preview_admin_post(handler, path, body):
    user=require_admin(handler)
    p=path.lower()
    if p=="/api/v1/admin/contract-variables/sync-defaults":
        defaults=[
          {"key":"user.fullName","label":"نام و نام خانوادگی","dataType":"String","source":"User","path":"fullName","required":True,"format":"","sensitivity":"Normal","defaultValue":"","validation":""},
          {"key":"user.nationalCode","label":"کد ملی","dataType":"String","source":"User","path":"nationalCode","required":True,"format":"","sensitivity":"Sensitive","defaultValue":"","validation":"10 digits"},
          {"key":"loan.amount","label":"مبلغ تسهیلات","dataType":"Money","source":"Loan","path":"amount","required":True,"format":"N0","sensitivity":"Normal","defaultValue":"","validation":">= 0"},
          {"key":"loan.months","label":"تعداد اقساط","dataType":"Integer","source":"Loan","path":"months","required":True,"format":"","sensitivity":"Normal","defaultValue":"","validation":"> 0"}]
        added=0; existing={x.get("key") for x in record_list("contract-variables")}
        for d in defaults:
            if d["key"] not in existing: save_record("contract-variables",d,actor_id=user["id"],action="seed-default")
            added+=int(d["key"] not in existing)
        return {"added":added}
    if p=="/api/v1/admin/contracts/generate":
        body=dict(body); contract_id=str(uuid.uuid4())
        contract={"id":contract_id,"number":"DP-"+now().__str__()+"-"+contract_id[:6].upper(),
          "title":"قرارداد پیش‌نمایش "+str(body.get("productId") or ""),
          "userId":str(body.get("userId") or ""),"productId":str(body.get("productId") or ""),
          "amount":int(body.get("amount") or 0),"months":int(body.get("months") or 0),
          "stage":body.get("stage") or "Draft","status":"Draft" if body.get("dry") else "Presented",
          "html":"<h1>قرارداد نمونه پیش‌نمایش</h1><p>این متن برای آزمایش رابط کاربری است و قرارداد حقوقی معتبر نیست.</p>",
          "events":[{"at":iso_now(),"action":"generate","note":"ایجاد در پیش‌نمایش"}]}
        if not body.get("dry"): save_record("contracts",contract,actor_id=user["id"],action="generate")
        return {"data":contract}
    if p=="/api/v1/admin/virtual-cards/issue":
        card={"id":str(uuid.uuid4()),"code":"DP-"+secrets.token_hex(4).upper(),
              "last4":secrets.token_hex(2).upper(),"holderName":str(body.get("holderName") or ""),
              "userId":str(body.get("userId") or ""),"loanId":str(body.get("loanId") or ""),
              "limit":int(body.get("limit") or 0),"perTxnLimit":int(body.get("limit") or 0),
              "status":"Active","createdAt":iso_now(),"transactions":[]}
        card=save_record("virtual-cards",card,actor_id=user["id"],action="issue")
        return {"data":public_record(card)}
    match=re.fullmatch(r"/api/v1/admin/virtual-cards/([^/]+)/(activate|freeze|cancel|block|unblock)",path,re.I)
    if match:
        card=record_get("virtual-cards",match.group(1))
        if not card: raise ApiError(404,"کارت پیدا نشد.")
        status={"activate":"Active","freeze":"Frozen","cancel":"Cancelled","block":"Blocked","unblock":"Active"}[match.group(2).lower()]
        return {"data":public_record(save_record("virtual-cards",{"status":status},match.group(1),user["id"],"status-change"))}
    match=re.fullmatch(r"/api/v1/admin/documents/([^/]+)/review",path,re.I)
    if match:
        return {"data":public_record(save_record("documents",{"status":body.get("status","Reviewed"),
              "reviewNote":str(body.get("note") or ""),"ocrText":str(body.get("ocrText") or "")},
              match.group(1),user["id"],"review"))}
    match=re.fullmatch(r"/api/v1/admin/payment-declarations/([^/]+)/review",path,re.I)
    if match:
        return {"data":public_record(save_record("payment-declarations",{"status":body.get("status","Reviewed"),
              "note":str(body.get("note") or "")},match.group(1),user["id"],"review"))}
    match=re.fullmatch(r"/api/v1/admin/inquiries/([^/]+)/result",path,re.I)
    if match:
        return {"data":public_record(save_record("inquiries",{"status":body.get("status","Done"),
              "result":str(body.get("result") or "")},match.group(1),user["id"],"result"))}
    match=re.fullmatch(r"/api/v1/admin/orders/([^/]+)/status",path,re.I)
    if match: return {"data":public_record(save_record("orders",{"status":body.get("status","Updated")},match.group(1),user["id"],"status-change"))}
    match=re.fullmatch(r"/api/v1/admin/tenants/([^/]+)/domains",path,re.I)
    if match:
        tenant=record_get("tenants",match.group(1))
        if not tenant: raise ApiError(404,"مستأجر پیدا نشد.")
        domain={"id":str(uuid.uuid4()),"host":str(body.get("host") or "").strip().lower(),"isPrimary":bool(body.get("isPrimary"))}
        if not re.fullmatch(r"[a-z0-9.-]{3,253}",domain["host"]): raise ApiError(400,"دامنه معتبر نیست.")
        domains=tenant.get("domains",[]); domains.append(domain)
        return {"data":public_record(save_record("tenants",{"domains":domains},match.group(1),user["id"],"add-domain"))}
    match=re.fullmatch(r"/api/v1/admin/backups",path,re.I)
    if match:
        with connect_db() as c:
            users=int(c.execute("SELECT COUNT(*) FROM app_users").fetchone()[0])
            products=[product_json(x) for x in c.execute("SELECT * FROM loan_products ORDER BY sort_order,name").fetchall()]
        snapshot={"createdAt":iso_now(),"previewOnly":True,"userCount":users,"loanProducts":products,
                  "resources":{name:record_list(name) for name in ("contract-templates","contract-variables","contracts","counterparties","documents","inquiries","ledger/accounts","ledger/entries","marketers","orders","payment-declarations","tenants","virtual-cards")}}
        name="preview-backup-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-"+secrets.token_hex(3)+".json"
        backup=save_record("backups",{"name":name,"createdAt":iso_now(),"size":len(json.dumps(snapshot,ensure_ascii=False)),"snapshot":snapshot},name,user["id"],"backup")
        return {"name":name,"createdAt":backup["createdAt"]}
    collection=re.fullmatch(r"/api/v1/admin/(contract-templates|contract-variables|contracts|counterparties|documents|inquiries|ledger/accounts|ledger/entries|marketers|orders|payment-declarations|tenants|virtual-cards)",path,re.I)
    if collection:
        resource=collection.group(1).lower()
        item=dict(body)
        if resource=="orders":
            item.setdefault("code","ORD-"+secrets.token_hex(4).upper()); item.setdefault("status","Pending"); item.setdefault("createdAt",iso_now())
        elif resource=="inquiries": item.setdefault("status","Pending"); item.setdefault("createdAt",iso_now())
        elif resource=="payment-declarations": item.setdefault("status","Pending"); item.setdefault("createdAt",iso_now())
        elif resource=="documents": item.setdefault("status","Pending"); item.setdefault("createdOn",iso_now())
        elif resource=="contracts":
            item.setdefault("number","DP-"+secrets.token_hex(5).upper()); item.setdefault("status","Draft")
        elif resource=="virtual-cards":
            item.setdefault("status","Active"); item.setdefault("limit",0); item.setdefault("perTxnLimit",item.get("limit",0))
        return {"data":public_record(save_record(resource,item,actor_id=user["id"],action="create"))}
    raise ApiError(501,"این عملیات در پیش‌نمایش توسعه‌ای هنوز پیاده‌سازی نشده است: "+path)

def preview_admin_put(handler, path, body):
    user=require_admin(handler)
    p=path.lower()
    if p=="/api/v1/admin/app-settings":
        if not isinstance(body,dict): raise ApiError(400,"تنظیمات باید به‌صورت شیء ارسال شوند.")
        with connect_db() as c:
            for key,value in body.items():
                if key=="jwt_secret": continue
                c.execute("INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                          (str(key),str(value)))
        audit_preview(user["id"],"update","app-settings","",{"keys":sorted(k for k in body if k!="jwt_secret")})
        return {"ok":True}
    match=re.fullmatch(r"/api/v1/admin/loan-products/([^/]+)/contracts",path,re.I)
    if match:
        if not isinstance(body,list): raise ApiError(400,"فهرست مراحل قرارداد معتبر نیست.")
        saved=save_record("loan-product-contracts",{"rows":body},match.group(1),user["id"],"update")
        return {"data":saved.get("rows",[])}
    match=re.fullmatch(r"/api/v1/admin/virtual-cards/([^/]+)/limit",path,re.I)
    if match:
        card=record_get("virtual-cards",match.group(1))
        if not card: raise ApiError(404,"کارت پیدا نشد.")
        return {"data":public_record(save_record("virtual-cards",{"limit":int(body.get("limit") or 0),
          "perTxnLimit":int(body.get("perTxnLimit") or 0)},match.group(1),user["id"],"limit-change"))}
    match=re.fullmatch(r"/api/v1/admin/(contract-templates|contract-variables|contracts|counterparties|documents|inquiries|ledger/accounts|ledger/entries|marketers|orders|payment-declarations|tenants|virtual-cards)/([^/]+)",path,re.I)
    if match:
        return {"data":public_record(save_record(match.group(1).lower(),body,match.group(2),user["id"],"update"))}
    raise ApiError(501,"این عملیات در پیش‌نمایش توسعه‌ای هنوز پیاده‌سازی نشده است: "+path)

def preview_admin_delete(handler, path):
    user=require_admin(handler)
    p=path.lower()
    match=re.fullmatch(r"/api/v1/admin/tenants/([^/]+)/domains/([^/]+)",path,re.I)
    if match:
        tenant=record_get("tenants",match.group(1))
        if not tenant: raise ApiError(404,"مستأجر پیدا نشد.")
        domains=[x for x in tenant.get("domains",[]) if str(x.get("id"))!=match.group(2)]
        save_record("tenants",{"domains":domains},match.group(1),user["id"],"delete-domain")
        return {"ok":True}
    match=re.fullmatch(r"/api/v1/admin/(contract-templates|contract-variables|contracts|counterparties|documents|inquiries|ledger/accounts|ledger/entries|marketers|orders|payment-declarations|tenants|virtual-cards)/([^/]+)",path,re.I)
    if match:
        delete_record(match.group(1).lower(),match.group(2),user["id"])
        return {"ok":True}
    raise ApiError(501,"این عملیات در پیش‌نمایش توسعه‌ای هنوز پیاده‌سازی نشده است: "+path)

def api_get(handler,path,query):
    p=path.lower()
    if p in ("/api/v1/health","/api/v1/health/live"):
        with connect_db() as c:
            users=c.execute("SELECT COUNT(*) n FROM app_users").fetchone()["n"]
            products=c.execute("SELECT COUNT(*) n FROM loan_products").fetchone()["n"]
        return 200,{"ok":True,"database":"sqlite","databasePath":str(DB_PATH),"users":users,"loanProducts":products}
    if p=="/api/v1/tenant/config":
        with connect_db() as c: t=c.execute("SELECT * FROM tenants ORDER BY id LIMIT 1").fetchone()
        return 200,{"data":{"name":t["name"],"brand":{"primary":t["brand_primary"],"accent":t["brand_accent"],"logoText":t["logo_text"]}}}
    if p=="/api/v1/loan-products":
        with connect_db() as c: rows=c.execute("SELECT * FROM loan_products WHERE is_active=1 ORDER BY sort_order,name").fetchall()
        return 200,{"data":[product_json(r) for r in rows]}
    if p=="/api/v1/security/captcha": return 200,create_captcha()
    if p=="/api/v1/security/otp/status":
        phone=normalize_phone((query.get("phone") or [""])[0])
        if not phone: raise ApiError(400,"شماره موبایل معتبر نیست.")
        with connect_db() as c: row=c.execute("SELECT expires_at,resend_at FROM otp_challenges WHERE phone=? ORDER BY created_at DESC LIMIT 1",(phone,)).fetchone()
        return 200,{"expiresIn":max(0,row["expires_at"]-now()) if row else 0,"resendIn":max(0,row["resend_at"]-now()) if row else 0}
    if p=="/api/v1/auth/me": return 200,{"data":safe_user(auth_user(handler))}
    if p=="/api/v1/admin/loan-products":
        require_admin(handler)
        with connect_db() as c: rows=c.execute("SELECT * FROM loan_products ORDER BY sort_order,name").fetchall()
        return 200,{"data":[product_json(r) for r in rows]}
    if p=="/api/v1/admin/users":
        require_admin(handler)
        with connect_db() as c: rows=c.execute("SELECT * FROM app_users ORDER BY created_at DESC").fetchall()
        return 200,{"data":[safe_user(r) for r in rows]}
    if p=="/api/v1/me/contracts":
        user=auth_user(handler)
        owned=[x for x in record_list("contracts") if str(x.get("userId") or "") in (str(user["id"]),str(user["phone"]))]
        return 200,{"data":[public_record(x) for x in owned]}
    if p=="/api/v1/me/documents":
        user=auth_user(handler)
        owned=[x for x in record_list("documents") if str(x.get("userId") or "") in (str(user["id"]),str(user["phone"]))]
        return 200,{"data":[public_record(x) for x in owned]}
    match=re.fullmatch(r"/api/v1/me/contracts/([^/]+)/html",path,re.I)
    if match:
        user=auth_user(handler); item=record_get("contracts",match.group(1))
        if not item or str(item.get("userId") or "") not in (str(user["id"]),str(user["phone"])):
            raise ApiError(404,"قرارداد پیدا نشد.")
        return 200,str(item.get("html") or "<h1>قرارداد پیش‌نمایش</h1><p>این متن نمونه است و قرارداد حقوقی معتبر محسوب نمی‌شود.</p>")
    match=re.fullmatch(r"/api/v1/me/documents/([^/]+)/file",path,re.I)
    if match:
        user=auth_user(handler); item=record_get("documents",match.group(1))
        if not item or str(item.get("userId") or "") not in (str(user["id"]),str(user["phone"])):
            raise ApiError(404,"مدرک پیدا نشد.")
        file_data=item.get("fileData")
        if not file_data: raise ApiError(404,"فایل این مدرک در پیش‌نمایش موجود نیست.")
        return 200,(base64.b64decode(file_data),str(item.get("contentType") or "application/octet-stream"))
    return 200,preview_admin_get(handler,path,query)

def save_product(body,product_id=None):
    name=str(body.get("name") or body.get("title") or "").strip()
    slug=str(body.get("slug") or body.get("code") or product_id or ("plan-"+secrets.token_hex(4))).strip()
    if not name: raise ApiError(400,"نام طرح الزامی است.")
    try:
        min_amount=int(body.get("minAmount",1000000)); max_amount=int(body.get("maxAmount",20000000)); interval=int(body.get("intervalDays",30))
    except (TypeError,ValueError): raise ApiError(400,"مبالغ و فاصله اقساط باید عددی باشند.")
    if min_amount<0 or max_amount<min_amount or interval<1: raise ApiError(400,"بازه مبلغ یا فاصله اقساط معتبر نیست.")
    tiers=body.get("tiers",body.get("Tiers",[])); conditions=body.get("conditions") or body.get("Conditions") or {}
    documents=body.get("documents") or body.get("Documents") or []
    tiers_json=body.get("tiersJson") or body.get("TiersJson") or json.dumps(tiers,ensure_ascii=False)
    cond_json=body.get("conditionsJson") or body.get("ConditionsJson") or json.dumps(conditions,ensure_ascii=False)
    docs_json=body.get("documentsJson") or body.get("DocumentsJson") or json.dumps(documents,ensure_ascii=False)
    active=0 if body.get("isActive",body.get("IsActive",True)) is False else 1
    badge=str(body.get("badge") or body.get("Badge") or ""); description=str(body.get("description") or body.get("Description") or "")
    product_id=str(product_id or body.get("id") or slug)
    with connect_db() as c:
        exists=c.execute("SELECT id FROM loan_products WHERE id=?",(product_id,)).fetchone()
        values=(name,slug,description,badge,min_amount,max_amount,interval,tiers_json,cond_json,docs_json,active)
        if exists:
            c.execute("UPDATE loan_products SET name=?,slug=?,description=?,badge=?,min_amount=?,max_amount=?,interval_days=?,tiers_json=?,conditions_json=?,documents_json=?,is_active=? WHERE id=?",values+(product_id,))
        else:
            c.execute("""INSERT INTO loan_products(id,name,slug,description,badge,min_amount,max_amount,interval_days,tiers_json,conditions_json,documents_json,is_active,sort_order,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (product_id,name,slug,description,badge,min_amount,max_amount,interval,tiers_json,cond_json,docs_json,active,int(body.get("sortOrder") or 100),iso_now()))
        row=c.execute("SELECT * FROM loan_products WHERE id=?",(product_id,)).fetchone()
    return product_json(row)

def api_post(handler,path,body):
    p=path.lower()
    if not isinstance(body,dict): raise ApiError(400,"بدنه درخواست باید یک شیء JSON یا فرم فایل معتبر باشد.")
    if p=="/api/v1/security/otp/request":
        phone=normalize_phone(body.get("phone")); purpose=str(body.get("purpose") or "login").lower()
        if not phone: raise ApiError(400,"شماره موبایل معتبر نیست.")
        if purpose not in ("login","register","reset"): purpose="login"
        if not validate_captcha(str(body.get("captchaId") or ""),str(body.get("captchaAnswer") or "")): raise ApiError(400,"کد امنیتی نادرست یا منقضی شده است.")
        with connect_db() as c: exists=c.execute("SELECT 1 FROM app_users WHERE phone=?",(phone,)).fetchone() is not None
        if purpose in ("login","reset") and not exists: raise ApiError(404,"حسابی با این شماره پیدا نشد.")
        if purpose=="register" and exists: raise ApiError(409,"این شماره قبلاً ثبت شده است؛ وارد شوید.")
        return 200,create_otp(phone,purpose)
    if p=="/api/v1/security/otp/verify":
        phone=normalize_phone(body.get("phone"))
        purpose=str(body.get("purpose") or "").lower()
        if purpose not in ("register","reset"): purpose="login"
        if not phone: raise ApiError(400,"شماره موبایل معتبر نیست.")
        challenge=verify_otp(phone,purpose,str(body.get("code") or ""))
        if purpose in ("register","reset"):
            ticket=create_ticket(phone)
            with connect_db() as c: c.execute("DELETE FROM otp_challenges WHERE phone=? AND purpose=?",(phone,purpose))
            return 200,{"ticket":ticket}
        with connect_db() as c:
            user=c.execute("SELECT * FROM app_users WHERE phone=? AND is_active=1",(phone,)).fetchone()
            c.execute("DELETE FROM otp_challenges WHERE phone=? AND purpose=?",(phone,purpose))
        if not user: raise ApiError(404,"حساب فعال پیدا نشد؛ ابتدا ثبت‌نام کنید.")
        token=issue_token(user); return 200,{"data":{"accessToken":token,"token":token,"user":safe_user(user)}}
    if p=="/api/v1/security/login":
        login=str(body.get("username") or body.get("phone") or "").strip()
        if not validate_captcha(str(body.get("captchaId") or ""),str(body.get("captchaAnswer") or "")): raise ApiError(400,"کد امنیتی نادرست یا منقضی شده است.")
        with connect_db() as c:
            user=find_user(c,login)
            if user is None or not user["is_active"] or not password_ok(str(body.get("password") or ""),user["password_hash"]): raise ApiError(401,"نام کاربری یا رمز عبور نادرست است.")
        token=issue_token(user); return 200,{"data":{"accessToken":token,"token":token,"user":safe_user(user)}}
    if p=="/api/v1/security/register":
        ticket=str(body.get("ticket") or "")
        if not ticket: raise ApiError(400,"تأیید شماره موبایل الزامی است.")
        if not validate_captcha(str(body.get("captchaId") or ""),str(body.get("captchaAnswer") or "")): raise ApiError(400,"کد امنیتی نادرست یا منقضی شده است.")
        with connect_db() as c:
            tr=c.execute("SELECT * FROM otp_tickets WHERE ticket=?",(ticket,)).fetchone()
            if not tr or tr["expires_at"]<now(): raise ApiError(400,"تأیید موبایل منقضی شده است؛ دوباره کد بگیرید.")
            full_name=str(body.get("fullName") or "").strip(); phone=tr["phone"]
            password=normalize_digits(body.get("password") or ""); nid=normalize_digits(body.get("nationalCode") or "").strip() or None
            email=str(body.get("email") or "").strip()
            if len(password)<8: raise ApiError(400,"رمز ثابت باید حداقل ۸ نویسه باشد.")
            if not re.fullmatch(r"\d{10}",nid or ""): raise ApiError(400,"کد ملی باید ۱۰ رقم باشد.")
            if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+",email): raise ApiError(400,"ایمیل معتبر و الزامی است.")
            user=add_user(c,full_name,phone,password_hash(password),"Customer",email,nid)
            c.execute("DELETE FROM otp_tickets WHERE ticket=?",(ticket,))
        token=issue_token(user); return 200,{"data":{"accessToken":token,"token":token,"user":safe_user(user)}}
    if p=="/api/v1/security/password/reset":
        ticket=str(body.get("ticket") or "")
        password=normalize_digits(body.get("password") or "")
        if len(password)<8: raise ApiError(400,"رمز عبور باید حداقل ۸ نویسه باشد.")
        with connect_db() as c:
            tr=c.execute("SELECT * FROM otp_tickets WHERE ticket=?",(ticket,)).fetchone()
            if not tr or tr["expires_at"]<now(): raise ApiError(400,"تأیید شماره منقضی شده است؛ فرایند را دوباره آغاز کنید.")
            user=c.execute("SELECT id FROM app_users WHERE phone=?",(tr["phone"],)).fetchone()
            if not user: raise ApiError(404,"حساب پیدا نشد.")
            c.execute("UPDATE app_users SET password_hash=? WHERE id=?",(password_hash(password),user["id"]))
            c.execute("DELETE FROM otp_tickets WHERE ticket=?",(ticket,))
        return 200,{"ok":True,"message":"رمز عبور در دیتابیس توسعه‌ای تغییر کرد."}
    if p=="/api/v1/security/register/ocr": raise ApiError(501,"OCR در پیش‌نمایش توسعه‌ای فعال نیست.")
    if p=="/api/v1/auth/login":
        login=str(body.get("phoneNumber") or body.get("username") or body.get("phone") or "").strip()
        with connect_db() as c:
            user=find_user(c,login)
            if user is None or not user["is_active"] or not password_ok(str(body.get("password") or ""),user["password_hash"]): raise ApiError(401,"نام کاربری یا رمز عبور نادرست است.")
        token=issue_token(user); return 200,{"data":{"accessToken":token,"token":token,"user":safe_user(user)}}
    if p=="/api/v1/auth/register":
        phone=normalize_phone(body.get("phoneNumber") or body.get("phone")); password=normalize_digits(body.get("password") or "")
        full_name=str(body.get("fullName") or "").strip()
        national_code=normalize_digits(body.get("nationalCode") or "").strip()
        email=str(body.get("email") or "").strip()
        if not phone: raise ApiError(400,"شماره موبایل معتبر نیست.")
        if len(password)<8: raise ApiError(400,"رمز ثابت باید حداقل ۸ نویسه باشد.")
        if len(full_name.split())<2: raise ApiError(400,"نام و نام خانوادگی الزامی است.")
        if not re.fullmatch(r"\d{10}",national_code): raise ApiError(400,"کد ملی باید ۱۰ رقم باشد.")
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+",email): raise ApiError(400,"ایمیل معتبر و الزامی است.")
        with connect_db() as c:
            if c.execute("SELECT 1 FROM app_users WHERE phone=?",(phone,)).fetchone(): raise ApiError(409,"این شماره قبلاً ثبت شده است.")
        pending=dict(body); pending["fullName"]=full_name; pending["nationalCode"]=national_code; pending["email"]=email
        pending["password_hash"]=password_hash(password); pending.pop("password",None)
        return 200,create_otp(phone,"home-register",pending)
    if p=="/api/v1/auth/verify-otp":
        phone=normalize_phone(body.get("phoneNumber") or body.get("phone"))
        challenge=verify_otp(phone,"home-register",str(body.get("code") or ""))
        pending=json.loads(challenge["pending_json"] or "{}")
        if not pending.get("password_hash"): raise ApiError(400,"اطلاعات ثبت‌نام ناقص است؛ دوباره ثبت‌نام کنید.")
        with connect_db() as c:
            user=add_user(c,str(pending.get("fullName") or ""),phone,pending["password_hash"],"Customer",pending.get("email"),normalize_digits(pending.get("nationalCode") or "") or None)
            c.execute("DELETE FROM otp_challenges WHERE phone=? AND purpose=?",(phone,"home-register"))
        token=issue_token(user); return 200,{"data":{"accessToken":token,"token":token,"user":safe_user(user)}}
    if p=="/api/v1/beta/inquiry": raise ApiError(503,"اتصال واقعی به سرویس استعلام بانک در این محیط تنظیم نشده است.")
    if p=="/api/v1/admin/loan-products":
        require_admin(handler); return 201,{"data":save_product(body)}
    match=re.fullmatch(r"/api/v1/admin/loan-products/([^/]+)/toggle",path,re.IGNORECASE)
    if match:
        require_admin(handler)
        with connect_db() as c:
            row=c.execute("SELECT * FROM loan_products WHERE id=? OR slug=?",(match.group(1),match.group(1))).fetchone()
            if not row: raise ApiError(404,"طرح پیدا نشد.")
            c.execute("UPDATE loan_products SET is_active=? WHERE id=?",(0 if row["is_active"] else 1,row["id"]))
            updated=c.execute("SELECT * FROM loan_products WHERE id=?",(row["id"],)).fetchone()
        return 200,{"data":product_json(updated)}
    if p=="/api/v1/me/documents":
        user=auth_user(handler)
        upload=body.get("file") if isinstance(body.get("file"),dict) else {}
        if not upload.get("contentBase64"): raise ApiError(400,"ابتدا یک فایل انتخاب کنید.")
        item={"userId":user["id"],"kind":str(body.get("kind") or "مدرک").strip()[:100],
              "status":"Pending","createdOn":iso_now(),"createdAt":iso_now(),
              "fileName":upload.get("filename","upload"),"contentType":upload.get("contentType","application/octet-stream"),
              "fileData":upload["contentBase64"],"size":int(upload.get("size") or 0),"fields":{},
              "ocrText":"","reviewNote":""}
        saved=save_record("documents",item,actor_id=user["id"],action="upload")
        return 201,{"data":public_record(saved),"ocr":False}
    match=re.fullmatch(r"/api/v1/me/contracts/([^/]+)/(sign|reject)",path,re.I)
    if match:
        user=auth_user(handler); item=record_get("contracts",match.group(1))
        if not item or str(item.get("userId") or "") not in (str(user["id"]),str(user["phone"])):
            raise ApiError(404,"قرارداد پیدا نشد.")
        status="Signed" if match.group(2).lower()=="sign" else "Rejected"
        events=list(item.get("events",[])); events.append({"at":iso_now(),"action":status.lower(),"note":str(body.get("note") or "")})
        updated=save_record("contracts",{"status":status,"events":events,"rejectionNote":str(body.get("note") or "")},
                            match.group(1),user["id"],status.lower())
        return 200,{"data":public_record(updated)}
    if p=="/api/v1/admin/loan-products":
        require_admin(handler); return 201,{"data":save_product(body)}
    match=re.fullmatch(r"/api/v1/admin/loan-products/([^/]+)/toggle",path,re.IGNORECASE)
    if match:
        require_admin(handler)
        with connect_db() as c:
            row=c.execute("SELECT * FROM loan_products WHERE id=? OR slug=?",(match.group(1),match.group(1))).fetchone()
            if not row: raise ApiError(404,"طرح پیدا نشد.")
            c.execute("UPDATE loan_products SET is_active=? WHERE id=?",(0 if row["is_active"] else 1,row["id"]))
            updated=c.execute("SELECT * FROM loan_products WHERE id=?",(row["id"],)).fetchone()
        return 200,{"data":product_json(updated)}
    if re.fullmatch(r"/api/v1/admin/loan-products/[^/]+/seed",path,re.IGNORECASE):
        require_admin(handler)
        with connect_db() as c: seed_products(c)
        return 200,{"ok":True,"message":"طرح‌های پیش‌فرض در دیتابیس توسعه‌ای ثبت شدند."}
    if p=="/api/v1/public/support-tickets":
        name=str(body.get("name") or "").strip()
        phone=normalize_phone(body.get("phone") or "")
        subject=str(body.get("subject") or "").strip()
        message=str(body.get("message") or "").strip()
        if len(name)<2 or not phone or len(subject)<2 or len(message)<5:
            raise ApiError(400,"نام، شماره موبایل، موضوع و متن پیام الزامی است.")
        item=save_record("support-tickets",{"name":name,"phone":phone,"subject":subject,
          "message":message,"status":"Open","createdAt":iso_now()},actor_id="anonymous",action="support-ticket")
        return 201,{"data":{"id":item["id"],"status":item["status"],"message":"درخواست در دیتابیس پیش‌نمایش ثبت شد؛ در این محیط به مرکز پشتیبانی واقعی ارسال نمی‌شود."}}
    if p=="/api/v1/public/partnership-applications":
        name=str(body.get("name") or "").strip()
        phone=normalize_phone(body.get("phone") or "")
        kind=str(body.get("kind") or "merchant").strip().lower()
        if kind not in ("merchant","agent","organization"): kind="merchant"
        if len(name)<2 or not phone:
            raise ApiError(400,"نام و شماره موبایل معتبر وارد کنید.")
        item=save_record("partnership-applications",{"name":name,"phone":phone,"kind":kind,
          "company":str(body.get("company") or "").strip(),"message":str(body.get("message") or "").strip(),
          "status":"New","createdAt":iso_now()},actor_id="anonymous",action="partnership-application")
        return 201,{"data":{"id":item["id"],"status":item["status"],"message":"درخواست در دیتابیس پیش‌نمایش ثبت شد؛ در این محیط به سامانه عملیاتی ارسال نمی‌شود."}}
    return 201,preview_admin_post(handler,path,body)

def api_put(handler,path,body):
    p=path.lower()
    if re.fullmatch(r"/api/v1/admin/loan-products/[^/]+",path,re.I):
        if not isinstance(body,dict): raise ApiError(400,"اطلاعات طرح معتبر نیست.")
        require_admin(handler)
        ident=path.rsplit("/",1)[-1]
        return 200,{"data":save_product(body,ident)}
    if re.fullmatch(r"/api/v1/me/documents/[^/]+/fields",path,re.I):
        user=auth_user(handler); ident=path.split("/")[-2]
        item=record_get("documents",ident)
        if not item or str(item.get("userId") or "") not in (str(user["id"]),str(user["phone"])):
            raise ApiError(404,"مدرک پیدا نشد.")
        fields=body.get("fields",{}) if isinstance(body,dict) else {}
        if not isinstance(fields,dict): raise ApiError(400,"فیلدهای مدرک معتبر نیستند.")
        updated=save_record("documents",{"fields":fields},ident,user["id"],"edit-fields")
        return 200,{"data":public_record(updated)}
    if p=="/api/v1/admin/app-settings" or re.fullmatch(r"/api/v1/admin/(contract-templates|contract-variables|contracts|counterparties|documents|inquiries|ledger/accounts|ledger/entries|marketers|orders|payment-declarations|tenants|virtual-cards)/[^/]+",path,re.I) or re.fullmatch(r"/api/v1/admin/virtual-cards/[^/]+/limit",path,re.I) or re.fullmatch(r"/api/v1/admin/loan-products/[^/]+/contracts",path,re.I):
        return 200,preview_admin_put(handler,path,body)
    raise ApiError(501,"این عملیات در پیش‌نمایش توسعه‌ای هنوز پیاده‌سازی نشده است: "+path)

def api_delete(handler,path):
    p=path.lower()
    if re.fullmatch(r"/api/v1/admin/loan-products/[^/]+",path,re.I):
        require_admin(handler); ident=path.rsplit("/",1)[-1]
        with connect_db() as c:
            row=c.execute("SELECT id FROM loan_products WHERE id=? OR slug=?",(ident,ident)).fetchone()
            if not row: raise ApiError(404,"طرح پیدا نشد.")
            c.execute("DELETE FROM loan_products WHERE id=?",(row["id"],))
        return 200,{"ok":True}
    if re.fullmatch(r"/api/v1/me/documents/[^/]+",path,re.I):
        user=auth_user(handler); ident=path.rsplit("/",1)[-1]; item=record_get("documents",ident)
        if not item or str(item.get("userId") or "") not in (str(user["id"]),str(user["phone"])):
            raise ApiError(404,"مدرک پیدا نشد.")
        delete_record("documents",ident,user["id"])
        return 200,{"ok":True}
    if re.fullmatch(r"/api/v1/admin/loan-products/[^/]+/image",path,re.I):
        require_admin(handler)
        return 200,{"ok":True,"url":""}
    return 200,preview_admin_delete(handler,path)

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(FRONTEND),**kwargs)
    def end_headers(self):
        # The preview HTML must not be cached across Codespaces/git updates.
        # API JSON responses set their own Cache-Control header in send_json().
        if not urlsplit(self.path).path.startswith("/api/"):
            self.send_header("Cache-Control","no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma","no-cache")
        super().end_headers()
    def log_message(self,fmt,*args): print("[preview] "+(fmt%args),flush=True)
    def send_json(self,status,payload):
        raw=json.dumps(payload,ensure_ascii=False).encode("utf-8")
        self.send_response(status); self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(raw))); self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff"); self.end_headers(); self.wfile.write(raw)
    def send_raw(self,status,raw,content_type="application/octet-stream"):
        self.send_response(status); self.send_header("Content-Type",content_type)
        self.send_header("Content-Length",str(len(raw))); self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff"); self.end_headers(); self.wfile.write(raw)
    def dispatch_api(self,method):
        path=urlsplit(self.path).path; query=parse_qs(urlsplit(self.path).query,keep_blank_values=True)
        try:
            if method=="GET": status,result=api_get(self,path,query)
            elif method=="POST": status,result=api_post(self,path,read_request_body(self))
            elif method=="PUT": status,result=api_put(self,path,read_request_body(self))
            elif method=="DELETE": status,result=api_delete(self,path)
            else: raise ApiError(405,"روش HTTP پشتیبانی نمی‌شود.")
            if isinstance(result,tuple) and len(result)==2 and isinstance(result[0],bytes):
                self.send_raw(status,result[0],result[1]); return
            if method=="GET" and isinstance(result,str) and path.lower().endswith("/html"):
                self.send_raw(status,result.encode("utf-8"),"text/html; charset=utf-8"); return
            self.send_json(status,result)
        except ApiError as e: self.send_json(e.status,{"ok":False,"message":e.message})
        except Exception:
            traceback.print_exc(); self.send_json(500,{"ok":False,"message":"خطای داخلی در بک‌اند توسعه‌ای رخ داد."})
    def do_GET(self):
        if urlsplit(self.path).path.startswith("/api/"): self.dispatch_api("GET")
        else: super().do_GET()
    def do_POST(self):
        if urlsplit(self.path).path.startswith("/api/"): self.dispatch_api("POST")
        else: self.send_json(405,{"message":"POST فقط برای مسیرهای API مجاز است."})
    def do_PUT(self):
        if urlsplit(self.path).path.startswith("/api/"): self.dispatch_api("PUT")
        else: self.send_json(405,{"message":"PUT فقط برای مسیرهای API مجاز است."})
    def do_DELETE(self):
        if urlsplit(self.path).path.startswith("/api/"): self.dispatch_api("DELETE")
        else: self.send_json(405,{"message":"DELETE فقط برای مسیرهای API مجاز است."})
    def do_OPTIONS(self):
        self.send_response(204); self.send_header("Allow","GET, POST, PUT, DELETE, OPTIONS"); self.send_header("Content-Length","0"); self.end_headers()

def create_user_cli():
    print("ساخت کاربر فقط برای دیتابیس توسعه‌ای Codespaces (نه دیتابیس عملیاتی)")
    role=input("نقش (SuperAdmin/Admin/Customer/Merchant/Agent): ").strip()
    role=next((r for r in ROLES if r.lower()==role.lower()),"")
    if not role: print("نقش نامعتبر است."); return 2
    name=input("نام و نام خانوادگی: ").strip(); phone=normalize_phone(input("شماره موبایل (09...): "))
    national_code=normalize_digits(input("کد ملی (۱۰ رقم): ")).strip()
    email=input("ایمیل: ").strip()
    password=getpass("رمز اولیه (حداقل ۸ نویسه): "); confirm=getpass("تکرار رمز: ")
    if (len(name.split())<2 or not phone or not re.fullmatch(r"\d{10}",national_code)
        or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+",email)
        or len(password)<8 or password!=confirm):
        print("نام، شماره، کد ملی یا ایمیل معتبر نیست؛ رمز باید حداقل ۸ نویسه باشد و دو رمز یکسان باشند. حساب ساخته نشد."); return 2
    try:
        with connect_db() as c: add_user(c,name,phone,password_hash(password),role,email,national_code)
        print("حساب توسعه‌ای با نقش {} ساخته شد (شماره با ••{} تمام می‌شود).".format(role,phone[-4:]))
        print("این حساب فقط در SQLite همین Codespace وجود دارد."); return 0
    except ApiError as e: print("ساخته نشد: "+e.message); return 2

def set_role_cli():
    print("تغییر نقش فقط برای حساب دیتابیس توسعه‌ای Codespaces")
    phone=normalize_phone(input("شماره موبایل حساب ثبت‌نام‌شده (09...): "))
    requested=input("نقش جدید (SuperAdmin/Admin/Customer/Merchant/Agent): ").strip()
    role=next((r for r in ROLES if r.lower()==requested.lower()),"")
    if not phone or not role:
        print("شماره موبایل یا نقش معتبر نیست؛ تغییری انجام نشد."); return 2
    with connect_db() as c:
        user=c.execute("SELECT id FROM app_users WHERE phone=?",(phone,)).fetchone()
        if not user:
            print("حسابی با این شماره در دیتابیس همین Codespace پیدا نشد."); return 2
        c.execute("UPDATE app_users SET role=? WHERE id=?",(role,user["id"]))
    print("نقش حساب به {} تغییر کرد (شماره با ••{} تمام می‌شود).".format(role,phone[-4:]))
    print("این تغییر فقط در SQLite همین Codespace اعمال شده است."); return 0

def main():
    parser=argparse.ArgumentParser(description="Development-only DigitalPay preview with SQLite")
    parser.add_argument("--host",default="0.0.0.0"); parser.add_argument("--port",type=int,default=8080)
    parser.add_argument("--check-db",action="store_true"); parser.add_argument("--create-user",action="store_true")
    parser.add_argument("--set-role",action="store_true",help="Change a registered user's role in the development SQLite database")
    args=parser.parse_args()
    if not FRONTEND.is_dir(): print("پوشه frontend پیدا نشد: "+str(FRONTEND),file=sys.stderr); return 2
    init_db()
    if args.check_db:
        with connect_db() as c:
            users=c.execute("SELECT COUNT(*) n FROM app_users").fetchone()["n"]
            products=c.execute("SELECT COUNT(*) n FROM loan_products").fetchone()["n"]
        print("SQLite OK | Database: {} | Users: {} | Loan products: {}".format(DB_PATH,users,products)); return 0
    if args.create_user: return create_user_cli()
    if args.set_role: return set_role_cli()
    print("============================================================")
    print("DigitalPay Codespaces DEVELOPMENT PREVIEW")
    print("SQLite database: "+str(DB_PATH))
    print("Development-only OTP is fixed at 123456; no SMS is sent.")
    print("Real bank inquiry and OCR are disabled.")
    print("DO NOT use this server or database for production data.")
    print("Listening on http://{}:{}/".format(args.host,args.port),flush=True)
    server=ThreadingHTTPServer((args.host,args.port),Handler)
    try: server.serve_forever()
    except KeyboardInterrupt: print("\nPreview server stopped.",flush=True)
    finally: server.server_close()
    return 0

if __name__=="__main__":
    init_db()
    raise SystemExit(main())
