import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import 'models/document_dto.dart';

/// Thin data source for the P2.5 document pipeline endpoints (authenticated).
class DocumentApi {
  const DocumentApi(this._client);

  final ApiClient _client;

  String _base(String caseId) => '/api/v1/cases/$caseId/documents';

  Future<DocumentListDto> list(String caseId, {Object? cancelToken}) async {
    final Map<String, dynamic> json = await _client
        .getJson<Map<String, dynamic>>(_base(caseId), cancelToken: cancelToken);
    return DocumentListDto.fromJson(json);
  }

  Future<DocumentDto> upload(
    String caseId, {
    required List<int> bytes,
    required String filename,
    String? mimeType,
    String? documentType,
  }) async {
    final Map<String, dynamic> json = await _client
        .uploadBytes<Map<String, dynamic>>(
          _base(caseId),
          bytes: bytes,
          filename: filename,
          mimeType: mimeType,
          fields: documentType != null && documentType.isNotEmpty
              ? <String, String>{'document_type': documentType}
              : const <String, String>{},
        );
    return DocumentDto.fromJson(json);
  }

  Future<DocumentAnalysisDto> analysis(
    String caseId,
    String documentId, {
    Object? cancelToken,
  }) async {
    final Map<String, dynamic> json = await _client
        .getJson<Map<String, dynamic>>(
          '${_base(caseId)}/$documentId/analysis',
          cancelToken: cancelToken,
        );
    return DocumentAnalysisDto.fromJson(json);
  }

  Future<DocumentDto> retry(String caseId, String documentId) async {
    final Map<String, dynamic> json = await _client
        .postJson<Map<String, dynamic>>('${_base(caseId)}/$documentId/retry');
    return DocumentDto.fromJson(json);
  }

  Future<void> delete(String caseId, String documentId) async {
    await _client.deleteJson<Map<String, dynamic>>(
      '${_base(caseId)}/$documentId',
    );
  }

  Future<ExtractionDto> confirmExtraction(
    String caseId,
    String documentId,
    String extractionId,
  ) async {
    final Map<String, dynamic> json = await _client
        .postJson<Map<String, dynamic>>(
          '${_base(caseId)}/$documentId/extractions/$extractionId/confirm',
        );
    return ExtractionDto.fromJson(json);
  }

  Future<ExtractionDto> rejectExtraction(
    String caseId,
    String documentId,
    String extractionId,
  ) async {
    final Map<String, dynamic> json = await _client
        .postJson<Map<String, dynamic>>(
          '${_base(caseId)}/$documentId/extractions/$extractionId/reject',
        );
    return ExtractionDto.fromJson(json);
  }

  /// Extracts the existing document id from a 409 duplicate response, if any.
  static String? duplicateIdFrom(ApiException error) {
    if (error.statusCode == 409) {
      return error.code;
    }
    return null;
  }
}
