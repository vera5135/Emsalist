import '../data/models/case_memory_dto.dart';

/// Domain aggregate of a case's structured memory, mapped from transport DTOs.
class CaseMemory {
  const CaseMemory({
    required this.caseId,
    required this.overallRiskLevel,
    required this.facts,
    required this.timeline,
    required this.missingInformation,
    required this.contradictions,
    required this.risks,
  });

  final String caseId;
  final String overallRiskLevel;
  final List<MemoryFact> facts;
  final List<MemoryEvent> timeline;
  final List<MemoryMissing> missingInformation;
  final List<MemoryContradiction> contradictions;
  final List<MemoryRisk> risks;

  bool get isEmpty =>
      facts.isEmpty &&
      timeline.isEmpty &&
      missingInformation.isEmpty &&
      contradictions.isEmpty &&
      risks.isEmpty;

  factory CaseMemory.fromDto(CaseMemoryDto dto) {
    return CaseMemory(
      caseId: dto.caseId,
      overallRiskLevel: dto.overallRiskLevel,
      facts: dto.facts.map(MemoryFact.fromDto).toList(),
      timeline: dto.timeline.map(MemoryEvent.fromDto).toList(),
      missingInformation: dto.missingInformation
          .map(MemoryMissing.fromDto)
          .toList(),
      contradictions: dto.contradictions
          .map(MemoryContradiction.fromDto)
          .toList(),
      risks: dto.risks.map(MemoryRisk.fromDto).toList(),
    );
  }
}

class MemoryFact {
  const MemoryFact({
    required this.id,
    required this.factType,
    required this.value,
    required this.importance,
    required this.sourceType,
    required this.verificationStatus,
    required this.version,
  });

  final String id;
  final String factType;
  final String value;
  final String importance;
  final String sourceType;
  final String verificationStatus;
  final int version;

  bool get isConfirmed => const <String>{
    'user_confirmed',
    'document_verified',
    'uyap_verified',
  }.contains(verificationStatus);
  bool get isConflicting => verificationStatus == 'conflicting';
  bool get isRejected => verificationStatus == 'rejected';

  factory MemoryFact.fromDto(FactDto dto) => MemoryFact(
    id: dto.id,
    factType: dto.factType,
    value: dto.value,
    importance: dto.importance,
    sourceType: dto.sourceType,
    verificationStatus: dto.verificationStatus,
    version: dto.version,
  );
}

class MemoryEvent {
  const MemoryEvent({
    required this.id,
    required this.eventType,
    required this.description,
    required this.eventDate,
    required this.isApproximate,
    required this.verificationStatus,
  });

  final String id;
  final String eventType;
  final String description;
  final String eventDate;
  final bool isApproximate;
  final String verificationStatus;

  bool get hasDate => eventDate.trim().isNotEmpty;

  factory MemoryEvent.fromDto(TimelineEventDto dto) => MemoryEvent(
    id: dto.id,
    eventType: dto.eventType,
    description: dto.description,
    eventDate: dto.eventDate,
    isApproximate: dto.isApproximate,
    verificationStatus: dto.verificationStatus,
  );
}

class MemoryMissing {
  const MemoryMissing({
    required this.id,
    required this.fieldKey,
    required this.label,
    required this.importance,
    required this.status,
  });

  final String id;
  final String fieldKey;
  final String label;
  final String importance;
  final String status;

  bool get isResolved =>
      const <String>{'supplied', 'verified', 'waived'}.contains(status);

  factory MemoryMissing.fromDto(MissingInfoDto dto) => MemoryMissing(
    id: dto.id,
    fieldKey: dto.fieldKey,
    label: dto.label,
    importance: dto.importance,
    status: dto.status,
  );
}

class MemoryContradiction {
  const MemoryContradiction({
    required this.id,
    required this.contradictionType,
    required this.description,
    required this.factIds,
    required this.severity,
    required this.status,
  });

  final String id;
  final String contradictionType;
  final String description;
  final List<String> factIds;
  final String severity;
  final String status;

  bool get isOpen => status == 'open';

  factory MemoryContradiction.fromDto(ContradictionDto dto) =>
      MemoryContradiction(
        id: dto.id,
        contradictionType: dto.contradictionType,
        description: dto.description,
        factIds: dto.factIds,
        severity: dto.severity,
        status: dto.status,
      );
}

class MemoryRisk {
  const MemoryRisk({
    required this.id,
    required this.riskType,
    required this.severity,
    required this.title,
    required this.rationale,
    required this.mitigation,
    required this.status,
  });

  final String id;
  final String riskType;
  final String severity;
  final String title;
  final String rationale;
  final String mitigation;
  final String status;

  factory MemoryRisk.fromDto(RiskDto dto) => MemoryRisk(
    id: dto.id,
    riskType: dto.riskType,
    severity: dto.severity,
    title: dto.title,
    rationale: dto.rationale,
    mitigation: dto.mitigation,
    status: dto.status,
  );
}
