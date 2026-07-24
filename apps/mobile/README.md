# AiPal Mobile (Flutter)

Package: `io.aipal.mvp` · version **2.4.3+21**

## Prerequisites

- Flutter SDK 3.16+
- Android SDK 35 for Play builds
- macOS + Xcode for iOS TestFlight

## Run

```bash
flutter pub get
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8102/api/v2
```

## Release Android AAB

```bash
flutter build appbundle --release \
  --dart-define=API_BASE_URL=https://43.160.220.9.sslip.io/api/v2
```

Output: `build/app/outputs/bundle/release/app-release.aab`

Upload to Play Internal testing (versionCode must exceed previous release; current **+13**).

## iOS TestFlight

Build on macOS:

```bash
flutter build ipa --release
```

See [fastlane/Fastfile](fastlane/Fastfile) for CI automation.
