#!/usr/bin/env python3
"""End-to-end smoke tests for the Codespaces-only SQLite preview server.

All records and credentials are created inside the disposable CI data directory.
The suite must never point at a production database.
"""
import base64
import importlib.util
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("DIGIBILEPAY_TEST_URL", "http://127.0.0.1:8088")
DATA_DIR = os.environ.get("DIGIBILEPAY_DATA_DIR")
assert DATA_DIR and "digibilepay-test-data" in DATA_DIR, "Refusing to run without disposable test DB"
spec = importlib.util.spec_from_file_location("dev_preview_server", ROOT / "backend" / "dev-preview-server.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

def request(path, method="GET", body=None, token=None, raw_body=None, content_type=None):
    headers = {}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = raw_body
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            payload = r.read()
            ctype = r.headers.get("Content-Type", "")
            if "application/json" in ctype:
                try:
                    return r.status, json.loads(payload.decode("utf-8")), payload, ctype
                except json.JSONDecodeError:
                    pass
            return r.status, None, payload, ctype
    except urllib.error.HTTPError as e:
        payload=e.read()
        try:
            parsed=json.loads(payload.decode("utf-8"))
        except Exception:
            parsed=None
        return e.code, parsed, payload, e.headers.get("Content-Type","")

def check_pages():
    pages = [
        "/", "/login.html", "/register.html", "/panel.html", "/profile.html",
        "/forgot.html", "/documents.html", "/contracts.html", "/support.html",
        "/partners.html", "/terms.html", "/privacy.html",
    ]
    for page in pages:
        status, _, _, _ = request(page)
        assert status == 200, f"{page} returned HTTP {status}"
    print("PASS: all primary preview pages return HTTP 200")

def check_inline_javascript():
    problems=[]
    pattern=re.compile(r"<script\b[^>]*>(.*?)</script\s*>", re.I|re.S)
    with tempfile.TemporaryDirectory(prefix="digibilepay-js-") as tmp:
        for html in sorted((ROOT/"frontend").glob("*.html")):
            source=html.read_text(encoding="utf-8")
            for n, script in enumerate(pattern.findall(source), 1):
                if not script.strip():
                    continue
                js=Path(tmp)/f"{html.stem}-{n}.js"
                js.write_text(script, encoding="utf-8")
                run=subprocess.run(["node","--check",str(js)],capture_output=True,text=True)
                if run.returncode:
                    problems.append(f"{html.name} script {n}: {run.stderr.strip()}")
    assert not problems, "Inline JavaScript syntax errors:\n"+"\n".join(problems)
    print("PASS: inline JavaScript syntax in every frontend HTML page")

def json_data(result):
    assert isinstance(result,dict), result
    return result.get("data", result)

def check_api_and_beta():
    status, health, _, _ = request("/api/v1/health")
    assert status==200 and health["ok"] and health["database"]=="sqlite", health
    status, tenant, _, _ = request("/api/v1/tenant/config")
    assert status==200 and json_data(tenant).get("name"), tenant
    status, plans, _, _ = request("/api/v1/loan-products")
    products=json_data(plans)
    assert status==200 and len(products)>=4, products
    beta=next((p for p in products if p.get("id")=="beta" or p.get("slug")=="beta"),None)
    assert beta and beta.get("kind")=="beta" and beta.get("steps"), beta
    assert beta.get("isActive") is True, beta
    print("PASS: health, tenant, seed plans and beta plan visibility")

def create_test_admin():
    phone="09000000000"
    with app.connect_db() as c:
        existing=c.execute("SELECT * FROM app_users WHERE phone=?",(phone,)).fetchone()
        if existing:
            return phone, "CI-preview-pass-2026"
        app.add_user(c,"CI Preview Admin",phone,app.password_hash("CI-preview-pass-2026"),
                     "SuperAdmin","ci-preview@example.invalid","0123456789")
    return phone, "CI-preview-pass-2026"

def check_auth_and_admin_routes():
    phone,password=create_test_admin()
    status, login, _, _=request("/api/v1/auth/login","POST",{"phoneNumber":phone,"password":password})
    assert status==200, login
    token=(login.get("data") or login).get("accessToken") or (login.get("data") or login).get("token")
    assert token, login
    status, me, _, _=request("/api/v1/auth/me",token=token)
    user=json_data(me)
    assert status==200 and user.get("role")=="SuperAdmin", me
    endpoints=[
        "/api/v1/admin/users",
        "/api/v1/admin/loan-products",
        "/api/v1/admin/loan-products/labels",
        "/api/v1/admin/app-settings",
        "/api/v1/admin/audit?take=20",
        "/api/v1/admin/audit/verify",
        "/api/v1/admin/backups",
        "/api/v1/admin/contract-templates",
        "/api/v1/admin/contract-variables",
        "/api/v1/admin/contracts",
        "/api/v1/admin/counterparties",
        "/api/v1/admin/documents",
        "/api/v1/admin/inquiries",
        "/api/v1/admin/ledger/accounts",
        "/api/v1/admin/ledger/entries",
        "/api/v1/admin/ledger/trial-balance",
        "/api/v1/admin/marketers",
        "/api/v1/admin/orders",
        "/api/v1/admin/payment-declarations",
        "/api/v1/admin/tenants",
        "/api/v1/admin/virtual-cards",
        "/api/v1/me/documents",
        "/api/v1/me/contracts",
    ]
    for path in endpoints:
        status, payload, _, _=request(path,token=token)
        assert status < 500, f"{path} => {status}: {payload}"
    status, settings, _, _=request("/api/v1/admin/app-settings","PUT",{"previewTest":"ok"},token)
    assert status==200, settings
    status, get_settings, _, _=request("/api/v1/admin/app-settings",token=token)
    assert status==200 and json_data(get_settings).get("previewTest")=="ok", get_settings
    status, marketer, _, _=request("/api/v1/admin/marketers","POST",
        {"name":"CI Test Marketer","phone":"09000000001","commissionPercent":2,"isActive":True},token)
    assert status==201, marketer
    mid=json_data(marketer).get("id")
    status, marketers, _, _=request("/api/v1/admin/marketers",token=token)
    assert status==200 and any(x.get("id")==mid for x in json_data(marketers)), marketers
    status, card, _, _=request("/api/v1/admin/virtual-cards/issue","POST",
        {"loanId":"CI-LOAN","userId":"CI-USER","holderName":"CI Preview","limit":100000},token)
    assert status==201, card
    card_id=json_data(card).get("id")
    status, changed, _, _=request("/api/v1/admin/virtual-cards/"+card_id+"/freeze","POST",{},token)
    assert status in (200,201) and json_data(changed).get("status")=="Frozen", changed
    status, audit, _, _=request("/api/v1/admin/audit/verify",token=token)
    assert status==200 and json_data(audit).get("ok") is True, audit
    # Bank inquiry is intentionally not connected in Codespaces.
    status, beta_inquiry, _, _=request("/api/v1/beta/inquiry","POST",
        {"nationalCode":"0123456789","consent":True},token)
    assert status==503 and beta_inquiry, beta_inquiry
    print("PASS: SuperAdmin auth, panel endpoints, persisted records, card state, audit chain")
    print("PASS: beta inquiry explicitly reports unavailable bank integration (HTTP 503)")
    return phone, password, token

def check_admin_module_mutations(token):
    status, created, _, _=request("/api/v1/admin/contract-templates","POST",
        {"title":"CI Template","bodyHtml":"<h1>CI template</h1>","type":"Company","status":"Draft"},token)
    assert status==201, created
    template=json_data(created); tid=template["id"]
    status, validation, _, _=request(f"/api/v1/admin/contract-templates/{tid}/validate","POST",{},token)
    assert status==201 and not json_data(validation).get("problems"), validation
    status, preview, _, _=request(f"/api/v1/admin/contract-templates/{tid}/preview","POST",{},token)
    assert status==201 and "CI template" in json_data(preview).get("html",""), preview
    status, published, _, _=request(f"/api/v1/admin/contract-templates/{tid}/publish","POST",{},token)
    assert status==201 and json_data(published).get("status")=="Published", published
    status, version, _, _=request(f"/api/v1/admin/contract-templates/{tid}/new-version","POST",{},token)
    assert status==201 and json_data(version).get("id")!=tid, version

    sample_boundary="----TemplateSampleBoundaryCI"
    sample_body=(b"--"+sample_boundary.encode()+b"\r\nContent-Disposition: form-data; name=\"file\"; filename=\"sample.txt\"\r\nContent-Type: text/plain\r\n\r\ntemplate-sample-data\r\n--"+sample_boundary.encode()+b"--\r\n")
    status, sample_meta, _, _=request(f"/api/v1/admin/contract-templates/{tid}/sample","POST",
        raw_body=sample_body,content_type="multipart/form-data; boundary="+sample_boundary,token=token)
    assert status==201, sample_meta
    status, _, sample_bytes, _=request(f"/api/v1/admin/contract-templates/{tid}/sample",token=token)
    assert status==200 and sample_bytes==b"template-sample-data", sample_bytes

    status, contract, _, _=request("/api/v1/admin/contracts/generate","POST",
        {"userId":"CI-USER","productId":"p3","amount":1000000,"months":3,"dry":False,"stage":"Draft"},token)
    assert status==201, contract
    contract_obj=json_data(contract); cid=contract_obj["id"]
    status, _, html, ctype=request(f"/api/v1/admin/contracts/{cid}/html",token=token)
    assert status==200 and "قرارداد نمونه پیش‌نمایش" in html.decode("utf-8") and "text/html" in ctype, (status,ctype,html)
    status, signed, _, _=request(f"/api/v1/admin/contracts/{cid}/sign","POST",{},token)
    assert status==201 and json_data(signed).get("status")=="Signed", signed

    for code,name in [("1000","CI Cash"),("2000","CI Clearing")]:
        status, account, _, _=request("/api/v1/admin/ledger/accounts","POST",
            {"code":code,"name":name,"type":"Asset"},token)
        assert status==201, account
    status, entry, _, _=request("/api/v1/admin/ledger/entries","POST",
        {"memo":"CI balanced entry","lines":[{"accountId":"1000","debit":1500,"credit":0},{"accountId":"2000","debit":0,"credit":1500}]},token)
    assert status==201, entry
    status, balance, _, _=request("/api/v1/admin/ledger/trial-balance",token=token)
    assert status==200 and any(x.get("code")=="1000" and x.get("debit")==1500 for x in json_data(balance)), balance
    status, reversed_entry, _, _=request("/api/v1/admin/ledger/entries/"+json_data(entry)["id"]+"/reverse","POST",{},token)
    assert status==201 and json_data(reversed_entry).get("reverses")==json_data(entry)["id"], reversed_entry

    status, tenant, _, _=request("/api/v1/admin/tenants","POST",
        {"name":"CI Tenant","slug":"ci-tenant","brand":{"logoText":"C"},"isActive":True},token)
    assert status==201, tenant
    tenant_id=json_data(tenant)["id"]
    status, domain, _, _=request(f"/api/v1/admin/tenants/{tenant_id}/domains","POST",
        {"host":"ci.example.test","isPrimary":False},token)
    assert status==201 and json_data(domain).get("domains"), domain
    domain_id=json_data(domain)["domains"][-1]["id"]
    status, _, _, _=request(f"/api/v1/admin/tenants/{tenant_id}/domains/{domain_id}","DELETE",token=token)
    assert status==200, "tenant domain delete failed"

    status, product, _, _=request("/api/v1/admin/loan-products","POST",
        {"name":"CI Temporary Plan","slug":"ci-temporary-plan","description":"CI only","minAmount":1000,
         "maxAmount":5000,"intervalDays":30,"tiers":[{"months":3,"feePercent":1,"downPaymentPercent":0}],
         "conditions":{},"documents":[],"isActive":True},token)
    assert status==201, product
    product_id=json_data(product)["id"]
    status, toggled, _, _=request(f"/api/v1/admin/loan-products/{product_id}/toggle","POST",{},token)
    assert status in (200,201) and json_data(toggled).get("isActive") is False, toggled
    status, _, _, _=request(f"/api/v1/admin/loan-products/{product_id}","DELETE",token=token)
    assert status==200, "temporary product delete failed"

    status, backup, _, _=request("/api/v1/admin/backups","POST",{},token)
    assert status==201 and backup.get("name"), backup
    status, _, backup_bytes, ctype=request("/api/v1/admin/backups/"+backup["name"],token=token)
    assert status==200 and b'"previewOnly": true' in backup_bytes and "application/json" in ctype, (status,ctype)
    print("PASS: contract templates, contracts, ledger, tenant domains, product actions, backups")

def check_multipart_and_public_forms(token):
    boundary="----DigitalPayPreviewBoundary7MA4YWxkTrZu0gW"
    parts=[
        b"--"+boundary.encode()+b"\r\nContent-Disposition: form-data; name=\"kind\"\r\n\r\nNational ID\r\n",
        b"--"+boundary.encode()+b"\r\nContent-Disposition: form-data; name=\"file\"; filename=\"sample.png\"\r\nContent-Type: image/png\r\n\r\npreview-image-bytes\r\n",
        b"--"+boundary.encode()+b"--\r\n"
    ]
    status, uploaded, _, _=request("/api/v1/me/documents","POST",raw_body=b"".join(parts),
        content_type="multipart/form-data; boundary="+boundary,token=token)
    assert status==201, uploaded
    doc=json_data(uploaded); doc_id=doc["id"]
    status, docs, _, _=request("/api/v1/me/documents",token=token)
    assert status==200 and any(d.get("id")==doc_id for d in json_data(docs)), docs
    status, _, file_bytes, ctype=request(f"/api/v1/me/documents/{doc_id}/file",token=token)
    assert status==200 and file_bytes==b"preview-image-bytes", (status,ctype,file_bytes)
    status, support, _, _=request("/api/v1/public/support-tickets","POST",
        {"name":"CI Preview","phone":"09000000002","subject":"Test ticket","message":"Preview smoke test"})
    assert status==201, support
    status, partner, _, _=request("/api/v1/public/partnership-applications","POST",
        {"name":"CI Partner","phone":"09000000003","kind":"merchant","company":"CI Co","message":"Preview test"})
    assert status==201, partner
    print("PASS: document multipart upload/list/download and public support/partner forms")

def check_password_recovery():
    status,captcha,_,_=request("/api/v1/security/captcha")
    assert status==200 and captcha.get("image") and captcha.get("id"), captcha
    decoded=captcha["image"].split(",",1)[1]
    svg=__import__("urllib.parse",fromlist=["unquote"]).unquote(decoded)
    match=re.search(r">(\d{5})</text>",svg)
    assert match, "Could not read test captcha SVG"
    captcha_answer=match.group(1)
    phone="09000000000"
    status,otp,_,_=request("/api/v1/security/otp/request","POST",
        {"phone":phone,"purpose":"reset","captchaId":captcha["id"],"captchaAnswer":captcha_answer})
    assert status==200, otp
    status,ver,_,_=request("/api/v1/security/otp/verify","POST",{"phone":phone,"purpose":"reset","code":"123456"})
    assert status==200 and ver.get("ticket"), ver
    status,reset,_,_=request("/api/v1/security/password/reset","POST",
        {"ticket":ver["ticket"],"password":"CI-new-pass-2030"})
    assert status==200, reset
    status,captcha2,_,_=request("/api/v1/security/captcha")
    svg2=__import__("urllib.parse",fromlist=["unquote"]).unquote(captcha2["image"].split(",",1)[1])
    answer2=re.search(r">(\d{5})</text>",svg2).group(1)
    status,login,_,_=request("/api/v1/security/login","POST",
        {"username":phone,"password":"CI-new-pass-2030","captchaId":captcha2["id"],"captchaAnswer":answer2})
    assert status==200 and ((login.get("data") or {}).get("accessToken")), login
    print("PASS: development OTP and password recovery flow")

def main():
    check_pages()
    check_inline_javascript()
    check_api_and_beta()
    phone,password,token=check_auth_and_admin_routes()
    check_admin_module_mutations(token)
    check_multipart_and_public_forms(token)
    check_password_recovery()
    print("ALL PREVIEW SMOKE TESTS PASSED")

if __name__=="__main__":
    main()
