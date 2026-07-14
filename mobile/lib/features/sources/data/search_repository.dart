import 'search_api.dart';

String searchVerificationBadgeLabel(String status) {
  switch (status) {
    case 'verified_official':
      return 'Resmî kaynaktan doğrulandı';
    case 'verified_secondary':
      return 'İkincil kaynaklarla doğrulandı';
    case 'editor_verified':
      return 'Editör tarafından doğrulandı';
    case 'needs_review':
      return 'İnceleme gerekli';
    case 'conflicting':
      return 'Çelişkili kaynak';
    case 'outdated':
      return 'Eski sürüm';
    case 'superseded':
      return 'Yeni sürümü var';
    case 'repealed':
      return 'Yürürlükten kaldırıldı';
    case 'unavailable':
      return 'Kaynağa şu anda ulaşılamıyor';
    case 'quarantined':
      return 'Kullanıma kapalı';
    default:
      return 'Durum bilinmiyor';
  }
}

String sourceTypeLabel(String type) {
  switch (type) {
    case 'yargitay_karari':
      return 'Yargıtay';
    case 'danistay_karari':
      return 'Danıştay';
    case 'anayasa_mahkemesi_karari':
      return 'AYM';
    case 'kanun':
      return 'Kanun';
    case 'yonetmelik':
      return 'Yönetmelik';
    case 'teblig':
      return 'Tebliğ';
    case 'genelge':
      return 'Genelge';
    case 'kararname':
      return 'Kararname';
    default:
      return type;
  }
}

class SearchResultItem {
  const SearchResultItem({
    required this.resultId,
    required this.sourceId,
    required this.sourceVersionId,
    required this.sourceParagraphId,
    this.sourceType,
    required this.title,
    this.court,
    this.chamber,
    this.caseNumber,
    this.decisionNumber,
    this.decisionDate,
    this.officialUrl,
    this.paragraphSnippet,
    this.articleNumber,
    this.articleKind,
    this.articleLabel,
    required this.verificationStatus,
    required this.temporalStatus,
    required this.finalScore,
    this.semanticScore,
    required this.semanticAvailable,
    required this.degradedMode,
    required this.matchReasons,
  });

  final String resultId;
  final String sourceId;
  final String sourceVersionId;
  final String sourceParagraphId;
  final String? sourceType;
  final String title;
  final String? court;
  final String? chamber;
  final String? caseNumber;
  final String? decisionNumber;
  final String? decisionDate;
  final String? officialUrl;
  final String? paragraphSnippet;
  final String? articleNumber;
  final String? articleKind;
  final String? articleLabel;
  final String verificationStatus;
  final String temporalStatus;
  final double finalScore;
  final double? semanticScore;
  final bool semanticAvailable;
  final bool degradedMode;
  final List<String> matchReasons;

  bool get isOfficial => verificationStatus == 'verified_official';
  String get displayTitle => title.trim().isEmpty ? 'İsimsiz kaynak' : title;

  String get badge => searchVerificationBadgeLabel(verificationStatus);

  String get relevancePercent => '${(finalScore * 100).round()}%';

  String get sourceTypeDisplay =>
      sourceType != null ? sourceTypeLabel(sourceType!) : 'Kaynak';

  factory SearchResultItem.fromJson(Map<String, dynamic> json) {
    return SearchResultItem(
      resultId: json['result_id'] as String? ?? '',
      sourceId: json['source_id'] as String? ?? '',
      sourceVersionId: json['source_version_id'] as String? ?? '',
      sourceParagraphId: json['source_paragraph_id'] as String? ?? '',
      sourceType: json['source_type'] as String?,
      title: json['title'] as String? ?? '',
      court: json['court'] as String?,
      chamber: json['chamber'] as String?,
      caseNumber: json['case_number'] as String?,
      decisionNumber: json['decision_number'] as String?,
      decisionDate: json['decision_date'] as String?,
      officialUrl: json['official_url'] as String?,
      paragraphSnippet: json['paragraph_snippet'] as String?,
      articleNumber: json['article_number'] as String?,
      articleKind: json['article_kind'] as String?,
      articleLabel: json['article_label'] as String?,
      verificationStatus:
          json['verification_status'] as String? ?? 'needs_review',
      temporalStatus: json['temporal_status'] as String? ?? 'unknown',
      finalScore: (json['final_score'] as num?)?.toDouble() ?? 0.0,
      semanticScore: (json['semantic_score'] as num?)?.toDouble(),
      semanticAvailable: json['semantic_available'] as bool? ?? false,
      degradedMode: json['degraded_mode'] as bool? ?? false,
      matchReasons:
          (json['match_reasons'] as List<dynamic>?)
              ?.map((dynamic e) => e.toString())
              .toList() ??
          const <String>[],
    );
  }
}

