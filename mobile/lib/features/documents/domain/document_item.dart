import '../data/models/document_dto.dart';

/// Domain representation of an uploaded document.
class DocumentItem {
  const DocumentItem({
    required this.id,
    required this.caseId,
    required this.filename,
    required this.extension,
    required this.sizeBytes,
    required this.documentType,
    required this.status,
    required this.supportLevel,
    required this.pageCount,
    required this.extractedTextAvailable,
    required this.version,
    this.createdAt,
  });

  final String id;
  final String caseId;
  final String filename;
  final String extension;
  final int sizeBytes;
  final String documentType;
  final String status;
  final String supportLevel;
  final int pageCount;
  final bool extractedTextAvailable;
  final int version;
  final DateTime? createdAt;

  bool get isProcessing =>
      status == 'uploading' || status == 'queued' || status == 'processing';
  bool get isAwaitingConfirmation => status == 'awaiting_confirmation';
  bool get isAnalyzed => status == 'analyzed';
  bool get isUnsupported => status == 'unsupported';
  bool get isFailed => status == 'failed';
  bool get isQuarantined => status == 'quarantined';

  String get displayName =>
      filename.trim().isEmpty ? 'İsimsiz belge' : filename;

  factory DocumentItem.fromDto(DocumentDto dto) {
    return DocumentItem(
      id: dto.id,
      caseId: dto.caseId,
      filename: dto.originalFilename,
      extension: dto.extension,
      sizeBytes: dto.sizeBytes,
      documentType: dto.documentType,
      status: dto.status,
      supportLevel: dto.supportLevel,
      pageCount: dto.pageCount,
      extractedTextAvailable: dto.extractedTextAvailable,
      version: dto.version,
      createdAt: DateTime.tryParse(dto.createdAt ?? ''),
    );
  }
}

/// A user-facing extraction suggestion with provenance.
class DocumentExtractionItem {
  const DocumentExtractionItem({
    required this.id,
    required this.documentId,
    required this.fieldKey,
    required this.value,
    required this.pageNumber,
    required this.confidence,
    required this.verificationStatus,
  });

  final String id;
  final String documentId;
  final String fieldKey;
  final String value;
  final int? pageNumber;
  final double confidence;
  final String verificationStatus;

  bool get isConfirmed => verificationStatus == 'user_confirmed';
  bool get isRejected => verificationStatus == 'rejected';
  bool get isPending => verificationStatus == 'detected';

  factory DocumentExtractionItem.fromDto(ExtractionDto dto) {
    return DocumentExtractionItem(
      id: dto.id,
      documentId: dto.documentId,
      fieldKey: dto.fieldKey,
      value: dto.value,
      pageNumber: dto.pageNumber,
      confidence: dto.confidence,
      verificationStatus: dto.verificationStatus,
    );
  }
}

/// Full analysis view of a document.
class DocumentAnalysis {
  const DocumentAnalysis({
    required this.documentId,
    required this.status,
    required this.supportLevel,
    required this.pageCount,
    required this.extractedTextAvailable,
    required this.documentType,
    required this.extractions,
  });

  final String documentId;
  final String status;
  final String supportLevel;
  final int pageCount;
  final bool extractedTextAvailable;
  final String documentType;
  final List<DocumentExtractionItem> extractions;

  factory DocumentAnalysis.fromDto(DocumentAnalysisDto dto) {
    return DocumentAnalysis(
      documentId: dto.documentId,
      status: dto.status,
      supportLevel: dto.supportLevel,
      pageCount: dto.pageCount,
      extractedTextAvailable: dto.extractedTextAvailable,
      documentType: dto.documentType,
      extractions: dto.extractions.map(DocumentExtractionItem.fromDto).toList(),
    );
  }
}

/// Raised when an upload is rejected as a duplicate of an existing document.
class DuplicateDocumentException implements Exception {
  const DuplicateDocumentException(this.existingDocumentId);
  final String? existingDocumentId;
}
