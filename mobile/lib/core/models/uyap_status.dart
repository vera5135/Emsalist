import 'package:flutter/material.dart';

enum UyapStatus {
  connected,
  disconnected,
  connecting,
  error;

  static UyapStatus fromString(String value) {
    return UyapStatus.values.firstWhere(
      (UyapStatus s) => s.name == value,
      orElse: () => UyapStatus.disconnected,
    );
  }

  String get label {
    switch (this) {
      case UyapStatus.connected:
        return 'Bağlı';
      case UyapStatus.disconnected:
        return 'Bağlı değil';
      case UyapStatus.connecting:
        return 'Bağlanıyor';
      case UyapStatus.error:
        return 'Hata';
    }
  }

  IconData get icon {
    switch (this) {
      case UyapStatus.connected:
        return Icons.cloud_done_outlined;
      case UyapStatus.disconnected:
        return Icons.cloud_off_outlined;
      case UyapStatus.connecting:
        return Icons.cloud_sync_outlined;
      case UyapStatus.error:
        return Icons.cloud_off;
    }
  }

  Color get color {
    switch (this) {
      case UyapStatus.connected:
        return const Color(0xFF2E7D32);
      case UyapStatus.disconnected:
        return const Color(0xFF757575);
      case UyapStatus.connecting:
        return const Color(0xFF1565C0);
      case UyapStatus.error:
        return const Color(0xFFC62828);
    }
  }

  String get semanticsLabel => 'UYAP durumu: $label';
}

@immutable
class UyapState {
  const UyapState({
    this.status = UyapStatus.disconnected,
    this.movementCount = 0,
    this.lastChecked,
  });

  final UyapStatus status;
  final int movementCount;
  final DateTime? lastChecked;

  bool get hasNewMovements => movementCount > 0;

  UyapState copyWith({
    UyapStatus? status,
    int? movementCount,
    DateTime? lastChecked,
  }) {
    return UyapState(
      status: status ?? this.status,
      movementCount: movementCount ?? this.movementCount,
      lastChecked: lastChecked ?? this.lastChecked,
    );
  }
}
