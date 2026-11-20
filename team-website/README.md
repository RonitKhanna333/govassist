# GovAssist Project Website

Project website for GovAssist, our UCS503 Software Engineering project: a web app that checks eligibility for government schemes and shows the official rule behind each result.

**Production:** hosted on AWS (S3 + CloudFront, admin API on Lambda). See [DEPLOYMENT.md](DEPLOYMENT.md). The earlier Vercel copy was [se-proj-gamma.vercel.app](https://se-proj-gamma.vercel.app/).

## Website structure

```text
index.html                         GovAssist overview, team, members and roles
planning-presentation.html         Planning Presentation v1 (kept unchanged)
planning-v2.html                   Planning Presentation v2 (separate page)
prototype-presentation.html        Prototype presentation page
final-presentation.html            Final presentation, test results and demo steps
presentations.html                 Archive of every presentation and version
changelog.html                     Change log for the app, website, report and decks
admin.html                         Admin sign-in, drag-and-drop upload and publishing
404.html                           Not-found page
members/member1.html ... 3.html    Member profiles and responsibilities
projects/project1.html ... 4.html  The four project proposals
data/team-data.json                Team, planning and change-log content
js/data.js                         Fetches and validates the JSON
js/render.js                       Renders the data-driven pages
js/admin.js                        Admin upload and publish page
js/site.js                         Responsive navigation
css/style.css                      Shared responsive styles
aws/template.yaml                  CloudFormation: S3, CloudFront, Lambda, DynamoDB
aws/api/handler.py                 Lambda backend: auth, uploads, versions, publishing
aws/deploy.ps1                     Deploys the stack and uploads the site
aws/set-admin-password.ps1         Sets an admin password (only a hash is stored)
aws/dev_server.py                  Local test server against the deployed resources
```

## Planning presentations

`planning-presentation.html` is Planning Presentation v1 and is never changed. The plan was updated in November 2026 and published as `planning-v2.html`. Both pages read from `data/team-data.json` (`planningPresentation` and `planningPresentationV2`).

## Content workflow

Team and planning content lives in `data/team-data.json`. New presentations and demonstrations are published from `admin.html`: sign in, drop a file or folder, enter the title, version, date and change summary, and publish. Each version gets a permanent page under `/p/`, and the Archive page lists them all.

## Local preview

```bash
python -m http.server 8000
```

Open `http://localhost:8000/`. Microsoft Office Viewer requires a public URL, so local pages show a presentation placeholder while retaining the direct PPTX download. The admin page needs the API; use `uv run --no-project --with boto3 --with "botocore[crt]" python aws/dev_server.py` to test it locally.

## Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md). In short: `./aws/deploy.ps1` with a signed-in AWS profile.

## Team

| Member | Ownership |
|---|---|
| Bhavneet | Team lead, backend and cloud |
| Ronit | Algorithms and rules |
| Shreyas | Frontend and integration |
