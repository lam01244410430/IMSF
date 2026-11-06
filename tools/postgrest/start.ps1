$ErrorActionPreference = 'Stop'
$composePath = Join-Path $PSScriptRoot 'compose.yaml'
$envPath = Join-Path $PSScriptRoot '.env.local'
if (!(Test-Path -LiteralPath $envPath)) {
    $random = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $bytes = New-Object byte[] 32
        $random.GetBytes($bytes)
        $dbPassword = [BitConverter]::ToString($bytes).Replace('-', '')
        $random.GetBytes($bytes)
        $apiPassword = [BitConverter]::ToString($bytes).Replace('-', '')
    } finally {
        $random.Dispose()
    }
    [System.IO.File]::WriteAllLines($envPath, @("REST_DB_PASSWORD=$dbPassword", "REST_API_PASSWORD=$apiPassword"))
}
docker compose --project-name family-rest-smoke --env-file $envPath -f $composePath up -d --wait
if ($LASTEXITCODE -ne 0) { throw 'PostgREST sandbox startup failed' }
Write-Output 'PostgREST sandbox is available at http://127.0.0.1:3033'
