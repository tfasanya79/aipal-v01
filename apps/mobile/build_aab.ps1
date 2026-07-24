# AiPal Android App Bundle Build Script
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host "   AiPal - Building Android App Bundle (.aab)" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host ""

# Set environment variables
$env:PATH = "$env:USERPROFILE\flutter\bin;$env:PATH"
$env:JAVA_HOME = "C:\Program Files\Java\jdk-17"
$env:PATH = "$env:JAVA_HOME\bin;$env:PATH"
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\sdk"
$env:PATH = "$env:ANDROID_HOME\cmdline-tools\latest\bin;$env:ANDROID_HOME\platform-tools;$env:PATH"

# Signing configuration
$env:AIPAL_RELEASE_STORE_FILE = "$PSScriptRoot\android\app\upload-keystore.jks"
$env:AIPAL_RELEASE_STORE_PASSWORD = "aipal2024"
$env:AIPAL_RELEASE_KEY_ALIAS = "upload"
$env:AIPAL_RELEASE_KEY_PASSWORD = "aipal2024"

Write-Host "[1/4] Cleaning previous builds..." -ForegroundColor Yellow
flutter clean

Write-Host "[2/4] Getting dependencies..." -ForegroundColor Yellow
flutter pub get

Write-Host "[3/4] Building Android App Bundle (Release)..." -ForegroundColor Yellow
Write-Host "      This may take 5-10 minutes..." -ForegroundColor Gray
flutter build appbundle --release --no-tree-shake-icons

Write-Host ""
Write-Host "==============================================" -ForegroundColor Green
Write-Host "   Build Complete!" -ForegroundColor Green
Write-Host "==============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Your .aab file is located at:" -ForegroundColor Cyan
Write-Host "build\app\outputs\bundle\release\app-release.aab" -ForegroundColor White
Write-Host ""
Write-Host "App Info:" -ForegroundColor Cyan
Write-Host "  - Package: io.aipal.mvp" -ForegroundColor White
Write-Host "  - Version: 2.4.3+24" -ForegroundColor White
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Cyan
Write-Host "  1. Go to Google Play Console (https://play.google.com/console)" -ForegroundColor White
Write-Host "  2. Select your app or create a new one" -ForegroundColor White
Write-Host "  3. Navigate to 'Testing' > 'Internal testing' or 'Closed testing'" -ForegroundColor White
Write-Host "  4. Create a new release and upload the .aab file" -ForegroundColor White
Write-Host ""
Write-Host "Keystore Info (save this safely!):" -ForegroundColor Yellow
Write-Host "  - Location: android\app\upload-keystore.jks" -ForegroundColor White
Write-Host "  - Password: aipal2024" -ForegroundColor White  
Write-Host "  - Alias: upload" -ForegroundColor White
Write-Host ""
