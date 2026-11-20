"""GovAssist project website API (AWS Lambda, Python 3.13).

CloudFront sends every /api/* request here through a Lambda function URL that only
CloudFront can call (origin access control). The function:

  * signs the admin in (PBKDF2 password hash stored in DynamoDB, signed session token),
  * hands out short-lived presigned S3 URLs so the browser uploads files straight to S3,
  * checks the uploaded files and records their details in DynamoDB,
  * publishes a new version as a permanent HTML page in S3, and
  * keeps every version: nothing is ever overwritten or deleted by this API.
"""

import base64
import datetime as dt
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import time
import urllib.parse
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key
from botocore.config import Config
from botocore.exceptions import ClientError

REGION = os.environ.get("AWS_REGION", "ap-southeast-2")
TABLE_NAME = os.environ["TABLE_NAME"]
CONTENT_BUCKET = os.environ["CONTENT_BUCKET"]
TOKEN_SECRET = os.environ["TOKEN_SECRET"].encode()

TOKEN_HOURS = 8
MAX_FILES = 300
MAX_FILE_BYTES = 200 * 1024 * 1024
MAX_TOTAL_BYTES = 500 * 1024 * 1024
LOCK_AFTER = 5
LOCK_MINUTES = 15
UPLOAD_TTL_DAYS = 7
TEAM = ["Ronit", "Bhavneet", "Shreyas"]
KINDS = ["Presentation", "Demonstration", "Report", "Other"]

table = boto3.resource("dynamodb", region_name=REGION).Table(TABLE_NAME)
s3 = boto3.client(
    "s3",
    region_name=REGION,
    endpoint_url=f"https://s3.{REGION}.amazonaws.com",
    config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
)

# Types the browser may show inline. Anything else is served as a download so an
# uploaded HTML or SVG file can never run script on the site's own domain.
INLINE_TYPES = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "mp4": "video/mp4",
    "webm": "video/webm",
    "txt": "text/plain; charset=utf-8",
    "md": "text/plain; charset=utf-8",
    "csv": "text/csv; charset=utf-8",
    "json": "application/json",
}
DOWNLOAD_TYPES = {
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "ppt": "application/vnd.ms-powerpoint",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "doc": "application/msword",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "zip": "application/zip",
    "drawio": "application/octet-stream",
}
OFFICE_EXT = {"pptx", "ppt", "docx", "doc", "xlsx"}
IMAGE_EXT = {"png", "jpg", "jpeg", "gif", "webp"}
VIDEO_EXT = {"mp4", "webm"}


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


# ---------------------------------------------------------------- helpers

def _json_default(value):
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    raise TypeError(f"Cannot serialise {type(value)}")


def respond(status, body):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", "Cache-Control": "no-store"},
        "body": json.dumps(body, default=_json_default),
    }


def b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def b64url_decode(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def now_iso():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def read_body(event):
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    if not raw:
        return {}
    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        raise ApiError(400, "The request body is not valid JSON.")
    if not isinstance(body, dict):
        raise ApiError(400, "The request body must be a JSON object.")
    return body


def text_field(body, name, max_len, required=True, pattern=None):
    value = body.get(name, "")
    if not isinstance(value, str):
        raise ApiError(400, f"{name} must be text.")
    value = value.strip()
    if required and not value:
        raise ApiError(400, f"{name} is required.")
    if len(value) > max_len:
        raise ApiError(400, f"{name} must be at most {max_len} characters.")
    if value and pattern and not re.fullmatch(pattern, value):
        raise ApiError(400, f"{name} has characters that are not allowed.")
    return value


def slugify(text):
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60].strip("-") or "deliverable"


def clean_path(path):
    """Keep a folder-relative path but drop anything that could escape the upload."""
    if not isinstance(path, str):
        raise ApiError(400, "Each file needs a path.")
    parts = []
    for part in path.replace("\\", "/").split("/"):
        part = part.strip()
        if part in ("", ".", ".."):
            continue
        part = re.sub(r"[^A-Za-z0-9 ._()\-]", "_", part)[:120]
        parts.append(part)
    if not parts:
        raise ApiError(400, "A file path is empty.")
    cleaned = "/".join(parts)
    if len(cleaned) > 400:
        raise ApiError(400, "A file path is too long.")
    return cleaned


