import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/constants/app_constants.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/widgets/state_widgets.dart';
import '../application/legal_reasoning_providers.dart';
import '../domain/legal_reasoning_workspace.dart';

class LegalReasoningWorkspaceScreen extends ConsumerStatefulWidget {
  const LegalReasoningWorkspaceScreen({required this.caseId, super.key});

  final String caseId;

  @override
  ConsumerState<LegalReasoningWorkspaceScreen> createState() =>
      _LegalReasoningWorkspaceScreenState();
}

class _LegalReasoningWorkspaceScreenState
    extends ConsumerState<LegalReasoningWorkspaceScreen> {
  bool _rebuilding = false;
  bool _findingPrecedents = false;

  Future<void> _rebuild() async {
    setState(() => _rebuilding = true);
    try {
      await ref.read(legalReasoningRepositoryProvider).rebuild(widget.caseId);
      ref.invalidate(legalReasoningWorkspaceProvider(widget.caseId));
      await ref.read(legalReasoningWorkspaceProvider(widget.caseId).future);
    } on ApiException catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(error.message)));
      }
    } finally {
      if (mounted) setState(() => _rebuilding = false);
    }
  }

  Future<void> _findPrecedents(LegalReasoningWorkspace workspace) async {
    setState(() => _findingPrecedents = true);
    try {
      await ref.read(legalReasoningRepositoryProvider).findPrecedents(workspace);
      ref.invalidate(legalReasoningWorkspaceProvider(widget.caseId));
      await ref.read(legalReasoningWorkspaceProvider(widget.caseId).future);
    } on ApiException catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(error.message)));
      }
    } finally {
      if (mounted) setState(() => _findingPrecedents = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final AsyncValue<LegalReasoningWorkspace> value = ref.watch(
      legalReasoningWorkspaceProvider(widget.caseId),
    );
    return Scaffold(
      appBar: AppBar(
        title: const Text('Hukuki Konular'),
        actions: <Widget>[
          IconButton(
            tooltip: 'Hukuki konuları yeniden oluştur',
            onPressed: _rebuilding ? null : _rebuild,
            icon: _rebuilding
                ? const SizedBox.square(
                    dimension: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.refresh),
          ),
        ],
      ),
      body: value.when(
        loading: () =>
            const LoadingWidget(message: 'Hukuki konu grafiği yükleniyor'),
        error: (Object error, _) => AppErrorWidget(
          message: error is ApiException
              ? error.message
              : 'Hukuki konu grafiği yüklenemedi.',
          onRetry: () =>
              ref.invalidate(legalReasoningWorkspaceProvider(widget.caseId)),
        ),
        data: (LegalReasoningWorkspace workspace) => workspace.isEmpty
            ? Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: <Widget>[
                  const EmptyWidget(
                    title: 'Henüz hukuki konu yok',
                    message:
                        'Dosya bilgilerini analiz ederek konu grafiği oluşturun.',
                    icon: Icons.account_tree_outlined,
                  ),
                  FilledButton.icon(
                    onPressed: _rebuilding ? null : _rebuild,
                    icon: const Icon(Icons.auto_awesome_outlined),
                    label: const Text('Oluştur'),
                  ),
                ],
              )
            : _WorkspaceBody(
                workspace: workspace,
                findingPrecedents: _findingPrecedents,
                onFindPrecedents: () => _findPrecedents(workspace),
              ),
      ),
    );
  }
}

class _WorkspaceBody extends StatelessWidget {
  const _WorkspaceBody({
    required this.workspace,
    required this.findingPrecedents,
    required this.onFindPrecedents,
  });

  final LegalReasoningWorkspace workspace;
  final bool findingPrecedents;
  final VoidCallback onFindPrecedents;

