# How the GovAssist website is deployed on AWS

This covers what runs where, why we chose each service, how an upload becomes a permanent page, and how the hosting stays free.

## The short version

The website is a set of static pages. They are stored in a private **Amazon S3** bucket and served to the world by **Amazon CloudFront** over HTTPS. The admin features (sign in, upload, publish) are handled by a small Python backend on **AWS Lambda**. Uploaded presentations go into a second, **versioned S3 bucket**. Records of every deliverable, version and file are kept in **Amazon DynamoDB**. All of it is described in one **CloudFormation** template, `aws/template.yaml`, so the whole setup can be recreated with one command.

```
Browser ──HTTPS──► CloudFront ──┬─► S3 site bucket       (HTML, CSS, JS, decks)
                                ├─► S3 content bucket    (/files, /p, /content)
                                └─► Lambda function URL  (/api/*)
                                         │
                                         ├─► DynamoDB  (users, deliverables, versions, file details)
                                         └─► S3 content bucket (checks uploads, writes pages)

Browser ──HTTPS PUT (presigned URL)──► S3 content bucket   (the actual file upload)
```

Region: **ap-southeast-2 (Sydney)**, the Region of our AWS project. CloudFront is global, so the site is served from edge locations close to the visitor, including India.

## What each service does and why

| Service | What it does for us | Why this choice |
|---|---|---|
| S3 site bucket | Holds the static pages, CSS, JS and the PPTX decks | Cheapest way to store a static site. The bucket is private; only CloudFront can read it. |
| CloudFront | Public HTTPS address, caching, routes `/api/*` to Lambda and `/files`, `/p`, `/content` to the content bucket | Gives HTTPS for free (needed by the Office viewer that shows our decks) and keeps both buckets private. |
| Lambda (Python 3.13) | The backend: authentication, upload links, file checks, publishing, version records | Runs only when someone uses the admin page, so it costs nothing while idle. The brief asks for a backend on a compute service we configure; this is it. |
| Lambda function URL with CloudFront origin access control | Connects CloudFront to Lambda | Only our CloudFront distribution can call the function. CloudFront signs every request (SigV4). |
| S3 content bucket (versioning on) | Uploaded files, generated permanent pages and the public list of published material | Versioning means even an overwritten object keeps its old copy. HTTPS is enforced by a bucket policy. |
| DynamoDB table | Admin login (salt + hash only), deliverables, versions, file sizes, types and checksums | Always-free tier, no server to run. Small provisioned capacity (2 reads, 2 writes per second) stays in the free tier. |
| CloudFormation | Creates and updates everything above from `aws/template.yaml` | Infrastructure as code: repeatable, reviewable in git, and easy to explain. |
| CloudWatch Logs | Lambda logs, kept for 14 days | For debugging. Short retention keeps storage tiny. |

## How the admin flow works

1. **Open the site** in a clean browser window: `https://<our CloudFront address>/`.
2. **Sign in** at `/admin.html`. The browser sends the username and password to `POST /api/login`. Lambda reads the user's record from DynamoDB, hashes the typed password with PBKDF2-SHA256 (210,000 rounds, random salt) and compares it with the stored hash. If they match it returns a session token signed with HMAC-SHA256, valid for 8 hours. Five wrong attempts lock the login for 15 minutes.
3. **Drag and drop** a file or a whole folder. The browser reads folders recursively and keeps their structure.
4. **Upload.** The browser asks `POST /api/uploads` for permission. Lambda checks the token, the file count and sizes, records the upload in DynamoDB, and returns one **presigned S3 URL** per file. A presigned URL is a one-hour, single-file upload link signed with the function's own credentials. The browser then uploads each file **directly to S3**, so large files never pass through Lambda.
5. **Enter the details**: title, presentation version, date, authors and change summary.
6. **Publish.** `POST /api/publish` makes Lambda:
   - check that every file really arrived in S3 and record its size, type and checksum (ETag);
   - refuse a version number that already exists for that deliverable;
   - write a new HTML page to `/p/<deliverable>/v<number>.html` using an S3 conditional write, so an existing page can never be overwritten;
   - save the version record in DynamoDB in one transaction;
   - rebuild `/p/<deliverable>.html` (all versions) and `/content/index.json`, which the Archive page reads.
7. The new page appears in the **Archive** with its version, date and authors. Older versions keep their own pages.

## Security points worth mentioning

- No AWS keys are stored anywhere in the site. Lambda gets temporary credentials from its IAM role, which only allows reading and writing our table and the `files/`, `p/` and `content/` folders of the content bucket (least privilege).
- Both buckets block all public access. Visitors read them only through CloudFront.
- The Lambda function URL can only be called by our CloudFront distribution.
- Passwords are never stored. The admin password is set with `aws/set-admin-password.ps1`, which hashes it on the team member's own computer and stores only the salt and hash.
- Uploaded HTML or other unknown file types are served as downloads, so an uploaded file cannot run script on our domain.
- CloudFront adds security headers (HSTS, `nosniff`, frame protection) to every response.

## Cost (why it stays free)

Our AWS project is on the **Free plan**: $100 of credits that run until May 2027, and AWS does not charge a Free plan account beyond its credits. On top of that, everything we use has a free allowance far above a class project's traffic:

- CloudFront: 1 TB of data and 10 million requests a month free.
- Lambda: 1 million requests and 400,000 GB-seconds a month free.
- DynamoDB: 25 GB and 25 read/write capacity units free; we use 2 of each.
- S3: a few hundred MB of decks and uploads costs a fraction of a cent a month.

## Updating the site

```powershell
aws login --profile govassist          # if the 12-hour session has expired
./aws/deploy.ps1                       # deploys the stack and uploads the pages
./aws/set-admin-password.ps1           # set or reset the admin password
```

`deploy.ps1` packages the Lambda code, runs `aws cloudformation deploy`, syncs the static files to the site bucket and clears the CloudFront cache.
