import 'dart:typed_data';

import '../../../core/network/api_client.dart';
import '../../../core/network/download_service.dart';
import 'models/draft_dto.dart';

class DraftApi {
  const DraftApi(this._client);

  final ApiClient _client;

  static const String _base = '/api/v1/cases';

  String _caseDrafts(String caseId) => '$_base/$caseId/drafts';

  String _draftPath(String caseId, String draftId) =>
      '$_base/$caseId/drafts/$draftId';

  String _paragraphsPath(String caseId, String draftId) =>
      '$_base/$caseId/drafts/$draftId/paragraphs';

  String _paragraphPath(String caseId, String draftId, String paragraphId) =>
      '$_base/$caseId/drafts/$draftId/paragraphs/$paragraphId';

  Future<DraftListDto> listDrafts(String caseId) async {
    final Map<String, dynamic> json = await _client
        .getJson<Map<String, dynamic>>(_caseDrafts(caseId));
    return DraftListDto.fromJson(json);
  }

  Future<DraftDto> createDraft(
    String caseId, {
    required String title,
    required String draftType,
    String? supersedesDraftId,
  }) async {
    final body = DraftCreateRequestDto(
      title: title,
      draftType: draftType,
      supersedesDraftId: supersedesDraftId,
    ).toJson();
    final Map<String, dynamic> json = await _client
        .postJson<Map<String, dynamic>>(_caseDrafts(caseId), body: body);
    return DraftDto.fromJson(json);
  }

  Future<DraftDetailDto> getDraft(String caseId, String draftId) async {
    final Map<String, dynamic> json = await _client
        .getJson<Map<String, dynamic>>(_draftPath(caseId, draftId));
    return DraftDetailDto.fromJson(json);
  }

  Future<DraftDto> updateDraft(
    String caseId,
    String draftId, {
    required int version,
    String? title,
    String? status,
  }) async {
    final Map<String, dynamic> body = <String, dynamic>{'version': version};
    if (title != null) body['title'] = title;
    if (status != null) body['status'] = status;
    final Map<String, dynamic> json = await _client
        .patchJson<Map<String, dynamic>>(
          _draftPath(caseId, draftId),
          body: body,
        );
    return DraftDto.fromJson(json);
  }

  Future<void> deleteDraft(String caseId, String draftId) async {
    await _client.deleteJson<dynamic>(_draftPath(caseId, draftId));
  }

  Future<DraftParagraphDto> createParagraph(
    String caseId,
    String draftId, {
    required int order,
    required String paragraphType,
    required String text,
  }) async {
    final Map<String, dynamic> json = await _client
        .postJson<Map<String, dynamic>>(
          _paragraphsPath(caseId, draftId),
          body: <String, dynamic>{
            'order': order,
            'paragraph_type': paragraphType,
            'text': text,
          },
        );
    return DraftParagraphDto.fromJson(json);
  }

  Future<DraftParagraphDto> updateParagraph(
    String caseId,
    String draftId,
    String paragraphId, {
    required int version,
    String? text,
    String? paragraphType,
    int? order,
    String? verificationStatus,
  }) async {
    final Map<String, dynamic> body = <String, dynamic>{'version': version};
    if (text != null) body['text'] = text;
    if (paragraphType != null) body['paragraph_type'] = paragraphType;
    if (order != null) body['order'] = order;
    if (verificationStatus != null) {
      body['verification_status'] = verificationStatus;
    }
    final Map<String, dynamic> json = await _client
        .patchJson<Map<String, dynamic>>(
          _paragraphPath(caseId, draftId, paragraphId),
          body: body,
        );
    return DraftParagraphDto.fromJson(json);
  }

  Future<DraftIssueLinkDto> addIssueLink(
    String caseId,
    String draftId,
    String paragraphId,
    String legalIssueId,
  ) async {
    final Map<String, dynamic> json = await _client
        .postJson<Map<String, dynamic>>(
          '${_paragraphPath(caseId, draftId, paragraphId)}/issue-links',
          body: <String, dynamic>{'legal_issue_id': legalIssueId},
        );
    return DraftIssueLinkDto.fromJson(json);
  }

