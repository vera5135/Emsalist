import '../../../core/network/api_exception.dart';
import '../domain/document_item.dart';
import 'document_api.dart';

/// Domain operations over documents and their extractions.
class DocumentRepository {
  const DocumentRepository(this._api);

  final DocumentApi _api;

  Future<List<DocumentItem>> listDocuments(String caseId) async {
    final dto = await _api.list(caseId);
    return dto.items.map(DocumentItem.fromDto).toList();
  }

  /// Uploads a document. Throws [DuplicateDocumentException] on a 409 duplicate.
  Future<DocumentItem> upload(
    String caseId, {
    required List<int> bytes,
    required String filename,
    String? mimeType,
    String? documentType,
  }) async {
    try {
      final dto = await _api.upload(
        caseId,
        bytes: bytes,
        filename: filename,
        mimeType: mimeType,
        documentType: documentType,
      );
      return DocumentItem.fromDto(dto);
    } on ApiException catch (e) {
      if (e.statusCode == 409) {
        throw DuplicateDocumentException(DocumentApi.duplicateIdFrom(e));
      }
      rethrow;
    }
  }

  Future<DocumentAnalysis> analysis(String caseId, String documentId) async {
    return DocumentAnalysis.fromDto(await _api.analysis(caseId, documentId));
  }

  Future<DocumentItem> retry(String caseId, String documentId) async {
    return DocumentItem.fromDto(await _api.retry(caseId, documentId));
  }

  Future<void> delete(String caseId, String documentId) {
    return _api.delete(caseId, documentId);
  }

  Future<void> confirmExtraction(
    String caseId,
    String documentId,
    String extractionId,
  ) {
    return _api.confirmExtraction(caseId, documentId, extractionId);
  }

  Future<void> rejectExtraction(
    String caseId,
    String documentId,
    String extractionId,
  ) {
    return _api.rejectExtraction(caseId, documentId, extractionId);
  }
}
