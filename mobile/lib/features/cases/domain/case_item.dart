import '../data/models/case_dto.dart';

/// Domain representation of a case, decoupled from transport DTOs.
class CaseItem {
  const CaseItem({
    required this.id,
    required this.title,
    required this.legalTopic,
    required this.status,
    required this.version,
    this.updatedAt,
  });

  final String id;
  final String title;
  final String legalTopic;
  final String status;
  final int version;
  final DateTime? updatedAt;

  bool get isArchived => status == 'archived';
  bool get isActive => status == 'active';

  String get displayTitle => title.trim().isEmpty ? 'İsimsiz dosya' : title;

  factory CaseItem.fromDto(CaseDto dto) {
    return CaseItem(
      id: dto.id,
      title: dto.title,
      legalTopic: dto.legalTopic,
      status: dto.status,
      version: dto.version,
      updatedAt: DateTime.tryParse(dto.updatedAt ?? ''),
    );
  }
}
