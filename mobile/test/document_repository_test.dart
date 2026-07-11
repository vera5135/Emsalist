import 'package:emsalist_mobile/core/network/api_exception.dart';
import 'package:emsalist_mobile/features/documents/data/document_api.dart';
import 'package:emsalist_mobile/features/documents/data/document_repository.dart';
import 'package:emsalist_mobile/features/documents/domain/document_item.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_api_client.dart';

const String _caseId = 'c1';
const String _base = '/api/v1/cases/$_caseId/documents';

DocumentRepository _repo(FakeApiClient client) =>
    DocumentRepository(DocumentApi(client));

void main() {
  test('listDocuments maps items', () async {
    final FakeApiClient client = FakeApiClient()
      ..whenGet(_base, <String, dynamic>{
        'items': <dynamic>[
          <String, dynamic>{
            'id': 'd1',
            'case_id': _caseId,
            'original_filename': 'sozlesme.txt',
            'extension': '.txt',
            'size_bytes': 100,
            'status': 'awaiting_confirmation',
            'support_level': 'fully_supported',
            'page_count': 1,
            'extracted_text_available': true,
            'version': 2,
          },
        ],
        'total': 1,
        'has_more': false,
      });

    final docs = await _repo(client).listDocuments(_caseId);

    expect(docs, hasLength(1));
    expect(docs.first.displayName, 'sozlesme.txt');
    expect(docs.first.isAwaitingConfirmation, isTrue);
  });

  test('upload posts multipart and maps result', () async {
    final FakeApiClient client = FakeApiClient()
      ..whenPost(_base, <String, dynamic>{
        'id': 'd2',
        'case_id': _caseId,
        'original_filename': 'not.txt',
        'extension': '.txt',
        'status': 'analyzed',
        'support_level': 'fully_supported',
      });

    final doc = await _repo(client).upload(
      _caseId,
      bytes: <int>[104, 105],
      filename: 'not.txt',
      mimeType: 'text/plain',
    );

    expect(doc.id, 'd2');
    expect(client.uploadPaths, contains(_base));
  });

  test('duplicate upload throws DuplicateDocumentException', () async {
    final FakeApiClient client = FakeApiClient()
      ..whenPostError(
        _base,
        const ApiException(
          kind: ApiErrorKind.server,
          message: 'duplicate',
          statusCode: 409,
          code: 'existing-doc-id',
        ),
      );

    await expectLater(
      _repo(client).upload(
        _caseId,
        bytes: <int>[1, 2, 3],
        filename: 'a.txt',
        mimeType: 'text/plain',
      ),
      throwsA(isA<DuplicateDocumentException>()),
    );
  });

  test('analysis maps extractions with provenance', () async {
    final FakeApiClient client = FakeApiClient()
      ..whenGet('$_base/d1/analysis', <String, dynamic>{
        'document_id': 'd1',
        'status': 'awaiting_confirmation',
        'support_level': 'fully_supported',
        'page_count': 2,
        'extracted_text_available': true,
        'document_type': '',
        'extractions': <dynamic>[
          <String, dynamic>{
            'id': 'e1',
            'document_id': 'd1',
            'field_key': 'amount',
            'value': '850000 TL',
            'page_number': 2,
            'confidence': 0.6,
            'verification_status': 'detected',
          },
        ],
      });

    final analysis = await _repo(client).analysis(_caseId, 'd1');

    expect(analysis.extractions, hasLength(1));
    expect(analysis.extractions.first.pageNumber, 2);
    expect(analysis.extractions.first.isPending, isTrue);
  });

  test('confirm and reject extraction hit endpoints', () async {
    final FakeApiClient client = FakeApiClient()
      ..whenPost('$_base/d1/extractions/e1/confirm', <String, dynamic>{
        'id': 'e1',
        'document_id': 'd1',
        'verification_status': 'user_confirmed',
      })
      ..whenPost('$_base/d1/extractions/e1/reject', <String, dynamic>{
        'id': 'e1',
        'document_id': 'd1',
        'verification_status': 'rejected',
      });

    await _repo(client).confirmExtraction(_caseId, 'd1', 'e1');
    await _repo(client).rejectExtraction(_caseId, 'd1', 'e1');

    expect(client.postPaths, contains('$_base/d1/extractions/e1/confirm'));
    expect(client.postPaths, contains('$_base/d1/extractions/e1/reject'));
  });

  test('delete hits delete endpoint', () async {
    final FakeApiClient client = FakeApiClient();
    await _repo(client).delete(_caseId, 'd1');
    expect(client.deletePaths, contains('$_base/d1'));
  });
}
