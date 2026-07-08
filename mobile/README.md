# Emsalist Mobile (P2.1)

iOS-first Flutter mobile shell for the Emsalist legal workspace. P2.1 delivers the
initial application shell with design system, navigation, chat composer, case drawer
mock, UYAP status mock, and CI/test infrastructure.

## Quick start

```powershell
cd mobile
flutter pub get
flutter run
```

The app launches in development flavor by default with mock data.

## Flavors

Flavors are configured via `--dart-define`:

```powershell
# Development (default)
flutter run --dart-define FLAVOR=development

# Staging
flutter run --dart-define FLAVOR=staging

# Production
flutter run --dart-define FLAVOR=production
```

Each flavor controls:

- Bundle identifier
- API base URL
- Push notification environment
- App display suffix

## Project structure

```text
mobile/
  lib/
    main.dart
    app/                          # App root, router, theme provider
    core/
      constants/                  # App-wide constants and tokens
      errors/                     # Error types and mapping
      models/                     # Shared domain models
      widgets/                    # Shared widgets (loading, error, empty)
    design_system/                # Theme, typography, spacing, semantic tokens
    features/                     # Feature-first modules
      auth/
      workspace/
      cases/
      chat/
      case_memory/
      documents/
      sources/
      search/
      drafts/
      uyap/
      notifications/
      settings/
  test/                           # Unit and widget tests
  integration_test/               # Integration tests
  ios/                            # iOS platform files
  android/                        # Android platform files (future)
```

## P2.1 scope

- [x] Flutter project under `/mobile`
- [x] Development, staging, production flavor foundation
- [x] iOS-first design system tokens
- [x] System/light/dark theme support
- [x] Main chat shell screen
- [x] Case drawer mock
- [x] Message composer with keyboard-safe behavior
- [x] UYAP status icon and mock bottom sheet
- [x] Appearance settings
- [x] Loading, empty, error, and offline states
- [x] Safe-area and Dynamic Type support
- [x] Small iPhone overflow tests
- [x] Golden light/dark tests
- [x] Widget test infrastructure
- [x] Mobile CI pipeline (format, analyze, test, iOS simulator build)

## Out of scope for P2.1

- Real authentication and secure token storage
- Real backend API integration
- Case creation, listing, and conversation persistence
- Document upload and processing
- Legal source ingestion and search
- AI-powered drafting
- Push notifications
- UYAP bridge integration
- Android platform support
- App Store / TestFlight distribution

## Known limitations

- **No real auth**: Login screens and flows use mock data. Real authentication
  arrives in P2.2.
- **Mock data only**: All case lists, messages, and UYAP status are hardcoded mock
  data. No backend calls are made.
- **iOS build needs macOS**: The CI iOS simulator build job (`ios_build`) runs on
  `macos-latest`. It is allowed to fail in pull requests since the iOS project
  scaffolding evolves during P2.1.
- **No offline cache**: Encrypted local storage for messages and case metadata is
  not yet implemented.
- **Certificate pinning not enforced**: Planned for post-threat-model evaluation.

## Test commands

```powershell
cd mobile

# Run all unit and widget tests
flutter test

# Run tests with coverage
flutter test --coverage

# Run a specific test file
flutter test test/chat_shell_test.dart

# Format check
flutter format --set-exit-if-changed .

# Static analysis
flutter analyze
```

## Architecture

P2.1 follows a **feature-first** layout with layered boundaries inside each feature:

| Layer            | Responsibility                                      |
| ---------------- | --------------------------------------------------- |
| `presentation/`  | Widgets, screens, UI logic                          |
| `application/`   | State management, notifiers, providers              |
| `domain/`        | Entities, value objects, repository interfaces      |
| `data/`          | Repository implementations, data sources, DTOs      |

**State management**: [Riverpod](https://riverpod.dev) — compile-safe, testable
providers with async loading/data/error states.

**Navigation**: [GoRouter](https://pub.dev/packages/go_router) — typed declarative
routing with auth guard, workspace guard, and deep link support.

**Key design rules**:

- UI widgets never call HTTP clients directly; all data flows through repository
  adapters.
- Active case state is invalidated on case switch.
- Theme follows `ThemeMode.system` by default; manual light/dark is available in
  settings.