  @override
  Widget build(BuildContext context) {
    final Map<String, List<LegalIssueSummary>> children =
        <String, List<LegalIssueSummary>>{};
    for (final LegalIssueSummary issue in workspace.issues) {
      if (issue.parentIssueId != null) {
        children.putIfAbsent(issue.parentIssueId!, () => []).add(issue);
      }
    }
    final List<LegalIssueSummary> roots = workspace.issues
        .where((LegalIssueSummary issue) => issue.parentIssueId == null)
        .toList();
    return ListView(
      padding: const EdgeInsets.all(AppConstants.spacingMd),
      children: <Widget>[
        _PrecedentPoolSection(
          workspace: workspace,
          loading: findingPrecedents,
          onFind: onFindPrecedents,
        ),
        if (workspace.stale)
          const Card(
            child: ListTile(
              leading: Icon(Icons.update_outlined),
              title: Text('Analiz güncel değil'),
              subtitle: Text(
                'Dosya veya kaynaklar değişti; yeniden oluşturun.',
              ),
            ),
          ),
        ...roots.map(
          (LegalIssueSummary issue) => _IssueCard(
            issue: issue,
            children: children[issue.id] ?? const <LegalIssueSummary>[],
            workspace: workspace,
          ),
        ),
        if (workspace.missingInformation.isNotEmpty)
          _SimpleSection(
            title: 'Eksik bilgiler',
            icon: Icons.help_outline,
            items: workspace.missingInformation,
            label: (item) => item['label'] as String? ?? 'Eksik bilgi',
          ),
        if (workspace.unsupportedClaims.isNotEmpty)
          _SimpleSection(
            title: 'Desteksiz iddialar',
            icon: Icons.link_off_outlined,
            items: workspace.unsupportedClaims,
            label: (item) => item['title'] as String? ?? 'Desteksiz iddia',
          ),
      ],
    );
  }
}

class _PrecedentPoolSection extends StatelessWidget {
  const _PrecedentPoolSection({
    required this.workspace,
    required this.loading,
    required this.onFind,
  });

  final LegalReasoningWorkspace workspace;
  final bool loading;
  final VoidCallback onFind;

  @override
  Widget build(BuildContext context) {
    final PrecedentPoolWorkspace? pool = workspace.precedentPool;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Row(
              children: <Widget>[
                const Expanded(
                  child: Text(
                    'Emsal havuzu',
                    style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
                  ),
                ),
                FilledButton.icon(
                  onPressed: loading ? null : onFind,
                  icon: loading
                      ? const SizedBox.square(
                          dimension: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.search_outlined),
                  label: const Text('Dosyaya göre emsal bul'),
                ),
              ],
            ),
            const SizedBox(height: 8),
            if (pool == null)
              const Text('Bu dosya için henüz dinamik emsal havuzu yok.'),
            if (pool != null) ...<Widget>[
              _ProfileSummary(pool.pool.profileSummary),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: <Widget>[
                  Chip(label: Text(_providerStatus(pool.pool.providerStatus))),
                  Chip(label: Text('Bulunan: ${pool.pool.totalDiscovered}')),
                  Chip(label: Text('İşlenen: ${pool.pool.totalIngested}')),
                  Chip(label: Text('Mükerrer: ${pool.pool.totalDuplicate}')),
                  Chip(label: Text('Hata: ${pool.pool.totalFailed}')),
                ],
              ),
              if (pool.pool.degraded)
                const Padding(
                  padding: EdgeInsets.only(top: 8),
                  child: Text(
                    'Canlı sağlayıcı tamamlanamadı; yalnızca mevcut resmi korpus arandı.',
                  ),
                ),
              if (pool.pool.partial)
                const Padding(
                  padding: EdgeInsets.only(top: 8),
                  child: Text('Bazı sağlayıcı istekleri başarısız oldu; mevcut sonuçlarla devam edildi.'),
                ),
              if (pool.isEmpty)
                const Padding(
                  padding: EdgeInsets.only(top: 12),
                  child: Text('Kısa listeye alınan karar bulunamadı.'),
                )
              else
                ...pool.decisions.map(
                  (PrecedentDecision decision) => _PrecedentDecisionTile(
                    decision: decision,
                    analysis: _analysisFor(pool.analyses, decision.id),
                  ),
                ),
            ],
          ],
        ),
      ),
    );
  }
}

class _ProfileSummary extends StatelessWidget {
  const _ProfileSummary(this.summary);

  final Map<String, dynamic> summary;

  @override
  Widget build(BuildContext context) {
    final String area = summary['legal_area'] as String? ?? '';
    final String dispute = summary['dispute_type'] as String? ?? '';
    if (area.isEmpty && dispute.isEmpty) return const SizedBox.shrink();
    return Text([area, dispute].where((String value) => value.isNotEmpty).join(' · '));
  }
}

class _PrecedentDecisionTile extends StatelessWidget {
  const _PrecedentDecisionTile({required this.decision, required this.analysis});

  final PrecedentDecision decision;
  final PrecedentAnalysis? analysis;

