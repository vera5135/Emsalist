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
            : _WorkspaceBody(workspace: workspace),
      ),
    );
  }
}

class _WorkspaceBody extends StatelessWidget {
  const _WorkspaceBody({required this.workspace});

  final LegalReasoningWorkspace workspace;

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

class _IssueCard extends StatelessWidget {
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
  Widget build(BuildContext context) {
    final Iterable<Map<String, dynamic>> burdens = _forIssue(workspace.burdens);
    final Iterable<Map<String, dynamic>> counterarguments = _forIssue(
      workspace.counterarguments,
    );
    final Iterable<Map<String, dynamic>> sources = _forIssue(
      workspace.sourceLinks,
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
