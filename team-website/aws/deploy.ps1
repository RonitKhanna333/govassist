<#
  Deploys the GovAssist project website to AWS.

    1. Makes sure a private "deploy" bucket exists for the packaged Lambda code.
    2. Packages aws/api into a zip and uploads it (aws cloudformation package).
    3. Creates or updates the CloudFormation stack in template.yaml.
    4. Copies the static site into the site bucket (aws s3 sync).
    5. Clears the CloudFront cache so visitors see the new pages.

  Usage (from any folder):  ./aws/deploy.ps1
  Needs the AWS CLI and a signed-in profile:  aws login --profile govassist
#>
param(
    [string] $ProfileName = "govassist",
    [string] $Region = "ap-southeast-2",
    [string] $StackName = "govassist-website"
)

$ErrorActionPreference = "Stop"
$env:Path = "$env:LOCALAPPDATA\Programs\Amazon\AWSCLIV2;$env:USERPROFILE\.local\bin;$env:Path"
$awsArgs = @("--profile", $ProfileName, "--region", $Region)

function Invoke-Aws {
    $output = & aws @args @awsArgs 2>&1
    if ($LASTEXITCODE -ne 0) { throw "aws $($args -join ' ') failed:`n$output" }
    return $output
}

$here = $PSScriptRoot
$site = Split-Path $here -Parent
$account = (Invoke-Aws sts get-caller-identity --query Account --output text).Trim()
$deployBucket = "govassist-deploy-$account-$Region"
Write-Host "Account $account, Region $Region, stack $StackName"

# 1. Deploy bucket for the Lambda package
& aws s3api head-bucket --bucket $deployBucket @awsArgs 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Creating deploy bucket $deployBucket"
    Invoke-Aws s3api create-bucket --bucket $deployBucket --create-bucket-configuration "LocationConstraint=$Region" | Out-Null
    Invoke-Aws s3api put-public-access-block --bucket $deployBucket --public-access-block-configuration "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true" | Out-Null
}

# 2. Session-token secret: generated once, then CloudFormation keeps the previous value
$overrides = @()
& aws cloudformation describe-stacks --stack-name $StackName @awsArgs 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    $bytes = New-Object byte[] 48
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $secret = -join ($bytes | ForEach-Object { $_.ToString("x2") })
    $overrides = @("--parameter-overrides", "TokenSecret=$secret")
    Write-Host "New stack: generated a fresh session-token secret"
}

# 3. Package and deploy the stack
$packaged = Join-Path ([System.IO.Path]::GetTempPath()) "govassist-packaged.yaml"
Push-Location $here
try {
    Invoke-Aws cloudformation package --template-file template.yaml --s3-bucket $deployBucket --s3-prefix lambda --output-template-file $packaged | Out-Null
    Write-Host "Deploying stack (a new stack takes about 5 minutes while CloudFront is created)..."
    & aws cloudformation deploy --template-file $packaged --stack-name $StackName --capabilities CAPABILITY_IAM --no-fail-on-empty-changeset @overrides @awsArgs
    if ($LASTEXITCODE -ne 0) { throw "Stack deployment failed. See the CloudFormation events in the console." }
} finally {
    Pop-Location
    Remove-Item $packaged -ErrorAction SilentlyContinue
}

$outputs = @{}
(Invoke-Aws cloudformation describe-stacks --stack-name $StackName --query "Stacks[0].Outputs" --output json | ConvertFrom-Json) |
    ForEach-Object { $outputs[$_.OutputKey] = $_.OutputValue }

# 4. Static site
Write-Host "Uploading the static site to $($outputs.SiteBucketName)"
Invoke-Aws s3 sync $site "s3://$($outputs.SiteBucketName)" --delete `
    --exclude ".git/*" --exclude ".gitignore" --exclude ".claude/*" --exclude "aws/*" --exclude "node_modules/*" `
    --exclude "README.md" --exclude "DEPLOYMENT.md" --exclude "vercel.json" --exclude "*.log" `
    --cache-control "public, max-age=300" | Out-Null

# An empty published-material index, only if nothing has been published yet
& aws s3api head-object --bucket $outputs.ContentBucketName --key content/index.json @awsArgs 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    $empty = Join-Path ([System.IO.Path]::GetTempPath()) "govassist-index.json"
    '{"generatedAt": null, "deliverables": []}' | Set-Content -Path $empty -Encoding ascii
    Invoke-Aws s3 cp $empty "s3://$($outputs.ContentBucketName)/content/index.json" --content-type application/json --cache-control "public, max-age=30" | Out-Null
    Remove-Item $empty
}

# 5. Clear the CDN cache
Invoke-Aws cloudfront create-invalidation --distribution-id $outputs.DistributionId --paths "/*" | Out-Null

Write-Host ""
Write-Host "Done. Website: $($outputs.WebsiteUrl)"
Write-Host "Admin page:    $($outputs.WebsiteUrl)/admin.html"
