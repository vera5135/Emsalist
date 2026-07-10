import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/config/api_config.dart';
import '../../../core/network/api_client.dart';
import '../../../core/network/dio_api_client.dart';
import '../../../core/providers/api_client_provider.dart';
import '../application/auth_controller.dart';
import '../application/auth_state.dart';
import '../data/apple_credential_provider.dart';
import '../data/auth_api.dart';
import '../data/auth_interceptor.dart';
import '../data/auth_repository.dart';
import '../data/refresh_interceptor.dart';
import '../data/secure_session_store.dart';
import '../data/session_manager.dart';
import '../data/token_refresher.dart';

/// Secure, platform-backed session storage.
final Provider<SecureSessionStore> secureSessionStoreProvider =
    Provider<SecureSessionStore>((ref) => const FlutterSecureSessionStore());

/// Refresh-token rotation client (bare Dio, no auth interceptors).
final Provider<TokenRefresher> tokenRefresherProvider =
    Provider<TokenRefresher>((ref) {
      final ApiConfig config = ref.watch(apiConfigProvider);
      return HttpTokenRefresher(config: config);
    });

/// Native Apple credential provider seam. Defaults to unavailable until the
/// native Sign in with Apple binding is wired in (see
/// `docs/p2/P2_MOBILE_APPLE_NATIVE.md`).
final Provider<AppleCredentialProvider> appleCredentialProvider =
    Provider<AppleCredentialProvider>(
      (ref) => const UnavailableAppleCredentialProvider(),
    );

/// Single source of truth for the live session and rotation.
///
/// Wires [SessionManager.onSessionCleared] to the [AuthController] so a failed
/// refresh flips the app to unauthenticated.
final Provider<SessionManager> sessionManagerProvider =
    Provider<SessionManager>((ref) {
      return SessionManager(
        store: ref.watch(secureSessionStoreProvider),
        refresher: ref.watch(tokenRefresherProvider),
        onSessionCleared: () {
          ref.read(authControllerProvider.notifier).onSessionCleared();
        },
      );
    });

/// Authenticated API client with auth (Bearer inject) + refresh (401 rotate)
/// interceptors installed.
final Provider<ApiClient> authenticatedApiClientProvider = Provider<ApiClient>((
  ref,
) {
  final ApiConfig config = ref.watch(apiConfigProvider);
  final SessionManager sessionManager = ref.watch(sessionManagerProvider);
  return DioApiClient(
    config: config,
    authInterceptors: (Dio dio) => <Interceptor>[
      AuthInterceptor(sessionManager: sessionManager),
      RefreshInterceptor(sessionManager: sessionManager, dio: dio),
    ],
  );
});

final Provider<AuthApi> authApiProvider = Provider<AuthApi>((ref) {
  return AuthApi(ref.watch(authenticatedApiClientProvider));
});

final Provider<AuthRepository> authRepositoryProvider =
    Provider<AuthRepository>((ref) {
      return AuthRepository(
        api: ref.watch(authApiProvider),
        appleCredentialProvider: ref.watch(appleCredentialProvider),
      );
    });

/// App-wide authentication state.
final StateNotifierProvider<AuthController, AuthState> authControllerProvider =
    StateNotifierProvider<AuthController, AuthState>((ref) {
      return AuthController(
        sessionManager: ref.watch(sessionManagerProvider),
        repository: ref.watch(authRepositoryProvider),
      );
    });