  @override
  Widget build(BuildContext context) {
    final Map<String, dynamic> data = analysis?.analysis ?? const <String, dynamic>{};
    return ExpansionTile(
      leading: const Icon(Icons.verified_outlined),
      title: Text(
        '${decision.chamber.isEmpty ? decision.court : decision.chamber} '
        'E.${decision.caseNumber} K.${decision.decisionNumber}',
      ),
      subtitle: Text(
        '${decision.decisionDate} · Skor ${(decision.relevanceScore * 100).round()}',
      ),
      childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
      children: <Widget>[
        if (decision.relevantParagraph.isNotEmpty)
          _FieldBlock(title: 'İlgili paragraf', text: decision.relevantParagraph),
        if (decision.matchReasons.isNotEmpty)
          _FieldBlock(title: 'Açıklama', text: decision.matchReasons.join('\n')),
        _ListBlock(title: 'Benzerlikler', values: data['similarities_to_case']),
        _ListBlock(title: 'Farklar', values: data['material_differences']),
        _FieldBlock(title: 'Lehe kullanım', text: data['favorable_use'] as String? ?? ''),
        _FieldBlock(title: 'Aleyhe kullanım', text: data['adverse_opposing_use'] as String? ?? ''),
        _ListBlock(title: 'Eksik olgular', values: data['missing_information']),
        Align(
          alignment: Alignment.centerLeft,
          child: TextButton.icon(
            onPressed: decision.officialUrl.isEmpty
                ? null
                : () => showDialog<void>(
                      context: context,
                      builder: (BuildContext context) => AlertDialog(
                        title: const Text('Resmi kaynak'),
                        content: SelectableText(decision.officialUrl),
                        actions: <Widget>[
                          TextButton(
                            onPressed: () => Navigator.of(context).pop(),
                            child: const Text('Kapat'),
                          ),
                        ],
                      ),
                    ),
            icon: const Icon(Icons.open_in_new_outlined),
            label: const Text('Resmi kaynağı aç'),
          ),
        ),
      ],
    );
  }
}

class _FieldBlock extends StatelessWidget {
  const _FieldBlock({required this.title, required this.text});

  final String title;
  final String text;

  @override
  Widget build(BuildContext context) {
    if (text.trim().isEmpty) return const SizedBox.shrink();
    return Align(
      alignment: Alignment.centerLeft,
      child: Padding(
        padding: const EdgeInsets.only(top: 8),
        child: Text('$title\n$text'),
      ),
    );
  }
}

class _ListBlock extends StatelessWidget {
  const _ListBlock({required this.title, required this.values});

  final String title;
  final Object? values;

  @override
  Widget build(BuildContext context) {
    final List<dynamic> items = values is List<dynamic>
        ? values as List<dynamic>
        : const <dynamic>[];
    if (items.isEmpty) return const SizedBox.shrink();
    return _FieldBlock(
      title: title,
      text: items.map((dynamic value) => value.toString()).join('\n'),
    );
  }
}

PrecedentAnalysis? _analysisFor(List<PrecedentAnalysis> analyses, String id) {
  for (final PrecedentAnalysis analysis in analyses) {
    if (analysis.poolDecisionId == id) return analysis;
  }
  return null;
}

String _providerStatus(String value) => switch (value) {
  'completed' => 'Canlı sağlayıcı tamamlandı',
  'completed_with_errors' => 'Kısmi başarı',
  'degraded_existing_corpus' => 'Mevcut korpus',
  _ => 'Hazırlanıyor',
};

class _IssueCard extends ConsumerWidget {
  const _IssueCard({
    required this.issue,
    required this.children,
    required this.workspace,
  });

  final LegalIssueSummary issue;
  final List<LegalIssueSummary> children;
  final LegalReasoningWorkspace workspace;

