import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/uyap_status.dart';

class UyapNotifier extends StateNotifier<UyapState> {
  UyapNotifier()
    : super(
        UyapState(
          status: UyapStatus.connected,
          movementCount: 2,
          lastChecked: DateTime.now().subtract(const Duration(minutes: 4)),
        ),
      );

  void reconnect() {
    state = state.copyWith(status: UyapStatus.connecting);
    Future<void>.delayed(const Duration(seconds: 2), () {
      if (!mounted) {
        return;
      }
      state = state.copyWith(
        status: UyapStatus.connected,
        lastChecked: DateTime.now(),
      );
    });
  }

  void setStatus(UyapStatus status) {
    state = state.copyWith(status: status, lastChecked: DateTime.now());
  }

  void clearMovements() {
    state = state.copyWith(movementCount: 0);
  }
}

final StateNotifierProvider<UyapNotifier, UyapState> uyapProvider =
    StateNotifierProvider<UyapNotifier, UyapState>((Ref ref) => UyapNotifier());
