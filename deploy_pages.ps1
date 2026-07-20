$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (git status --porcelain) {
    throw "Commit project changes before deploying GitHub Pages."
}

$commit = (git subtree split --prefix webapp).Trim()
if (-not $commit) {
    throw "Could not create a webapp subtree commit."
}

git push origin "${commit}:gh-pages" --force-with-lease
if ($LASTEXITCODE -ne 0) {
    throw "Could not update the gh-pages branch."
}

Write-Host "GitHub Pages branch updated: $commit"
