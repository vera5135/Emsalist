import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'auth_providers.dart';
import 'auth_state.dart';

/// Bridges Riverpod [authControllerProvider] changes to a [Listenable] so
/// GoRouter's `refreshListenable` re-evaluates redirects whenever auth status
/// changes. Only status transitions trigger a notification to avoid redundant
/// router refreshes.
class AuthRouterRefresh extends ChangeNotifier {
  AuthRouterRefresh(this._ref) {
    _status = _ref.read(authControllerProvider).status;
    _removeListener = _ref.listen<AuthState>(authControllerProvider, (
      AuthState? previous,
      AuthState next,
    ) {
      if (next.status != _status) {
        _status = next.status;
        notifyListeners();
      }
    }).close;
  }

  final Ref _ref;
  late AuthStatus _status;
  late final VoidCallback _removeListener;

  @override
  void dispose() {
    _removeListener();
    super.dispose();
  }
}

final Provider<AuthRouterRefresh> authRouterRefreshProvider =
    Provider<AuthRouterRefresh>((ref) {
      final AuthRouterRefresh refresh = AuthRouterRefresh(ref);
      ref.onDispose(refresh.dispose);
      return refresh;
    });