def file_type(path):
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    if ext in INLINE_TYPES:
        return ext, INLINE_TYPES[ext], None
    name = path.rsplit("/", 1)[-1].replace('"', "")
    return ext, DOWNLOAD_TYPES.get(ext, "application/octet-stream"), f'attachment; filename="{name}"'


def display_date(iso_date):
    day = dt.date.fromisoformat(iso_date)
    return f"{day.day} {day.strftime('%B %Y')}"


def files_url(key):
    return "/" + urllib.parse.quote(key)


# ---------------------------------------------------------------- auth

def hash_password(password, salt, iterations):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, dklen=32)


def make_token(username):
    payload = {"sub": username, "iat": int(time.time()), "exp": int(time.time()) + TOKEN_HOURS * 3600}
    body = b64url(json.dumps(payload, separators=(",", ":")).encode())
    sig = b64url(hmac.new(TOKEN_SECRET, body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}", payload["exp"]


def require_admin(event):
    headers = event.get("headers") or {}
    token = headers.get("x-admin-token", "")
    try:
        body, sig = token.split(".", 1)
        expected = b64url(hmac.new(TOKEN_SECRET, body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            raise ValueError
        payload = json.loads(b64url_decode(body))
        if payload["exp"] < time.time():
            raise ValueError
        return payload["sub"]
    except Exception:
        raise ApiError(401, "Please sign in again.")


def login(event):
    body = read_body(event)
    username = text_field(body, "username", 40, pattern=r"[A-Za-z0-9._-]+").lower()
    password = body.get("password", "")
    if not isinstance(password, str) or not password or len(password) > 200:
        raise ApiError(400, "Enter your password.")

    item = table.get_item(Key={"pk": f"USER#{username}", "sk": "PROFILE"}).get("Item")
    if not item:
        hash_password(password, b"no-such-user-salt", 210000)  # same work either way
        raise ApiError(401, "Wrong username or password.")

    locked_until = int(item.get("lockedUntil", 0))
    if locked_until > time.time():
        minutes = max(1, int((locked_until - time.time()) // 60) + 1)
        raise ApiError(429, f"Too many failed attempts. Try again in {minutes} minutes.")

    salt = base64.b64decode(item["salt"])
    expected = base64.b64decode(item["hash"])
    if not hmac.compare_digest(hash_password(password, salt, int(item["iterations"])), expected):
        failed = int(item.get("failedCount", 0)) + 1
        update = {"failedCount": 0 if failed >= LOCK_AFTER else failed}
        if failed >= LOCK_AFTER:
            update["lockedUntil"] = int(time.time()) + LOCK_MINUTES * 60
        table.update_item(
            Key={"pk": item["pk"], "sk": "PROFILE"},
            UpdateExpression="SET " + ", ".join(f"{k} = :{k}" for k in update),
            ExpressionAttributeValues={f":{k}": v for k, v in update.items()},
        )
        raise ApiError(401, "Wrong username or password.")

    table.update_item(
        Key={"pk": item["pk"], "sk": "PROFILE"},
        UpdateExpression="SET failedCount = :z, lastLogin = :t REMOVE lockedUntil",
        ExpressionAttributeValues={":z": 0, ":t": now_iso()},
    )
    token, expires = make_token(username)
    return respond(200, {"token": token, "expires": expires, "username": username})


# ---------------------------------------------------------------- uploads

def create_upload(event, user):
    body = read_body(event)
    files = body.get("files")
    if not isinstance(files, list) or not files:
        raise ApiError(400, "Choose at least one file.")
    if len(files) > MAX_FILES:
        raise ApiError(400, f"Upload at most {MAX_FILES} files at a time.")

    upload_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + secrets.token_hex(4)
    seen, records, total = set(), [], 0
    for entry in files:
        if not isinstance(entry, dict):
            raise ApiError(400, "Each file must be an object.")
        path = clean_path(entry.get("path"))
        if path in seen:
            raise ApiError(400, f"{path} appears twice.")
        seen.add(path)
        size = entry.get("size")
        if not isinstance(size, int) or size < 0 or size > MAX_FILE_BYTES:
            raise ApiError(400, f"{path} is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB.")
        total += size
        ext, content_type, disposition = file_type(path)
        records.append({"path": path, "key": f"files/{upload_id}/{path}", "size": size,
                        "contentType": content_type, "disposition": disposition or ""})
    if total > MAX_TOTAL_BYTES:
        raise ApiError(400, f"An upload can be at most {MAX_TOTAL_BYTES // (1024 * 1024)} MB in total.")

    table.put_item(Item={
        "pk": f"UPLOAD#{upload_id}", "sk": "META", "files": records, "createdBy": user,
        "createdAt": now_iso(), "expiresAt": int(time.time()) + UPLOAD_TTL_DAYS * 86400,
    }, ConditionExpression="attribute_not_exists(pk)")

    out = []
    for index, rec in enumerate(records):
        params = {"Bucket": CONTENT_BUCKET, "Key": rec["key"], "ContentType": rec["contentType"],
                  "CacheControl": "public, max-age=31536000, immutable"}
        headers = {"Content-Type": rec["contentType"], "Cache-Control": params["CacheControl"]}
        if rec["disposition"]:
            params["ContentDisposition"] = rec["disposition"]
            headers["Content-Disposition"] = rec["disposition"]
        url = s3.generate_presigned_url("put_object", Params=params, ExpiresIn=3600)
        out.append({"index": index, "path": rec["path"], "url": url, "headers": headers})
    return respond(201, {"uploadId": upload_id, "files": out})


# ---------------------------------------------------------------- publishing

def list_versions(slug):
    resp = table.query(KeyConditionExpression=Key("pk").eq(f"DELIV#{slug}") & Key("sk").begins_with("V#"),
                       ScanIndexForward=False)
    return resp.get("Items", [])


def all_deliverables():
    items, kwargs = [], {}
    while True:
        resp = table.scan(**kwargs)
        items.extend(resp.get("Items", []))
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    metas = {i["pk"][6:]: i for i in items if i["pk"].startswith("DELIV#") and i["sk"] == "META"}
    versions = {}
    for i in items:
        if i["pk"].startswith("DELIV#") and i["sk"].startswith("V#"):
            versions.setdefault(i["pk"][6:], []).append(i)
    result = []
    for slug, meta in metas.items():
        vs = sorted(versions.get(slug, []), key=lambda v: v["sk"], reverse=True)
        result.append({"slug": slug, "meta": meta, "versions": vs})
    result.sort(key=lambda d: d["versions"][0]["publishedAt"] if d["versions"] else "", reverse=True)
    return result


def public_version(v):
    return {"version": v["versionLabel"], "seq": int(v["seq"]), "date": v["displayDate"], "dateISO": v["date"],
            "authors": v["authors"], "changeSummary": v["changeSummary"], "url": v["pageUrl"],
            "publishedAt": v["publishedAt"]}


def put_page(key, page, overwrite):
    extra = {} if overwrite else {"IfNoneMatch": "*"}
    try:
        s3.put_object(Bucket=CONTENT_BUCKET, Key=key, Body=page.encode("utf-8"),
                      ContentType="text/html; charset=utf-8",
                      CacheControl="public, max-age=60" if overwrite else "public, max-age=3600", **extra)
    except ClientError as err:
        if err.response["Error"]["Code"] in ("PreconditionFailed", "ConditionalRequestConflict"):
            raise ApiError(409, "That version page already exists and will not be overwritten.")
        raise


def rebuild_indexes(slug=None):
    data = all_deliverables()
    index = {"generatedAt": now_iso(), "deliverables": []}
    for d in data:
        index["deliverables"].append({
            "slug": d["slug"], "title": d["meta"]["title"], "kind": d["meta"]["kind"],
            "url": f"/p/{d['slug']}.html", "versions": [public_version(v) for v in d["versions"]],
        })
        if slug is None or d["slug"] == slug:
            put_page(f"p/{d['slug']}.html", render_versions_page(d), overwrite=True)
    s3.put_object(Bucket=CONTENT_BUCKET, Key="content/index.json",
                  Body=json.dumps(index, default=_json_default, indent=2).encode("utf-8"),
                  ContentType="application/json", CacheControl="public, max-age=30")
    return index


def publish(event, user):
    body = read_body(event)
    upload_id = text_field(body, "uploadId", 40, pattern=r"[0-9]{14}-[0-9a-f]{8}")
    title = text_field(body, "title", 120)
    version = text_field(body, "version", 20, pattern=r"[A-Za-z0-9 ._\-]+")
    date = text_field(body, "date", 10, pattern=r"\d{4}-\d{2}-\d{2}")
    try:
        shown_date = display_date(date)
    except ValueError:
        raise ApiError(400, "date is not a real date.")
    summary = text_field(body, "changeSummary", 2000)
    kind = body.get("kind", "Presentation")
    if kind not in KINDS:
        raise ApiError(400, "kind is not one of the allowed types.")
    authors = body.get("authors") or TEAM
    if (not isinstance(authors, list) or not 1 <= len(authors) <= 10
            or not all(isinstance(a, str) and 0 < len(a.strip()) <= 60 for a in authors)):
        raise ApiError(400, "authors must be a list of names.")
    authors = [a.strip() for a in authors]

    upload = table.get_item(Key={"pk": f"UPLOAD#{upload_id}", "sk": "META"}).get("Item")
    if not upload:
        raise ApiError(400, "That upload was not found. Upload the files again.")
    if upload.get("publishedAs"):
        raise ApiError(409, "These files are already published.")

    files, total = [], 0
    for rec in upload["files"]:
        try:
            head = s3.head_object(Bucket=CONTENT_BUCKET, Key=rec["key"])
        except ClientError:
            raise ApiError(400, f"{rec['path']} did not finish uploading.")
        size = head["ContentLength"]
        if size > MAX_FILE_BYTES:
            raise ApiError(400, f"{rec['path']} is too large.")
        total += size
        files.append({"path": rec["path"], "key": rec["key"], "size": size, "contentType": rec["contentType"],
                      "etag": head["ETag"].strip('"'), "download": bool(rec.get("disposition"))})
    if total > MAX_TOTAL_BYTES:
        raise ApiError(400, "The upload is too large in total.")
    files.sort(key=lambda f: f["path"].lower())

    existing_slug = body.get("slug")
    if existing_slug:
        slug = text_field(body, "slug", 60, pattern=r"[a-z0-9-]+")
        meta = table.get_item(Key={"pk": f"DELIV#{slug}", "sk": "META"}).get("Item")
        if not meta:
            raise ApiError(400, "That deliverable does not exist.")
    else:
        slug, meta, n = slugify(title), None, 1
        base = slug
        while table.get_item(Key={"pk": f"DELIV#{slug}", "sk": "META"}).get("Item"):
            n += 1
            slug = f"{base[:56]}-{n}"

    versions = list_versions(slug)
    if any(v["versionLabel"].lower() == version.lower() for v in versions):
        raise ApiError(409, f"Version {version} already exists. Use a new version number; old versions are kept.")
    seq = (int(versions[0]["seq"]) + 1) if versions else 1

    primary = body.get("primaryPath") or pick_primary(files)
    if primary and primary not in {f["path"] for f in files}:
        raise ApiError(400, "The main file is not part of this upload.")

    page_key = f"p/{slug}/v{seq}.html"
    record = {
        "pk": f"DELIV#{slug}", "sk": f"V#{seq:04d}", "seq": seq, "versionLabel": version, "title": title,
        "kind": kind if not meta else meta["kind"], "date": date, "displayDate": shown_date,
        "changeSummary": summary, "authors": authors, "files": files, "primaryPath": primary or "",
        "uploadId": upload_id, "pageKey": page_key, "pageUrl": f"/{page_key}",
        "publishedAt": now_iso(), "publishedBy": user,
    }
    put_page(page_key, render_version_page(slug, record, versions), overwrite=False)

    items = [{"Put": {"TableName": TABLE_NAME, "Item": record, "ConditionExpression": "attribute_not_exists(pk)"}}]
    if meta:
        items.append({"Update": {"TableName": TABLE_NAME, "Key": {"pk": f"DELIV#{slug}", "sk": "META"},
                                 "UpdateExpression": "SET latestSeq = :s, updatedAt = :t",
                                 "ExpressionAttributeValues": {":s": seq, ":t": record["publishedAt"]}}})
    else:
        items.append({"Put": {"TableName": TABLE_NAME, "ConditionExpression": "attribute_not_exists(pk)",
                              "Item": {"pk": f"DELIV#{slug}", "sk": "META", "title": title, "kind": kind,
                                       "createdAt": record["publishedAt"], "updatedAt": record["publishedAt"],
                                       "latestSeq": seq}}})
    items.append({"Update": {"TableName": TABLE_NAME, "Key": {"pk": f"UPLOAD#{upload_id}", "sk": "META"},
                             "UpdateExpression": "SET publishedAs = :p REMOVE expiresAt",
                             "ConditionExpression": "attribute_not_exists(publishedAs)",
                             "ExpressionAttributeValues": {":p": f"{slug}#{seq}"}}})
    try:
        table.meta.client.transact_write_items(TransactItems=items)
    except ClientError as err:
        if err.response["Error"]["Code"] == "TransactionCanceledException":
            raise ApiError(409, "Someone published the same thing at the same moment. Refresh and try again.")
        raise

    rebuild_indexes(slug)
    return respond(201, {"slug": slug, "version": version, "seq": seq, "url": record["pageUrl"],
                         "allVersionsUrl": f"/p/{slug}.html"})


def pick_primary(files):
    for exts in (("pptx", "ppt"), ("pdf",), tuple(IMAGE_EXT), tuple(VIDEO_EXT), ("docx", "doc", "xlsx")):
        for f in files:
            if f["path"].rsplit(".", 1)[-1].lower() in exts:
                return f["path"]
    return None


def list_for_admin(event, user):
    data = all_deliverables()
    out = []
    for d in data:
        out.append({"slug": d["slug"], "title": d["meta"]["title"], "kind": d["meta"]["kind"],
                    "url": f"/p/{d['slug']}.html",
                    "versions": [dict(public_version(v), files=v["files"], publishedBy=v["publishedBy"])
                                 for v in d["versions"]]})
    return respond(200, {"deliverables": out, "user": user})


# ---------------------------------------------------------------- page rendering

NAV = [("Overview", "/index.html"), ("Planning v1", "/planning-presentation.html"), ("Planning v2", "/planning-v2.html"),
       ("Prototype", "/prototype-presentation.html"), ("Final", "/final-presentation.html"),
       ("Archive", "/presentations.html"), ("Change log", "/changelog.html")]


def human_size(n):
    n = int(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def page_shell(title, description, hero, body):
    e = html.escape
    active = ' class="active"'
    nav = "".join(f'<a{active if label == "Archive" else ""} href="{href}">{label}</a>' for label, href in NAV)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="{e(description)}">
  <title>{e(title)} · GovAssist</title>
  <link rel="stylesheet" href="/css/style.css">
</head>
<body>
  <header class="site-header">
    <div class="nav-shell">
      <a class="wordmark" href="/index.html" aria-label="GovAssist home">
        <span class="wordmark-mark">GA</span>
        <span class="wordmark-copy"><strong>GovAssist</strong><small>UCS503 project website</small></span>
      </a>
      <button class="nav-toggle" type="button" aria-expanded="false" aria-controls="site-nav">Menu</button>
      <nav class="site-nav" id="site-nav" aria-label="Primary navigation">{nav}<a class="admin-link" href="/admin.html">Admin</a></nav>
    </div>
  </header>
  <main>
{hero}
{body}
  </main>
  <footer class="site-footer">
    <div class="container footer-main">
      <div class="footer-brand"><h2>GovAssist</h2><p>UCS503 software engineering project</p></div>
      <div class="footer-meta">
        <div><span>Course</span><strong>UCS503</strong></div>
        <div><span>Page</span><strong>{e(title)}</strong></div>
        <div><span>Team</span><strong>Ronit · Bhavneet · Shreyas</strong></div>
      </div>
    </div>
    <div class="container footer-bottom"><span>© 2026 GovAssist team</span><span>Published from the admin page</span></div>
  </footer>
  <script src="/js/site.js"></script>
</body>
</html>
"""


def render_embed(record):
    e = html.escape
    primary = record.get("primaryPath")
    if not primary:
        return ""
    f = next(x for x in record["files"] if x["path"] == primary)
    ext = primary.rsplit(".", 1)[-1].lower()
    url = files_url(f["key"])
    if ext in OFFICE_EXT:
        inner = (f'<iframe id="office-embed" title="{e(primary)}" allowfullscreen></iframe>'
                 f'<script>document.getElementById("office-embed").src = "https://view.officeapps.live.com/op/embed.aspx?src=" '
                 f'+ encodeURIComponent(location.origin + {json.dumps(url)});</script>')
    elif ext == "pdf":
        inner = f'<iframe src="{e(url)}" title="{e(primary)}"></iframe>'
    elif ext in IMAGE_EXT:
        return (f'<section class="container presentation-section"><div class="presentation-heading"><div>'
                f'<p class="eyebrow">Main file</p><h2>{e(primary)}</h2></div></div>'
                f'<img class="published-image" src="{e(url)}" alt="{e(record["title"])}"></section>')
    elif ext in VIDEO_EXT:
        inner = f'<video src="{e(url)}" controls preload="metadata"></video>'
    else:
        return ""
    return (f'<section class="container presentation-section"><div class="presentation-heading"><div>'
            f'<p class="eyebrow">Main file</p><h2>{e(primary)}</h2></div>'
            f'<a class="button button-secondary" href="{e(url)}" download>Download <span>↓</span></a></div>'
            f'<div class="embed-wrapper">{inner}</div></section>')


def render_version_page(slug, record, older_versions):
    e = html.escape
    authors = " · ".join(record["authors"])
    hero = f"""    <section class="planning-hero">
      <div class="container planning-hero-inner">
        <div>
          <p class="eyebrow light">UCS503 · {e(record['kind'])}</p>
          <h1 class="page-title">{e(record['title'])}</h1>
          <p class="page-lead">Permanent page for version {e(record['versionLabel'])}. Later versions get their own pages, so this one never changes.</p>
          <div class="hero-actions"><a class="button button-light" href="/p/{e(slug)}.html">All versions <span>→</span></a></div>
        </div>
        <aside>
          <ul class="page-meta planning-meta">
            <li><span>Version</span><strong>{e(record['versionLabel'])}</strong></li>
            <li><span>Date</span><strong>{e(record['displayDate'])}</strong></li>
            <li><span>Authors</span><strong>{e(authors)}</strong></li>
            <li><span>Files</span><strong>{len(record['files'])}</strong></li>
          </ul>
          <div class="plan-change"><span>Change summary</span><p>{e(record['changeSummary'])}</p></div>
        </aside>
      </div>
    </section>"""
    rows = "".join(
        f'<article class="file-row"><a href="{e(files_url(f["key"]))}"{" download" if f["download"] else ""}>{e(f["path"])}</a>'
        f'<span>{e(f["contentType"].split(";")[0])}</span><span>{human_size(f["size"])}</span></article>'
        for f in record["files"])
    history = "".join(
        f'<article class="version-row"><span class="version-name"><a href="{e(v["pageUrl"])}">{e(v["versionLabel"])}</a></span>'
        f'<span>{e(v["displayDate"])}</span><span>Earlier</span><p>{e(v["changeSummary"])}</p></article>'
        for v in older_versions)
    body = render_embed(record) + f"""
    <section class="section-block">
      <div class="container">
        <header class="section-header">
          <span class="section-number">01 · Files</span>
          <div><h2 class="section-title">Uploaded material</h2><p class="section-intro">Published {e(record['publishedAt'][:10])}. Folder structure is kept as uploaded.</p></div>
        </header>
        <div class="file-list">{rows}</div>
      </div>
    </section>
    <section class="section-block">
      <div class="container">
        <header class="section-header">
          <span class="section-number">02 · History</span>
          <div><h2 class="section-title">Earlier versions</h2><p class="section-intro">Versions that existed when this one was published. The <a class="text-link" href="/p/{e(slug)}.html">all versions</a> page always has the full list.</p></div>
        </header>
        <div class="version-list">{history or '<p class="archive-empty">This is the first version.</p>'}</div>
      </div>
    </section>"""
    return page_shell(f"{record['title']} {record['versionLabel']}", record["changeSummary"][:150], hero, body)


def render_versions_page(d):
    e = html.escape
    latest = d["versions"][0]
    hero = f"""    <section class="planning-hero">
      <div class="container planning-hero-inner">
        <div>
          <p class="eyebrow light">UCS503 · {e(d['meta']['kind'])}</p>
          <h1 class="page-title">{e(d['meta']['title'])}</h1>
          <p class="page-lead">Every published version of this deliverable. Each version keeps its own permanent page.</p>
          <div class="hero-actions"><a class="button button-light" href="{e(latest['pageUrl'])}">Open latest ({e(latest['versionLabel'])}) <span>→</span></a></div>
        </div>
        <aside>
          <ul class="page-meta planning-meta">
            <li><span>Latest version</span><strong>{e(latest['versionLabel'])}</strong></li>
            <li><span>Date</span><strong>{e(latest['displayDate'])}</strong></li>
            <li><span>Authors</span><strong>{e(' · '.join(latest['authors']))}</strong></li>
            <li><span>Versions</span><strong>{len(d['versions'])}</strong></li>
          </ul>
        </aside>
      </div>
    </section>"""
    rows = "".join(
        f'<article class="version-row"><span class="version-name"><a href="{e(v["pageUrl"])}">{e(v["versionLabel"])}</a></span>'
        f'<span>{e(v["displayDate"])}</span><span>{"Latest" if i == 0 else "Earlier"}</span><p>{e(v["changeSummary"])}</p></article>'
        for i, v in enumerate(d["versions"]))
    body = f"""
    <section class="section-block">
      <div class="container">
        <header class="section-header">
          <span class="section-number">01 · Versions</span>
          <div><h2 class="section-title">Version history</h2><p class="section-intro">Newest first. Nothing here is ever replaced or removed.</p></div>
        </header>
        <div class="version-list">{rows}</div>
      </div>
    </section>"""
    return page_shell(d["meta"]["title"], f"All versions of {d['meta']['title']}", hero, body)


# ---------------------------------------------------------------- router

def lambda_handler(event, context=None):
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    path = event.get("rawPath", "/")
    try:
        if path == "/api/health" and method == "GET":
            return respond(200, {"ok": True, "time": now_iso()})
        if path == "/api/login" and method == "POST":
            return login(event)
        user = require_admin(event)
        if path == "/api/me" and method == "GET":
            return respond(200, {"username": user})
        if path == "/api/deliverables" and method == "GET":
            return list_for_admin(event, user)
        if path == "/api/uploads" and method == "POST":
            return create_upload(event, user)
        if path == "/api/publish" and method == "POST":
            return publish(event, user)
        raise ApiError(400, "Unknown API route.")
    except ApiError as err:
        return respond(err.status, {"error": err.message})
    except Exception as err:  # keep details in the logs, not in the response
        print("Unhandled error:", repr(err))
        return respond(500, {"error": "Something went wrong on the server. Please try again."})
