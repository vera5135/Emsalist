import 'package:json_annotation/json_annotation.dart';

part 'document_dto.g.dart';

@JsonSerializable(createToJson: false)
class DocumentDto {
  const DocumentDto({
    required this.id,
    required this.caseId,
    this.originalFilename = '',
    this.mimeType = '',
    this.extension = '',
    this.sizeBytes = 0,
    this.documentType = '',
    this.documentTypeSource = 'suggested',
    this.status = 'uploading',
    this.analysisStatus = 'pending',
    this.supportLevel = '',
    this.pageCount = 0,
    this.extractedTextAvailable = false,
    this.failureCode,
    this.version = 1,
    this.createdAt,
  });

  final String id;

  @JsonKey(name: 'case_id')
  final String caseId;

  @JsonKey(name: 'original_filename')
  final String originalFilename;

  @JsonKey(name: 'mime_type')
  final String mimeType;

  final String extension;

  @JsonKey(name: 'size_bytes')
  final int sizeBytes;

  @JsonKey(name: 'document_type')
  final String documentType;

  @JsonKey(name: 'document_type_source')
  final String documentTypeSource;

  final String status;

  @JsonKey(name: 'analysis_status')
  final String analysisStatus;

  @JsonKey(name: 'support_level')
  final String supportLevel;

  @JsonKey(name: 'page_count')
  final int pageCount;

  @JsonKey(name: 'extracted_text_available')
  final bool extractedTextAvailable;

  @JsonKey(name: 'failure_code')
  final String? failureCode;

  final int version;

  @JsonKey(name: 'created_at')
  final String? createdAt;

  factory DocumentDto.fromJson(Map<String, dynamic> json) =>
      _$DocumentDtoFromJson(json);
}

@JsonSerializable(createToJson: false)
class DocumentListDto {
  const DocumentListDto({
    this.items = const <DocumentDto>[],
    this.total = 0,
    this.hasMore = false,
  });

  final List<DocumentDto> items;
  final int total;

  @JsonKey(name: 'has_more')
  final bool hasMore;

  factory DocumentListDto.fromJson(Map<String, dynamic> json) =>
      _$DocumentListDtoFromJson(json);
}

@JsonSerializable(createToJson: false)
class ExtractionDto {
  const ExtractionDto({
    required this.id,
    required this.documentId,
    this.extractionType = '',
    this.fieldKey = '',
    this.value = '',
    this.pageNumber,
    this.confidence = 0.0,
    this.verificationStatus = 'detected',
    this.memoryFactId,
  });

  final String id;

  @JsonKey(name: 'document_id')
  final String documentId;

  @JsonKey(name: 'extraction_type')
  final String extractionType;

  @JsonKey(name: 'field_key')
  final String fieldKey;

  final String value;

  @JsonKey(name: 'page_number')
  final int? pageNumber;

  final double confidence;

  @JsonKey(name: 'verification_status')
  final String verificationStatus;

  @JsonKey(name: 'memory_fact_id')
  final String? memoryFactId;

  factory ExtractionDto.fromJson(Map<String, dynamic> json) =>
      _$ExtractionDtoFromJson(json);
}

@JsonSerializable(createToJson: false)
class DocumentAnalysisDto {
  const DocumentAnalysisDto({
    required this.documentId,
    this.status = '',
    this.analysisStatus = '',
    this.supportLevel = '',
    this.pageCount = 0,
    this.extractedTextAvailable = false,
    this.documentType = '',
    this.documentTypeSource = 'suggested',
    this.failureCode,
    this.extractions = const <ExtractionDto>[],
  });

  @JsonKey(name: 'document_id')
  final String documentId;

  final String status;

  @JsonKey(name: 'analysis_status')
  final String analysisStatus;

  @JsonKey(name: 'support_level')
  final String supportLevel;

  @JsonKey(name: 'page_count')
  final int pageCount;

  @JsonKey(name: 'extracted_text_available')
  final bool extractedTextAvailable;

  @JsonKey(name: 'document_type')
  final String documentType;

  @JsonKey(name: 'document_type_source')
  final String documentTypeSource;

  @JsonKey(name: 'failure_code')
  final String? failureCode;

  final List<ExtractionDto> extractions;

  factory DocumentAnalysisDto.fromJson(Map<String, dynamic> json) =>
      _$DocumentAnalysisDtoFromJson(json);
}
