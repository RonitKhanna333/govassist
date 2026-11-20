<#
  Sets (or resets) the password for an admin login on the GovAssist website.

  The password is typed here, hashed on this computer with PBKDF2-SHA256
  (210,000 iterations, random salt) and only the salt and hash are stored in
  DynamoDB. The plain password never leaves this computer.

  Usage:  ./aws/set-admin-password.ps1               (sets the "admin" login)
          ./aws/set-admin-password.ps1 -Username ronit
#>
param(
    [string] $Username = "admin",
    [string] $ProfileName = "govassist",
    [string] $Region = "ap-southeast-2",
    [string] $TableName = "govassist-website"
)

$ErrorActionPreference = "Stop"
$env:Path = "$env:LOCALAPPDATA\Programs\Amazon\AWSCLIV2;$env:Path"
$Username = $Username.ToLowerInvariant()
if ($Username -notmatch '^[a-z0-9._-]{1,40}$') { throw "Use letters, numbers, dot, dash or underscore for the username." }

function Read-Plain([string] $prompt) {
    $secure = Read-Host $prompt -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}

$first = Read-Plain "New password for '$Username' (at least 12 characters)"
if ($first.Length -lt 12) { throw "The password must be at least 12 characters." }
$second = Read-Plain "Type the same password again"
if ($first -ne $second) { throw "The two passwords do not match. Nothing was changed." }

$iterations = 210000
$salt = New-Object byte[] 16
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($salt)
$kdf = New-Object System.Security.Cryptography.Rfc2898DeriveBytes($first, $salt, $iterations, [System.Security.Cryptography.HashAlgorithmName]::SHA256)
$hash = $kdf.GetBytes(32)
$kdf.Dispose()
$first = $null; $second = $null

$item = @{
    pk          = @{ S = "USER#$Username" }
    sk          = @{ S = "PROFILE" }
    salt        = @{ S = [Convert]::ToBase64String($salt) }
    hash        = @{ S = [Convert]::ToBase64String($hash) }
    iterations  = @{ N = "$iterations" }
    failedCount = @{ N = "0" }
    updatedAt   = @{ S = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ") }
} | ConvertTo-Json -Compress

$file = Join-Path ([System.IO.Path]::GetTempPath()) "govassist-admin-$([guid]::NewGuid()).json"
try {
    [System.IO.File]::WriteAllText($file, $item)
    & aws dynamodb put-item --table-name $TableName --item "file://$file" --profile $ProfileName --region $Region
    if ($LASTEXITCODE -ne 0) { throw "Saving the password failed. Are you signed in? Run: aws login --profile $ProfileName" }
} finally {
    Remove-Item $file -ErrorAction SilentlyContinue
}
Write-Host "Password saved for '$Username'. Sign in at /admin.html on the website."
