#!/usr/bin/env python3
"""نصب‌کننده‌ی مرورگری DigitalPay (موقت). فقط برای چند دقیقه روی سرور اجرا می‌شود.
- با لینک یک‌بارمصرف (توکن تصادفی) و قفل روی اولین IP؛ بعد از ۶۰ دقیقه یا پایان خودکار بسته می‌شود.
- فقط مراحل از پیش‌تعریف‌شده را اجرا می‌کند (هیچ دستور دلخواهی از مرورگر پذیرفته نمی‌شود).
- هشدار: HTTP ساده است. فقط کوتاه و برای همین نصب باز بگذارید؛ رمز/کلید در این صفحه وارد یا نمایش داده نمی‌شود.
استفاده:  python3 setup-web.py [مسیر_پروژه] [پورت]"""
import http.server, subprocess, secrets, sys, os, time, threading, json, urllib.parse, socket, re
H = os.path.dirname(os.path.abspath(__file__))
ROOT = sys.argv[1] if len(sys.argv) > 1 else "/home/ghestine/domains/ghestine.ir/Ghestine"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8765
TOKEN = secrets.token_urlsafe(24); START = time.time(); TTL = 3600; BOUND = {"ip": None}; LOCK = threading.Lock()
MASK = re.compile(r'(KEY|PEPPER|SECRET|PASSWORD|Password|Pwd|pwd)=\S+')
SQ = lambda s: "'" + s.replace("'", "'\\''") + "'"
R, HH = SQ(ROOT), SQ(H)
STEPS = {
 "check": ("۱) بررسی پیش‌نیازها", f'[ -d {R}/src ] && echo "پروژه: پیدا شد" || echo "پروژه پیدا نشد: "{R}; command -v dotnet >/dev/null && dotnet --version || echo "dotnet پیدا نشد"; command -v node >/dev/null && echo "node $(node -v)" || echo "Node.js نصب نیست (برای Next.js لازم است؛ نسخه‌ی 20.9 به بالا)"; command -v tesseract >/dev/null && tesseract --version 2>&1 | head -1 || echo "tesseract نصب نیست (apt install -y tesseract-ocr tesseract-ocr-fas)"; df -h {R} | tail -1; [ -f /etc/ghestine/secrets.env ] && echo "secrets.env: هست" || echo "secrets.env هنوز ساخته نشده"', False),
 "backup": ("۲) بکاپ پوشه‌ی پروژه", f'B="$HOME/digitalpay-backup-$(date +%Y%m%d-%H%M%S).tar.gz"; tar czf "$B" --exclude=bin --exclude=obj -C {R} src && echo "ساخته شد: $B"; echo "یادآوری: بکاپ دیتابیس را جداگانه (SQL Server) بگیرید."', False),
 "install": ("۳) نصب ماژول‌ها", f'bash {HH}/install-all.sh {R}', True),
 "migrate": ("۴) مایگریشن دیتابیس", f'cd {R} && dotnet ef migrations add DigitalPayModules -p src/Ghestine.Infrastructure -s src/Ghestine.API && dotnet ef database update -p src/Ghestine.Infrastructure -s src/Ghestine.API', True),
 "deploy": ("۵) استقرار (چند ثانیه قطع)", 'bash /home/ghestine/deploy.sh', True),
 "web": ("۶) نصب فرانت Next.js (نیازمند root)", f'[ "$(id -u)" = 0 ] && bash {HH}/web-next/install-web.sh || echo "این مرحله باید با کاربر root اجرا شود: sudo bash {HH}/web-next/install-web.sh"', True),
 "doctor": ("۷) تشخیص ورود", f'bash {HH}/backend/security/run-tool.sh --auth-doctor', False),
}
PAGE = """<!doctype html><html lang="fa" dir="rtl"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>نصب DigitalPay</title>
<style>body{font-family:Tahoma,sans-serif;background:#130c1f;color:#f3edfb;max-width:760px;margin:0 auto;padding:16px;line-height:1.9}button{font:inherit;padding:10px 16px;border:0;border-radius:10px;background:#ffb629;cursor:pointer;margin:4px 0}button[disabled]{opacity:.5}.s{background:#1d1330;border:1px solid #3a2c52;border-radius:14px;padding:12px;margin:10px 0}pre{background:#000;color:#9f9;padding:10px;border-radius:10px;max-height:340px;overflow:auto;direction:ltr;text-align:left;white-space:pre-wrap}.w{color:#ffb629}input{font:inherit;padding:6px;border-radius:8px;border:1px solid #666}</style>
<h1>نصب DigitalPay</h1><p class="w">این صفحه موقت است و HTTP ساده. بعد از اتمام، پنجره‌ی ترمینال را ببندید (Ctrl+C) تا سرور نصب خاموش شود. بکاپ دیتابیس را پیش از مراحل ۴ و ۵ بگیرید.</p>
<label class="s" style="display:block"><input type="checkbox" id="ok"> بکاپ دیتابیس و پروژه را گرفته‌ام و می‌خواهم مراحل تغییردهنده (۳، ۴ و ۵) اجرا شود.</label><div id="st"></div><pre id="o">خروجی اینجا نمایش داده می‌شود…</pre>
<script>const K=__K__,S=__S__;const st=document.getElementById('st'),o=document.getElementById('o'),ok=document.getElementById('ok');
for(const [k,v] of Object.entries(S)){const d=document.createElement('div');d.className='s';d.innerHTML='<b>'+v[0]+'</b> <button data-k="'+k+'">اجرا</button>';st.appendChild(d)}
st.onclick=async e=>{const b=e.target.closest('button');if(!b)return;const k=b.dataset.k;if(S[k][1]&&!ok.checked){alert('ابتدا تیک تأیید بکاپ را بزنید.');return}
 document.querySelectorAll('button').forEach(x=>x.disabled=true);o.textContent='';try{const r=await fetch('/run?step='+k+'&k='+K,{method:'POST'});const rd=r.body.getReader(),dc=new TextDecoder();for(;;){const {done,value}=await rd.read();if(done)break;o.textContent+=dc.decode(value);o.scrollTop=o.scrollHeight}}catch(x){o.textContent+='\\nخطا: '+x}document.querySelectorAll('button').forEach(x=>x.disabled=false)};</script>"""