  Iterable<Map<String, dynamic>> _forIssue(List<Map<String, dynamic>> rows) =>
      rows.where((row) => row['issue_id'] == issue.id);

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final Iterable<Map<String, dynamic>> burdens = _forIssue(workspace.burdens);
    final Iterable<Map<String, dynamic>> counterarguments = _forIssue(
      workspace.counterarguments,
    );
    final Iterable<Map<String, dynamic>> sources = _forIssue(
      workspace.sourceLinks,
    );
    final Iterable<Map<String, dynamic>> facts = _forIssue(workspace.factLinks);
    final Iterable<Map<String, dynamic>> evidence = _forIssue(
      workspace.evidenceLinks,
    );
    return Card(
      child: ExpansionTile(
        initiallyExpanded: true,
        leading: const Icon(Icons.account_tree_outlined),
        title: Text(issue.title),
        subtitle: Wrap(
          spacing: AppConstants.spacingSm,
          children: <Widget>[
            Chip(label: Text(_supportLabel(issue.supportState))),
            Chip(label: Text(_statusLabel(issue.status))),
          ],
        ),
        childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
        children: <Widget>[
          if (issue.description.isNotEmpty)
            Align(
              alignment: Alignment.centerLeft,
              child: Text(issue.description),
            ),
          OverflowBar(
            children: <Widget>[
              TextButton(
                onPressed: () => _update(ref, 'accepted'),
                child: const Text('Kabul et'),
              ),
              TextButton(
                onPressed: () => _update(ref, 'disputed'),
                child: const Text('İtirazlı işaretle'),
              ),
            ],
          ),
          ...children.map(
            (LegalIssueSummary child) => ListTile(
              contentPadding: const EdgeInsets.only(left: 16),
              leading: const Icon(Icons.subdirectory_arrow_right),
              title: Text(child.title),
              subtitle: Text(_supportLabel(child.supportState)),
            ),
          ),
          ...burdens.map(
            (row) => ListTile(
              leading: const Icon(Icons.balance_outlined),
              title: const Text('İspat yükü'),
              subtitle: Text(
                '${row['burden_type'] ?? 'belirlenmedi'} · '
                '${row['evidence_status'] ?? 'inceleme gerekli'}',
              ),
            ),
          ),
          ...facts.map(
            (row) => ListTile(
              leading: Icon(
                row['relation_type'] == 'fact_contradicts_issue'
                    ? Icons.remove_circle_outline
                    : Icons.add_circle_outline,
              ),
              title: Text(row['fact_label'] as String? ?? 'Bağlı olgu'),
              subtitle: Text(
                row['relation_type'] == 'fact_contradicts_issue'
                    ? 'Çelişiyor'
                    : 'Destekliyor',
              ),
            ),
          ),
          ...evidence.map(
            (row) => ListTile(
              leading: const Icon(Icons.inventory_2_outlined),
              title: Text(row['evidence_label'] as String? ?? 'Bağlı delil'),
              subtitle: Text(_evidenceLabel(row['status'] as String? ?? '')),
            ),
          ),
          ...counterarguments.map(
            (row) => ListTile(
              leading: const Icon(Icons.gavel_outlined),
              title: Text(row['title'] as String? ?? 'Karşı argüman'),
              subtitle: Text(row['rationale'] as String? ?? ''),
            ),
          ),
          ...sources.map(
            (row) => ListTile(
              leading: const Icon(Icons.verified_outlined),
              title: const Text('Kaynak dayanağı'),
              subtitle: Text(
                '${row['source_record_id']} / ${row['source_version_id']} / '
                '${row['source_paragraph_id']}',
              ),
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _update(WidgetRef ref, String status) async {
    await ref.read(legalReasoningRepositoryProvider).updateIssue(issue, status);
    ref.invalidate(legalReasoningWorkspaceProvider(workspace.caseId));
    await ref.read(legalReasoningWorkspaceProvider(workspace.caseId).future);
  }
}

class _SimpleSection extends StatelessWidget {
  const _SimpleSection({
    required this.title,
    required this.icon,
    required this.items,
    required this.label,
  });

  final String title;
  final IconData icon;
  final List<Map<String, dynamic>> items;
  final String Function(Map<String, dynamic>) label;

  @override
  Widget build(BuildContext context) => Card(
    child: ExpansionTile(
      leading: Icon(icon),
      title: Text('$title (${items.length})'),
      children: items
          .map((item) => ListTile(title: Text(label(item))))
          .toList(),
    ),
  );
}

String _supportLabel(String value) => switch (value) {
  'strong' => 'Güçlü destek',
  'partial' => 'Kısmi destek',
  'unsupported' => 'Desteksiz',
  'source_missing' => 'Kaynak eksik',
  _ => 'Belirsiz',
};

String _statusLabel(String value) => switch (value) {
  'needs_review' => 'İnceleme gerekli',
  'resolved' => 'Çözüldü',
  'rejected' => 'Reddedildi',
  _ => 'Belirlendi',
};

String _evidenceLabel(String value) => switch (value) {
  'supported' => 'Destekliyor',
  'contradicted' => 'Çelişiyor',
  'partially_supported' => 'Kısmi destek',
  _ => 'Destek belirsiz',
};