  Future<DraftSourceLinkDto> addSourceLink(
    String caseId,
    String draftId,
    String paragraphId, {
    required String sourceRecordId,
    required String sourceVersionId,
    String? sourceParagraphId,
    required String usageType,
    required String quoteHash,
  }) async {
    final Map<String, dynamic> body = <String, dynamic>{
      'source_record_id': sourceRecordId,
      'source_version_id': sourceVersionId,
      'usage_type': usageType,
      'quote_hash': quoteHash,
    };
    if (sourceParagraphId != null) {
      body['source_paragraph_id'] = sourceParagraphId;
    }
    final Map<String, dynamic> json = await _client
        .postJson<Map<String, dynamic>>(
          '${_paragraphPath(caseId, draftId, paragraphId)}/source-links',
          body: body,
        );
    return DraftSourceLinkDto.fromJson(json);
  }

  Future<DraftReadinessDto> checkReadiness(
    String caseId,
    String draftId,
  ) async {
    final Map<String, dynamic> json = await _client
        .getJson<Map<String, dynamic>>(
          '${_draftPath(caseId, draftId)}/readiness',
        );
    return DraftReadinessDto.fromJson(json);
  }

  Future<DraftPlanDto> getPlan(String caseId, String draftId) async {
    final Map<String, dynamic> json = await _client
        .getJson<Map<String, dynamic>>('${_draftPath(caseId, draftId)}/plan');
    return DraftPlanDto.fromJson(json);
  }

  Future<DraftValidationDto> validateDraft(
    String caseId,
    String draftId,
  ) async {
    final Map<String, dynamic> json = await _client
        .getJson<Map<String, dynamic>>(
          '${_draftPath(caseId, draftId)}/validate',
        );
    return DraftValidationDto.fromJson(json);
  }

  Future<DraftFinalizeDto> finalizeDraft(
    String caseId,
    String draftId, {
    required int version,
  }) async {
    final Map<String, dynamic> json = await _client
        .postJson<Map<String, dynamic>>(
          '${_draftPath(caseId, draftId)}/finalize',
          body: <String, dynamic>{'version': version},
        );
    return DraftFinalizeDto.fromJson(json);
  }

  Future<DraftRevisionActionDto> editParagraph(
    String caseId,
    String draftId,
    String paragraphId, {
    required int draftVersion,
    required int paragraphVersion,
    required String text,
  }) async {
    final Map<String, dynamic> json = await _client
        .postJson<Map<String, dynamic>>(
          '${_paragraphPath(caseId, draftId, paragraphId)}/edit',
          body: <String, dynamic>{
            'draft_version': draftVersion,
            'paragraph_version': paragraphVersion,
            'text': text,
          },
        );
    return DraftRevisionActionDto.fromJson(json);
  }

  Future<DraftReviewActionDto> acceptParagraph(
    String caseId,
    String draftId,
    String paragraphId, {
    required int draftVersion,
    required int paragraphVersion,
    required String revisionId,
  }) async {
    final Map<String, dynamic> json = await _client
        .postJson<Map<String, dynamic>>(
          '${_paragraphPath(caseId, draftId, paragraphId)}/accept',
          body: <String, dynamic>{
            'draft_version': draftVersion,
            'paragraph_version': paragraphVersion,
            'revision_id': revisionId,
          },
        );
    return DraftReviewActionDto.fromJson(json);
  }

  Future<DraftReviewActionDto> requestChanges(
    String caseId,
    String draftId,
    String paragraphId, {
    required int draftVersion,
    required int paragraphVersion,
    required String revisionId,
    required String reasonCode,
  }) async {
    final Map<String, dynamic> json = await _client
        .postJson<Map<String, dynamic>>(
          '${_paragraphPath(caseId, draftId, paragraphId)}/request-changes',
          body: <String, dynamic>{
            'draft_version': draftVersion,
            'paragraph_version': paragraphVersion,
            'revision_id': revisionId,
            'reason_code': reasonCode,
          },
        );
    return DraftReviewActionDto.fromJson(json);
  }

