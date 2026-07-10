import '../domain/auth_session.dart';

/// High-level authentication lifecycle status used by the router guard and UI.
enum AuthStatus {
  /// App is still restoring any persisted session (splash / auth-loading).
  unknown,

  /// No valid session; the user must sign in.
  unauthenticated,

  /// A valid session exists.
  authenticated,
}

/// Immutable auth state exposed to the UI.
class AuthState {
  const AuthState({
    required this.status,
    this.session,
    this.appleAvailable = false,
  });

  const AuthState.unknown()
    : status = AuthStatus.unknown,
      session = null,
      appleAvailable = false;

  final AuthStatus status;
  final AuthSession? session;
  final bool appleAvailable;

  bool get isAuthenticated => status == AuthStatus.authenticated;
  bool get isUnknown => status == AuthStatus.unknown;

  AuthState copyWith({
    AuthStatus? status,
    AuthSession? session,
    bool clearSession = false,
    bool? appleAvailable,
  }) {
    return AuthState(
      status: status ?? this.status,
      session: clearSession ? null : (session ?? this.session),
      appleAvailable: appleAvailable ?? this.appleAvailable,
    );
  }
}
