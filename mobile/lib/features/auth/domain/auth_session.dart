/// Immutable authenticated session tokens held in memory and persisted to
/// secure storage.
///
/// Token values are never logged. [toString] intentionally redacts them.
class AuthSession {
  const AuthSession({
    required this.accessToken,
    required this.refreshToken,
    this.userId,
    this.tenant,
    this.role,
  });

  final String accessToken;
  final String refreshToken;
  final String? userId;
  final String? tenant;
  final String? role;

  AuthSession copyWith({
    String? accessToken,
    String? refreshToken,
    String? userId,
    String? tenant,
    String? role,
  }) {
    return AuthSession(
      accessToken: accessToken ?? this.accessToken,
      refreshToken: refreshToken ?? this.refreshToken,
      userId: userId ?? this.userId,
      tenant: tenant ?? this.tenant,
      role: role ?? this.role,
    );
  }

  bool get hasTokens => accessToken.isNotEmpty && refreshToken.isNotEmpty;

  @override
  String toString() =>
      'AuthSession(userId: $userId, tenant: $tenant, role: $role, '
      'accessToken: <redacted>, refreshToken: <redacted>)';
}