  Future<List<DraftRevisionDto>> listRevisions(
    String caseId,
    String draftId,
    String paragraphId,
  ) async {
    final List<dynamic> json = await _client.getJson<List<dynamic>>(
      '${_paragraphPath(caseId, draftId, paragraphId)}/revisions',
    );
    return json
        .map(
          (dynamic e) => DraftRevisionDto.fromJson(e as Map<String, dynamic>),
        )
        .toList();
  }

  Future<DraftRevisionActionDto> restoreRevision(
    String caseId,
    String draftId,
    String paragraphId, {
    required String revisionId,
    required int draftVersion,
    required int paragraphVersion,
  }) async {
    final Map<String, dynamic>
    json = await _client.postJson<Map<String, dynamic>>(
      '${_paragraphPath(caseId, draftId, paragraphId)}/revisions/$revisionId/restore',
      body: <String, dynamic>{
        'draft_version': draftVersion,
        'paragraph_version': paragraphVersion,
      },
    );
    return DraftRevisionActionDto.fromJson(json);
  }

  Future<List<DraftReviewEventDto>> listReviews(
    String caseId,
    String draftId,
    String paragraphId,
  ) async {
    final List<dynamic> json = await _client.getJson<List<dynamic>>(
      '${_paragraphPath(caseId, draftId, paragraphId)}/reviews',
    );
    return json
        .map(
          (dynamic e) =>
              DraftReviewEventDto.fromJson(e as Map<String, dynamic>),
        )
        .toList();
  }

  Future<DraftGenerationJobDto> enqueueGenerationJob(
    String caseId,
    String draftId, {
    required int draftVersion,
    required String clientRequestId,
    List<String>? selectedIssueIds,
    List<String>? selectedSourceUsageIds,
  }) async {
    final Map<String, dynamic> body = <String, dynamic>{
      'draft_version': draftVersion,
      'client_request_id': clientRequestId,
    };
    if (selectedIssueIds != null) {
      body['selected_issue_ids'] = selectedIssueIds;
    }
    if (selectedSourceUsageIds != null) {
      body['selected_source_usage_ids'] = selectedSourceUsageIds;
    }
    final Map<String, dynamic> json = await _client
        .postJson<Map<String, dynamic>>(
          '${_draftPath(caseId, draftId)}/generate',
          body: body,
        );
    return DraftGenerationJobDto.fromJson(json);
  }

  Future<DraftGenerationJobDto> getGenerationJob(
    String caseId,
    String draftId,
    String jobId,
  ) async {
    final Map<String, dynamic> json = await _client
        .getJson<Map<String, dynamic>>(
          '${_draftPath(caseId, draftId)}/generate/$jobId',
        );
    return DraftGenerationJobDto.fromJson(json);
  }

  Future<DownloadedFile> downloadDocx(String caseId, String draftId) async {
    final result = await _download(
      '${_draftPath(caseId, draftId)}/export/docx',
    );
    return DownloadedFile(
      bytes: result.bytes,
      filename: result.filename,
      contentType:
          'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    );
  }

  Future<DownloadedFile> downloadPdf(String caseId, String draftId) async {
    final result = await _download('${_draftPath(caseId, draftId)}/export/pdf');
    return DownloadedFile(
      bytes: result.bytes,
      filename: result.filename,
      contentType: 'application/pdf',
    );
  }

  Future<({Uint8List bytes, String filename})> _download(String path) async {
    final result = await _client.downloadBytes(path);
    final String disposition = result.headers['content-disposition'] ?? '';
    String filename = 'download';
    final RegExp re = RegExp(r'''filename[^;=\n]*=["']?([^"';\n]*)["']?''');
    final RegExpMatch? match = re.firstMatch(disposition);
    if (match != null) {
      final String? extracted = match.group(1);
      if (extracted != null && extracted.isNotEmpty) {
        filename = extracted;
      }
    }
    return (bytes: result.bytes, filename: filename);
  }
}
