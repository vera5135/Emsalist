import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../auth/application/auth_providers.dart';
import '../data/document_api.dart';
import '../data/document_repository.dart';
import '../domain/document_item.dart';

final Provider<DocumentApi> documentApiProvider = Provider<DocumentApi>((ref) {
  return DocumentApi(ref.watch(authenticatedApiClientProvider));
});

final Provider<DocumentRepository> documentRepositoryProvider =
    Provider<DocumentRepository>((ref) {
      return DocumentRepository(ref.watch(documentApiProvider));
    });

/// Documents for a case; refetched per case id.
final FutureProviderFamily<List<DocumentItem>, String> documentsProvider =
    FutureProvider.family<List<DocumentItem>, String>((ref, String caseId) async {
      return ref.watch(documentRepositoryProvider).listDocuments(caseId);
    });

/// Analysis for a single document, keyed by "caseId::documentId".
final FutureProviderFamily<DocumentAnalysis, String> documentAnalysisProvider =
    FutureProvider.family<DocumentAnalysis, String>((ref, String key) async {
      final int sep = key.indexOf('::');
      final String caseId = key.substring(0, sep);
      final String documentId = key.substring(sep + 2);
      return ref.watch(documentRepositoryProvider).analysis(caseId, documentId);
    });
