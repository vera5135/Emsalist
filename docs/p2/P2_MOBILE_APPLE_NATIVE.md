# P2.2B2B — Mobile Apple Sign-In: iOS Native Configuration

Status: **backend-facing flow + secure session implemented; native binding pending real Apple config.**

This document lists the native iOS setup required to enable the real
"Sign in with Apple" flow. Until these are completed and real Apple developer
credentials exist, the app ships with an **unavailable** Apple credential
provider (`UnavailableAppleCredentialProvider`): the "Apple ile Devam Et"
button is hidden and email/password login is fully functional. No part of the
Apple native flow has been run on a device or simulator.

## What is already in the repo

- `ios/Runner/Runner.entitlements` — declares the
  `com.apple.developer.applesignin` entitlement (`Default`).
- Dart seam `AppleCredentialProvider` (+ `AppleNonce`) isolates the native SDK
  from the app so the flow is testable and the native package can be added
  without touching callers.
- The backend contract is already live on `main`
  (`POST /api/v1/auth/apple/login`, `/apple/link`, `/apple/status`,
  `/apple/unlink`).

## Required native steps (not doable from Dart/CI alone)

1. **Xcode capability**: In Xcode → Runner target → Signing & Capabilities, add
   **Sign in with Apple** for the `Runner` target. Ensure the build
   configurations reference `Runner/Runner.entitlements`
   (`CODE_SIGN_ENTITLEMENTS = Runner/Runner.entitlements`) for Debug, Release
   and Profile across all three flavors (dev/staging/production). This edits
   `ios/Runner.xcodeproj/project.pbxproj`, which is not modified here.

2. **Apple Developer portal**:
   - Enable "Sign in with Apple" for each App ID:
     `com.emsalist.app.dev`, `com.emsalist.app.staging`, `com.emsalist.app`.
   - Create a **Services ID** (used as the backend `APPLE_CLIENT_ID` audience
     for the token exchange) and a **Key** (`.p8`) with Sign in with Apple
     enabled; note the **Team ID** and **Key ID**.
   - These map to the backend env vars documented in P2.2B2A:
     `APPLE_CLIENT_ID`, `APPLE_TEAM_ID`, `APPLE_KEY_ID`,
     `APPLE_PRIVATE_KEY_PATH`, `APPLE_SUBJECT_PEPPER`.

3. **Add the native package + concrete provider**: add `sign_in_with_apple`
   (or a platform-channel implementation) and implement
   `AppleCredentialProvider`:
   - Generate a raw nonce with `AppleNonce.generateRaw()`.
   - Pass `AppleNonce.sha256Hex(rawNonce)` to Apple as the request `nonce`.
   - Return `AppleCredential(authorizationCode, rawNonce)`; the backend verifies
     the ID token `nonce` claim equals `SHA256(rawNonce)`.
   - Override `appleCredentialProvider` in `auth_providers.dart` to return the
     real implementation and report `isAvailable()` accordingly.

4. **Device / TestFlight E2E**: exercise authenticated login, first-time link,
   session restore, refresh rotation and unlink on a real device with real
   Apple credentials. This has **not** been performed.

## Security notes

- Access and refresh tokens are stored only in `flutter_secure_storage`
  (iOS Keychain), never in SharedPreferences, and are never logged
  (`AuthSession.toString()` redacts them; `SafeLoggingInterceptor` redacts the
  Authorization header).
- The Apple `link_ticket` is treated as an opaque secret and is never displayed
  to the user.
- Refresh rotation replaces the token pair atomically and is single-flight; a
  failed refresh clears the whole session and routes to login.