class SearchResultPage {
  const SearchResultPage({
    required this.results,
    required this.total,
    required this.hasMore,
    this.nextCursor,
    this.queryId,
    this.indexVersion,
    required this.semanticAvailable,
    required this.degradedMode,
  });

  final List<SearchResultItem> results;
  final int total;
  final bool hasMore;
  final String? nextCursor;
  final String? queryId;
  final String? indexVersion;
  final bool semanticAvailable;
  final bool degradedMode;

  factory SearchResultPage.fromJson(Map<String, dynamic> json) {
    final List<dynamic> rawResults =
        json['results'] as List<dynamic>? ?? const <dynamic>[];
    return SearchResultPage(
      results: rawResults
          .map(
            (dynamic e) => SearchResultItem.fromJson(e as Map<String, dynamic>),
          )
          .toList(),
      total: json['total'] as int? ?? 0,
      hasMore: json['has_more'] as bool? ?? false,
      nextCursor: json['next_cursor'] as String?,
      queryId: json['query_id'] as String?,
      indexVersion: json['index_version'] as String?,
      semanticAvailable: json['semantic_available'] as bool? ?? false,
      degradedMode: json['degraded_mode'] as bool? ?? false,
    );
  }
}

class SearchRepository {
  const SearchRepository(this._api);

  final SearchApi _api;

  Future<SearchResultPage> searchLegal({
    required String query,
    String? caseId,
    bool? officialOnly,
    List<String>? sourceTypes,
    String? court,
    int? limit,
    String? cursor,
    Object? cancelToken,
  }) async {
    final Map<String, dynamic> json = await _api.searchLegal(
      query: query,
      caseId: caseId,
      officialOnly: officialOnly,
      sourceTypes: sourceTypes,
      court: court,
      limit: limit,
      cursor: cursor,
      cancelToken: cancelToken,
    );
    return SearchResultPage.fromJson(json);
  }

  Future<SearchResultPage> searchSimilar({
    required String sourceId,
    String? sourceParagraphId,
    int? limit,
    Object? cancelToken,
  }) async {
    final Map<String, dynamic> json = await _api.searchSimilar(
      sourceId: sourceId,
      sourceParagraphId: sourceParagraphId,
      limit: limit,
      cancelToken: cancelToken,
    );
    return SearchResultPage.fromJson(json);
  }

  Future<SearchResultPage> searchOpposing({
    required String sourceId,
    Object? cancelToken,
  }) async {
    final Map<String, dynamic> json = await _api.searchOpposing(
      sourceId: sourceId,
      cancelToken: cancelToken,
    );
    return SearchResultPage.fromJson(json);
  }

  Future<List<String>> getSuggestions(
    String prefix, {
    Object? cancelToken,
  }) async {
    final Map<String, dynamic> envelope = await _api.getSuggestions(
      prefix,
      cancelToken: cancelToken,
    );
    final List<dynamic> raw =
        envelope['suggestions'] as List<dynamic>? ?? <dynamic>[];
    return raw.map((dynamic e) => e.toString()).toList();
  }

  Future<void> submitFeedback(
    String resultId,
    String feedbackType,
    String queryId, {
    Object? cancelToken,
  }) {
    return _api.submitFeedback(
      resultId,
      feedbackType,
      queryId,
      cancelToken: cancelToken,
    );
  }
}
