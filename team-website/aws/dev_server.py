"""Local test server: runs the real Lambda handler against the real AWS resources.

Serves the static site from this repository, sends /api/* to aws/api/handler.py and
reads /files, /p and /content from the content bucket, so the admin page can be
tested on http://127.0.0.1:8766 before using the live site.

    uv run --no-project --with boto3 --with "botocore[crt]" python aws/dev_server.py

Needs a signed-in AWS profile (default: govassist) and the deployed stack.
"""

import http.server
import json
import mimetypes
import os
import pathlib
import secrets
import sys
import tempfile

import boto3

PROFILE = os.environ.get("AWS_PROFILE", "govassist")
REGION = os.environ.get("AWS_REGION", "ap-southeast-2")
STACK = os.environ.get("STACK_NAME", "govassist-website")
PORT = int(os.environ.get("PORT", "8766"))
SITE = pathlib.Path(__file__).resolve().parent.parent

session = boto3.Session(profile_name=PROFILE, region_name=REGION)
outputs = {o["OutputKey"]: o["OutputValue"]
           for o in session.client("cloudformation").describe_stacks(StackName=STACK)["Stacks"][0]["Outputs"]}

os.environ.update({
    "AWS_PROFILE": PROFILE, "AWS_REGION": REGION, "AWS_DEFAULT_REGION": REGION,
    "TABLE_NAME": outputs["TableName"], "CONTENT_BUCKET": outputs["ContentBucketName"],
    # A local-only signing secret: tokens from this server do not work on the live site.
    "TOKEN_SECRET": os.environ.get("TOKEN_SECRET", secrets.token_hex(32)),
})
# Saved to a temp file so a local test can create a session token for this server only.
pathlib.Path(tempfile.gettempdir(), "govassist-dev-token-secret").write_text(os.environ["TOKEN_SECRET"])
sys.path.insert(0, str(SITE / "aws" / "api"))
import handler  # noqa: E402

s3 = session.client("s3")


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(SITE), **kwargs)

    def _api(self, method):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8") if length else ""
        event = {
            "rawPath": self.path.split("?", 1)[0],
            "headers": {k.lower(): v for k, v in self.headers.items()},
            "body": body,
            "isBase64Encoded": False,
            "requestContext": {"http": {"method": method}},
        }
        result = handler.lambda_handler(event)
        data = result["body"].encode("utf-8")
        self.send_response(result["statusCode"])
        for k, v in result["headers"].items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _content(self):
        import urllib.parse
        key = urllib.parse.unquote(self.path.split("?", 1)[0].lstrip("/"))
        try:
            obj = s3.get_object(Bucket=outputs["ContentBucketName"], Key=key)
        except s3.exceptions.NoSuchKey:
            self.send_error(404)
            return
        except Exception:
            self.send_error(404)
            return
        data = obj["Body"].read()
        self.send_response(200)
        self.send_header("Content-Type", obj.get("ContentType") or mimetypes.guess_type(key)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith("/api/"):
            return self._api("GET")
        if self.path.startswith(("/files/", "/p/", "/content/")):
            return self._content()
        return super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/"):
            return self._api("POST")
        self.send_error(405)


if __name__ == "__main__":
    print(f"Serving {SITE} with the live table {outputs['TableName']} on http://127.0.0.1:{PORT}")
    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
