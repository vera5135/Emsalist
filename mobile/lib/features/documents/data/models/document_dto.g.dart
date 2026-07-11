// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'document_dto.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

DocumentDto _$DocumentDtoFromJson(Map<String, dynamic> json) => DocumentDto(
  id: json['id'] as String,
  caseId: json['case_id'] as String,
  originalFilename: json['original_filename'] as String? ?? '',
  mimeType: json['mime_type'] as String? ?? '',
  extension: json['extension'] as String? ?? '',
  sizeBytes: (json['size_bytes'] as num?)?.toInt() ?? 0,
  documentType: json['document_type'] as String? ?? '',
  documentTypeSource: json['document_type_source'] as String? ?? 'suggested',
  status: json['status'] as String? ?? 'uploading',
  analysisStatus: json['analysis_status'] as String? ?? 'pending',
  supportLevel: json['support_level'] as String? ?? '',
  pageCount: (json['page_count'] as num?)?.toInt() ?? 0,
  extractedTextAvailable: json['extracted_text_available'] as bool? ?? false,
  failureCode: json['failure_code'] as String?,
  version: (json['version'] as num?)?.toInt() ?? 1,
  createdAt: json['created_at'] as String?,
);

DocumentListDto _$DocumentListDtoFromJson(Map<String, dynamic> json) =>
    DocumentListDto(
      items:
          (json['items'] as List<dynamic>?)
              ?.map((e) => DocumentDto.fromJson(e as Map<String, dynamic>))
              .toList() ??
          const <DocumentDto>[],
      total: (json['total'] as num?)?.toInt() ?? 0,
      hasMore: json['has_more'] as bool? ?? false,
    );

ExtractionDto _$ExtractionDtoFromJson(Map<String, dynamic> json) =>
    ExtractionDto(
      id: json['id'] as String,
      documentId: json['document_id'] as String,
      extractionType: json['extraction_type'] as String? ?? '',
      fieldKey: json['field_key'] as String? ?? '',
      value: json['value'] as String? ?? '',
      pageNumber: (json['page_number'] as num?)?.toInt(),
      confidence: (json['confidence'] as num?)?.toDouble() ?? 0.0,
      verificationStatus: json['verification_status'] as String? ?? 'detected',
      memoryFactId: json['memory_fact_id'] as String?,
    );

DocumentAnalysisDto _$DocumentAnalysisDtoFromJson(
  Map<String, dynamic> json,
) => DocumentAnalysisDto(
  documentId: json['document_id'] as String,
  status: json['status'] as String? ?? '',
  analysisStatus: json['analysis_status'] as String? ?? '',
  supportLevel: json['support_level'] as String? ?? '',
  pageCount: (json['page_count'] as num?)?.toInt() ?? 0,
  extractedTextAvailable: json['extracted_text_available'] as bool? ?? false,
  documentType: json['document_type'] as String? ?? '',
  documentTypeSource: json['document_type_source'] as String? ?? 'suggested',
  failureCode: json['failure_code'] as String?,
  extractions:
      (json['extractions'] as List<dynamic>?)
          ?.map((e) => ExtractionDto.fromJson(e as Map<String, dynamic>))
          .toList() ??
      const <ExtractionDto>[],
);