class Hd(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    def log_message(self, *a): pass
    def deny(self, c=403): self.send_response(c); self.end_headers(); self.wfile.write(b"denied")
    def auth(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query); ip = self.client_address[0]
        if time.time() - START > TTL or not secrets.compare_digest((q.get("k") or [""])[0], TOKEN): return None
        if BOUND["ip"] is None: BOUND["ip"] = ip
        return q if BOUND["ip"] == ip else None
    def do_GET(self):
        if not self.auth(): return self.deny()
        body = PAGE.replace("__K__", json.dumps(TOKEN)).replace("__S__", json.dumps({k: [v[0], v[2]] for k, v in STEPS.items()}, ensure_ascii=False)).encode()
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(body)
    def do_POST(self):
        q = self.auth()
        if not q or not self.path.startswith("/run"): return self.deny()
        step = (q.get("step") or [""])[0]
        if step not in STEPS: return self.deny(400)
        if not LOCK.acquire(blocking=False): self.send_response(409); self.end_headers(); self.wfile.write("یک مرحله در حال اجراست".encode()); return
        try:
            self.send_response(200); self.send_header("Content-Type", "text/plain; charset=utf-8"); self.send_header("X-Accel-Buffering", "no"); self.end_headers()
            self.wfile.write(("=== " + STEPS[step][0] + " ===\n").encode()); self.wfile.flush()
            p = subprocess.Popen(["bash", "-c", STEPS[step][1]], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, cwd=H)
            for line in iter(p.stdout.readline, b""):
                self.wfile.write(MASK.sub(r"\1=***", line.decode("utf-8", "replace")).encode()); self.wfile.flush()
            self.wfile.write(("\n=== پایان (کد %s) ===\n" % p.wait()).encode())
        except (BrokenPipeError, ConnectionResetError): pass
        finally: LOCK.release()
def ip():
    try: s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("8.8.8.8", 80)); r = s.getsockname()[0]; s.close(); return r
    except Exception: return "IP_SERVER"
if __name__ == "__main__":
    srv = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Hd)
    print("\nلینک نصب (فقط از همین کامپیوتر/شبکه باز شود، یک‌بارمصرف، ۶۰ دقیقه اعتبار):\n  http://%s:%d/?k=%s\n\nاگر باز نشد، پورت %d در فایروال سرور (CSF/ufw) موقتاً باز شود. پایان نصب: Ctrl+C\n" % (ip(), PORT, TOKEN, PORT), flush=True)
    threading.Timer(TTL, lambda: os._exit(0)).start()
    try: srv.serve_forever()
    except KeyboardInterrupt: print("بسته شد.")
