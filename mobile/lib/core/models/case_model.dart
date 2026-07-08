import 'package:flutter/material.dart';

import 'uyap_status.dart';

@immutable
class CaseModel {
  const CaseModel({
    required this.id,
    required this.title,
    required this.legalTopic,
    required this.status,
    required this.lastUpdated,
    this.pinned = false,
    this.archived = false,
  });

  final String id;
  final String title;
  final String legalTopic;
  final UyapStatus status;
  final DateTime lastUpdated;
  final bool pinned;
  final bool archived;

  CaseModel copyWith({
    String? id,
    String? title,
    String? legalTopic,
    UyapStatus? status,
    DateTime? lastUpdated,
    bool? pinned,
    bool? archived,
  }) {
    return CaseModel(
      id: id ?? this.id,
      title: title ?? this.title,
      legalTopic: legalTopic ?? this.legalTopic,
      status: status ?? this.status,
      lastUpdated: lastUpdated ?? this.lastUpdated,
      pinned: pinned ?? this.pinned,
      archived: archived ?? this.archived,
    );
  }

  static List<CaseModel> mockCases() {
    final DateTime now = DateTime.now();
    return <CaseModel>[
      CaseModel(
        id: 'case-001',
        title: 'Araç Ayıbı',
        legalTopic: 'Tüketici Hukuku',
        status: UyapStatus.connected,
        lastUpdated: now.subtract(const Duration(minutes: 12)),
        pinned: true,
      ),
      CaseModel(
        id: 'case-002',
        title: 'Kira Tespit',
        legalTopic: 'Kira Hukuku',
        status: UyapStatus.disconnected,
        lastUpdated: now.subtract(const Duration(hours: 5)),
      ),
      CaseModel(
        id: 'case-003',
        title: 'İşçilik Alacakları',
        legalTopic: 'İş Hukuku',
        status: UyapStatus.error,
        lastUpdated: now.subtract(const Duration(days: 2)),
        archived: true,
      ),
    ];
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) || (other is CaseModel && other.id == id);

  @override
  int get hashCode => id.hashCode;
}
