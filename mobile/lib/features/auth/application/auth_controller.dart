import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/auth_repository.dart';
import '../data/session_manager.dart';
import '../domain/auth_session.dart';
import 'auth_state.dart';

/// Owns the app-wide authentication lifecycle.
///
/// Responsibilities:
/// - Restore any persisted session on startup (splash → authenticated /
///   unauthenticated).
/// - Establish a session after password login or Apple link/authenticated.
/// - Clear the session on logout or when a refresh permanently fails
///   (the [SessionManager] invokes [onSessionCleared], which flips state to
///   unauthenticated so the router redirects to login).
///
/// It never stores tokens itself; the [SessionManager] is the single owner of
/// the secure-storage-backed session.
class AuthController extends StateNotifier<AuthState> {
  AuthController({
    required SessionManager sessionManager,
    required AuthRepository repository,
  }) : _sessionManager = sessionManager,
       _repository = repository,
       super(const AuthState.unknown());

  final SessionManager _sessionManager;
  final AuthRepository _repository;

  /// Called by the composition root once, after construction.
  Future<void> bootstrap() async {
    final AuthSession? restored = await _sessionManager.restore();
    bool appleAvailable = false;
    try {
      appleAvailable = await _repository.isAppleAvailable();
    } on Object {
      appleAvailable = false;
    }
    if (restored != null && restored.hasTokens) {
      state = AuthState(
        status: AuthStatus.authenticated,
        session: restored,
        appleAvailable: appleAvailable,
      );
    } else {
      // Ensure no partial session lingers.
      await _sessionManager.clear();
      state = AuthState(
        status: AuthStatus.unauthenticated,
        appleAvailable: appleAvailable,
      );
    }
  }

  Future<void> loginWithPassword({
    required String email,
    required String password,
  }) async {
    final AuthSession session = await _repository.loginWithPassword(
      email: email,
      password: password,
    );
    await _establish(session);
  }

  /// Establishes a session produced by the Apple authenticated branch.
  Future<void> completeAppleAuthenticated(AuthSession session) {
    return _establish(session);
  }

  /// Confirms email + password to link a pending Apple identity, then signs in.
  Future<void> linkApple({
    required String linkTicket,
    required String email,
    required String password,
  }) async {
    final AuthSession session = await _repository.linkApple(
      linkTicket: linkTicket,
      email: email,
      password: password,
    );
    await _establish(session);
  }

  /// Signs out: best-effort backend revoke, then always clears locally.
  Future<void> logout() async {
    try {
      await _repository.logout();
    } on Object {
      // Even if the network call fails, always clear the local session.
    }
    await _sessionManager.clear();
    state = state.copyWith(
      status: AuthStatus.unauthenticated,
      clearSession: true,
    );
  }

  /// Called when the [SessionManager] clears the session due to a failed
  /// refresh; flips the app to unauthenticated so the router redirects.
  void onSessionCleared() {
    if (state.status != AuthStatus.unauthenticated) {
      state = state.copyWith(
        status: AuthStatus.unauthenticated,
        clearSession: true,
      );
    }
  }

  Future<void> _establish(AuthSession session) async {
    await _sessionManager.establish(session);
    state = state.copyWith(
      status: AuthStatus.authenticated,
      session: session,
    );
  }
}
