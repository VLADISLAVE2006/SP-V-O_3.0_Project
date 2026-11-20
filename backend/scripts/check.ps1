param(
    [string]$ProjectName = 'codex-polls-er4'
)

$ErrorActionPreference = 'Stop'
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    $checks = @(
        @{ Name = 'Django configuration'; Args = @('python', 'manage.py', 'check') },
        @{ Name = 'Pending model changes'; Args = @('python', 'manage.py', 'makemigrations', '--check', '--dry-run') },
        @{ Name = 'Code checks'; Args = @('python', '-m', 'ruff', 'check', '.') },
        @{ Name = 'Code formatting'; Args = @('python', '-m', 'ruff', 'format', '--check', '.') },
        @{ Name = 'OpenAPI validation'; Args = @('python', 'manage.py', 'spectacular', '--validate', '--fail-on-warn', '--file', '/tmp/checked-schema.yaml') },
        @{ Name = 'Automated tests'; Args = @('python', 'manage.py', 'test', '--verbosity', '2') }
    )
    foreach ($check in $checks) {
        Write-Host "Checking: $($check.Name)"
        $arguments = @('compose', '-p', $ProjectName, 'exec', '-T', 'backend') + $check.Args
        & docker @arguments
        if ($LASTEXITCODE -ne 0) { throw "Failed: $($check.Name) (exit $LASTEXITCODE)" }
    }
    Write-Host 'All checks passed.'
}
finally {
    Pop-Location
}
