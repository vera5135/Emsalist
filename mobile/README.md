# Emsalist Mobile (P2.1)

iOS-first Flutter mobile shell for the Emsalist legal workspace. P2.1 delivers the
initial application shell with design system, navigation, chat composer, case drawer
mock, UYAP status mock, native iOS/Android flavors, and CI/test infrastructure.

## Environment

- Flutter 3.44.4 (stable channel)
- Dart 3.12.2

## Quick start

```powershell
cd mobile
flutter pub get
flutter run --flavor development
```

The app launches with mock data.

### Chrome preview

```powershell
# Terminal 1
cd ..
.\start-backend.ps1

# Terminal 2
cd mobile
flutter run -d chrome --web-port 5173 --dart-define=APP_ENVIRONMENT=development --dart-define=API_BASE_URL=http://127.0.0.1:8000
```

The backend allows `http://localhost:5173` and `http://127.0.0.1:5173` in local
development CORS defaults, including the PATCH preflights used by legal issue
actions.

## Flavors

Flavors are real native build flavors (iOS schemes/build configurations and Android
product flavors), selected with `--flavor`:

```powershell
# Development
flutter run --flavor development

# Staging
flutter run --flavor staging

# Production
flutter run --flavor production
```

Build examples:

```powershell
flutter build ios --simulator --no-codesign --flavor development
flutter build apk --flavor staging
flutter build appbundle --flavor production
```

### Bundle / application ID matrix

| Flavor      | iOS `PRODUCT_BUNDLE_IDENTIFIER` | Android `applicationId`  |
| ----------- | ------------------------------- | ------------------------ |
| development | `com.emsalist.app.dev`          | `com.emsalist.app.dev`     |
| staging     | `com.emsalist.app.staging`      | `com.emsalist.app.staging` |
| production  | `com.emsalist.app`              | `com.emsalist.app`         |

- iOS: three shared schemes (`development`, `staging`, `production`) with
  `Debug`/`Profile`/`Release` build configurations per flavor, wired through
  `ios/Flutter/Flavors/*.xcconfig`. No signing Team ID is committed; simulator
  builds run with `--no-codesign`.
- Android: `flavorDimensions "environment"` with `development`, `staging`, and
  `production` product flavors (dev/staging apply an `applicationIdSuffix`).

## Project structure

```text
mobile/
  lib/
    main.dart
    app/                          # App root, router, theme
    core/
      constants/                  # App-wide constants and tokens
      models/                     # Shared domain models
      providers/                  # Riverpod providers (case, theme, UYAP)
      widgets/                    # Shared state widgets (loading, error, empty)
    design_system/
      components/                 # App bar, card, composer
    features/
      assistant/                  # Chat/assistant screen and message cards
      cases/                      # Case drawer and summary sheet
      settings/                   # Appearance settings
      uyap/                       # UYAP status icon and bottom sheet
  test/                           # Widget tests
  ios/                            # iOS platform files (Runner + flavors)
  android/                        # Android platform files (flavors)
```

## P2.1 scope

- [x] Flutter project under `/mobile`
- [x] Native development, staging, production flavors (iOS + Android)
- [x] iOS-first design system tokens
- [x] System/light/dark theme support
- [x] Main chat shell screen
- [x] Case drawer mock
- [x] Message composer with keyboard-safe behavior and 6 attach options
- [x] UYAP status icon and mock bottom sheet
- [x] Appearance settings
- [x] Loading, empty, error states
- [x] Safe-area and Dynamic Type support
- [x] Overflow tests across 375x812 / 390x844 / 430x932
- [x] Widget test suite (45 tests)
- [x] Mobile CI pipeline (format, analyze, test, iOS simulator build per flavor)

## P2.5B native document picker

The case-scoped document upload screen uses the operating system's native
picker through `file_picker` 11.0.2. It accepts PDF, TXT, DOCX, UDF, JPG, JPEG,
and PNG files. Cancellation returns to the screen without an error.

Empty files and files larger than 15 MB are rejected before upload with a
controlled user-facing message. These client checks are upload preflight/UX
only; backend validation remains the authoritative security and size boundary.

## Out of scope for P2.1

- Real authentication and secure token storage
- Real backend API integration
- Case creation, listing, and conversation persistence
- Legal source ingestion and search
- AI-powered drafting
- Push notifications
- UYAP bridge integration
- App Store / TestFlight distribution

## Known limitations

- **Mock data only**: All case lists, messages, and UYAP status are hardcoded mock
  data. No backend calls are made.
- **No real auth**: Real authentication arrives in a later phase.
- **iOS build requires macOS**: The CI `iOS Simulator Build` job runs on
  `macos-latest` for all three flavors and is a required check (not
  allowed-to-fail). It cannot be validated on Windows locally.
- **No golden tests**: Golden image tests are not part of P2.1.
- **No offline cache**: Encrypted local storage is not yet implemented.

## Test commands

```powershell
cd mobile

# Run all widget tests
flutter test

# Run a specific test file
flutter test test/composer_test.dart

# Format check (CI gate)
dart format --output=none --set-exit-if-changed lib test

# Static analysis
flutter analyze
```

## Architecture

P2.1 uses a **feature-first** layout with Riverpod for state and GoRouter for
navigation.

**State management**: [Riverpod](https://riverpod.dev) — compile-safe, testable
providers.

**Navigation**: [GoRouter](https://pub.dev/packages/go_router) — declarative routing.

**Key design rules**:

- UI widgets never call HTTP clients directly.
- Active case state is invalidated on case switch.
- Theme follows `ThemeMode.system` by default; manual light/dark is available in
  settings.
