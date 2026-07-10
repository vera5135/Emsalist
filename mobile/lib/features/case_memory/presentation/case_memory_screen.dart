import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/constants/app_constants.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/widgets/state_widgets.dart';
import '../application/case_memory_providers.dart';
import '../domain/case_memory.dart';

/// Case memory screen reached from a case: summary + facts, timeline, missing
/// information, contradictions and risks, with verify/reject/edit/resolve
/// actions. Never shows raw technical models or log text to the user.
class CaseMemoryScreen extends ConsumerWidget {
  const CaseMemoryScreen({required this.caseId, super.key});

  final String caseId;

  Future<void> _refresh(WidgetRef ref) async {
    ref.invalidate(caseMemoryProvider(caseId));
    await ref.read(caseMemoryProvider(caseId).future);
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final AsyncValue<CaseMemory> memory = ref.watch(caseMemoryProvider(caseId));
    return DefaultTabController(
      length: 5,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Dosya Hafızası'),
          bottom: const TabBar(
            isScrollable: true,
            tabs: <Widget>[
              Tab(text: 'Özet'),
              Tab(text: 'Olaylar'),
              Tab(text: 'Eksikler'),
              Tab(text: 'Çelişkiler'),
              Tab(text: 'Riskler'),
            ],
          ),
        ),
        body: memory.when(
          loading: () =>
              const LoadingWidget(message: 'Dosya hafızası yükleniyor'),
          error: (Object error, _) => AppErrorWidget(
            message: _messageFor(error),
            onRetry: () => ref.invalidate(caseMemoryProvider(caseId)),
          ),
          data: (CaseMemory data) => RefreshIndicator(
            onRefresh: () => _refresh(ref),
            child: TabBarView(
              children: <Widget>[
                _SummaryTab(memory: data),
                _FactsTimelineTab(caseId: caseId, memory: data),
                _MissingTab(caseId: caseId, memory: data),
                _ContradictionsTab(caseId: caseId, memory: data),
                _RisksTab(memory: data),
              ],
            ),
          ),
        ),
      ),
    );
  }

  static String _messageFor(Object error) {
    if (error is ApiException) {
      return error.message;
    }
    return 'Dosya hafızası yüklenemedi.';
  }
}

String _riskLabel(String severity) {
  switch (severity) {
    case 'critical':
      return 'Kritik';
    case 'high':
      return 'Yüksek';
    case 'medium':
      return 'Orta';
    default:
      return 'Düşük';
  }
}

Color _riskColor(BuildContext context, String severity) {
  final ColorScheme scheme = Theme.of(context).colorScheme;
  switch (severity) {
    case 'critical':
    case 'high':
      return scheme.error;
    case 'medium':
      return scheme.tertiary;
    default:
      return scheme.primary;
  }
}

class _VerificationBadge extends StatelessWidget {
  const _VerificationBadge({required this.status});

  final String status;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    late final String label;
    late final Color color;
    late final IconData icon;
    switch (status) {
      case 'user_confirmed':
      case 'document_verified':
      case 'uyap_verified':
        label = 'Doğrulandı';
        color = theme.colorScheme.primary;
        icon = Icons.verified_outlined;
      case 'conflicting':
        label = 'Çelişkili';
        color = theme.colorScheme.error;
        icon = Icons.error_outline;
      case 'rejected':
        label = 'Reddedildi';
        color = theme.colorScheme.outline;
        icon = Icons.block;
      default:
        label = 'Önerildi';
        color = theme.colorScheme.tertiary;
        icon = Icons.help_outline;
    }
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Icon(icon, size: 14, color: color),
        const SizedBox(width: AppConstants.spacingXs),
        Text(label, style: theme.textTheme.labelSmall?.copyWith(color: color)),
      ],
    );
  }
}

class _SourceChip extends StatelessWidget {
  const _SourceChip({required this.sourceType});

  final String sourceType;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    late final String label;
    switch (sourceType) {
      case 'document_extraction':
      case 'document_verified':
        label = 'Belge';
      case 'uyap_document':
      case 'uyap_movement':
        label = 'UYAP';
      case 'user_manual_entry':
      case 'user_message':
        label = 'Kullanıcı';
      case 'system_inference':
        label = 'Sistem';
      default:
        label = 'Kaynak';
    }
    return Text(
      label,
      style: theme.textTheme.labelSmall?.copyWith(
        color: theme.colorScheme.onSurfaceVariant,
      ),
    );
  }
}

class _SummaryTab extends StatelessWidget {
  const _SummaryTab({required this.memory});

  final CaseMemory memory;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return ListView(
      padding: const EdgeInsets.all(AppConstants.spacingMd),
      children: <Widget>[
        Card(
          child: Padding(
            padding: const EdgeInsets.all(AppConstants.spacingMd),
            child: Row(
              children: <Widget>[
                Icon(
                  Icons.shield_outlined,
                  color: _riskColor(context, memory.overallRiskLevel),
                ),
                const SizedBox(width: AppConstants.spacingSm),
                Text('Genel Risk: ', style: theme.textTheme.titleMedium),
                Text(
                  _riskLabel(memory.overallRiskLevel),
                  style: theme.textTheme.titleMedium?.copyWith(
                    color: _riskColor(context, memory.overallRiskLevel),
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: AppConstants.spacingMd),
        _CountRow(
          label: 'Doğrulanan bilgi',
          value: memory.facts.where((MemoryFact f) => f.isConfirmed).length,
        ),
        _CountRow(label: 'Toplam bilgi', value: memory.facts.length),
        _CountRow(label: 'Kronoloji olayı', value: memory.timeline.length),
        _CountRow(
          label: 'Açık eksik',
          value: memory.missingInformation
              .where((MemoryMissing m) => !m.isResolved)
              .length,
        ),
        _CountRow(
          label: 'Açık çelişki',
          value: memory.contradictions
              .where((MemoryContradiction c) => c.isOpen)
              .length,
        ),
        _CountRow(label: 'Risk', value: memory.risks.length),
      ],
    );
  }
}

class _CountRow extends StatelessWidget {
  const _CountRow({required this.label, required this.value});

  final String label;
  final int value;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppConstants.spacingSm),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: <Widget>[
          Text(label, style: theme.textTheme.bodyMedium),
          Text('$value', style: theme.textTheme.titleMedium),
        ],
      ),
    );
  }
}

class _FactsTimelineTab extends ConsumerWidget {
  const _FactsTimelineTab({required this.caseId, required this.memory});

  final String caseId;
  final CaseMemory memory;

  Future<void> _confirm(WidgetRef ref, String factId) async {
    await ref.read(caseMemoryRepositoryProvider).confirmFact(caseId, factId);
    ref.invalidate(caseMemoryProvider(caseId));
  }

  Future<void> _reject(WidgetRef ref, String factId) async {
    await ref.read(caseMemoryRepositoryProvider).rejectFact(caseId, factId);
    ref.invalidate(caseMemoryProvider(caseId));
  }

  Future<void> _edit(
    BuildContext context,
    WidgetRef ref,
    MemoryFact fact,
  ) async {
    final TextEditingController controller = TextEditingController(
      text: fact.value,
    );
    final String? value = await showDialog<String>(
      context: context,
      builder: (BuildContext ctx) => AlertDialog(
        title: const Text('Bilgiyi düzenle'),
        content: TextField(
          controller: controller,
          autofocus: true,
          decoration: const InputDecoration(border: OutlineInputBorder()),
        ),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('Vazgeç'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(ctx).pop(controller.text),
            child: const Text('Kaydet'),
          ),
        ],
      ),
    );
    if (value != null && value.trim().isNotEmpty) {
      await ref
          .read(caseMemoryRepositoryProvider)
          .updateFactValue(
            caseId,
            fact.id,
            version: fact.version,
            value: value.trim(),
          );
      ref.invalidate(caseMemoryProvider(caseId));
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final ThemeData theme = Theme.of(context);
    if (memory.facts.isEmpty && memory.timeline.isEmpty) {
      return const EmptyWidget(
        title: 'Henüz bilgi yok',
        message: 'Bilgi eklendikçe burada görünecek.',
        icon: Icons.fact_check_outlined,
      );
    }
    return ListView(
      padding: const EdgeInsets.all(AppConstants.spacingMd),
      children: <Widget>[
        if (memory.facts.isNotEmpty)
          Text('Bilgiler', style: theme.textTheme.titleMedium),
        ...memory.facts.map(
          (MemoryFact f) => Card(
            child: ListTile(
              title: Text(f.value.isEmpty ? f.factType : f.value),
              subtitle: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(f.factType),
                  const SizedBox(height: AppConstants.spacingXs),
                  Row(
                    children: <Widget>[
                      _VerificationBadge(status: f.verificationStatus),
                      const SizedBox(width: AppConstants.spacingSm),
                      _SourceChip(sourceType: f.sourceType),
                    ],
                  ),
                ],
              ),
              trailing: PopupMenuButton<String>(
                onSelected: (String action) {
                  switch (action) {
                    case 'confirm':
                      _confirm(ref, f.id);
                    case 'reject':
                      _reject(ref, f.id);
                    case 'edit':
                      _edit(context, ref, f);
                  }
                },
                itemBuilder: (BuildContext ctx) =>
                    const <PopupMenuEntry<String>>[
                      PopupMenuItem<String>(
                        value: 'confirm',
                        child: Text('Doğrula'),
                      ),
                      PopupMenuItem<String>(
                        value: 'reject',
                        child: Text('Reddet'),
                      ),
                      PopupMenuItem<String>(
                        value: 'edit',
                        child: Text('Düzenle'),
                      ),
                    ],
              ),
            ),
          ),
        ),
        if (memory.timeline.isNotEmpty) ...<Widget>[
          const SizedBox(height: AppConstants.spacingMd),
          Text('Kronoloji', style: theme.textTheme.titleMedium),
          ...memory.timeline.map(
            (MemoryEvent e) => Card(
              child: ListTile(
                leading: const Icon(Icons.event_outlined),
                title: Text(e.description),
                subtitle: Text(
                  e.hasDate
                      ? (e.isApproximate ? '~${e.eventDate}' : e.eventDate)
                      : 'Tarih bilinmiyor',
                ),
                trailing: _VerificationBadge(status: e.verificationStatus),
              ),
            ),
          ),
        ],
      ],
    );
  }
}

class _MissingTab extends ConsumerWidget {
  const _MissingTab({required this.caseId, required this.memory});

  final String caseId;
  final CaseMemory memory;

  Future<void> _complete(
    BuildContext context,
    WidgetRef ref,
    String itemId,
  ) async {
    try {
      await ref
          .read(caseMemoryRepositoryProvider)
          .resolveMissing(caseId, itemId);
      ref.invalidate(caseMemoryProvider(caseId));
    } on ApiException catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (memory.missingInformation.isEmpty) {
      return const EmptyWidget(
        title: 'Eksik bilgi yok',
        message: 'Tüm kritik bilgiler mevcut görünüyor.',
        icon: Icons.checklist_outlined,
      );
    }
    return ListView(
      padding: const EdgeInsets.all(AppConstants.spacingMd),
      children: memory.missingInformation.map((MemoryMissing m) {
        return Card(
          child: ListTile(
            leading: Icon(
              m.isResolved ? Icons.check_circle_outline : Icons.error_outline,
              color: m.isResolved
                  ? Theme.of(context).colorScheme.primary
                  : _riskColor(context, m.importance),
            ),
            title: Text(m.label),
            subtitle: Text(m.isResolved ? 'Tamamlandı' : 'Eksik'),
            trailing: m.isResolved
                ? null
                : TextButton(
                    onPressed: () => _complete(context, ref, m.id),
                    child: const Text('Tamamla'),
                  ),
          ),
        );
      }).toList(),
    );
  }
}

class _ContradictionsTab extends ConsumerWidget {
  const _ContradictionsTab({required this.caseId, required this.memory});

  final String caseId;
  final CaseMemory memory;

  Future<void> _resolve(
    BuildContext context,
    WidgetRef ref,
    MemoryContradiction contradiction,
  ) async {
    final List<MemoryFact> candidates = memory.facts
        .where((MemoryFact f) => contradiction.factIds.contains(f.id))
        .toList();
    if (candidates.isEmpty) {
      return;
    }
    final String? chosen = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      builder: (BuildContext ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Padding(
              padding: const EdgeInsets.all(AppConstants.spacingMd),
              child: Text(
                'Doğru değeri seçin',
                style: Theme.of(ctx).textTheme.titleMedium,
              ),
            ),
            ...candidates.map(
              (MemoryFact f) => ListTile(
                title: Text(f.value.isEmpty ? f.factType : f.value),
                onTap: () => Navigator.of(ctx).pop(f.id),
              ),
            ),
          ],
        ),
      ),
    );
    if (chosen != null) {
      await ref
          .read(caseMemoryRepositoryProvider)
          .resolveContradiction(
            caseId,
            contradiction.id,
            resolutionFactId: chosen,
          );
      ref.invalidate(caseMemoryProvider(caseId));
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (memory.contradictions.isEmpty) {
      return const EmptyWidget(
        title: 'Çelişki yok',
        message: 'Bilgiler arasında çelişki tespit edilmedi.',
        icon: Icons.rule_outlined,
      );
    }
    return ListView(
      padding: const EdgeInsets.all(AppConstants.spacingMd),
      children: memory.contradictions.map((MemoryContradiction c) {
        return Card(
          child: ListTile(
            leading: Icon(
              Icons.warning_amber_outlined,
              color: _riskColor(context, c.severity),
            ),
            title: Text(c.description),
            subtitle: Text(c.isOpen ? 'Açık' : 'Çözüldü'),
            trailing: c.isOpen
                ? TextButton(
                    onPressed: () => _resolve(context, ref, c),
                    child: const Text('Çöz'),
                  )
                : null,
          ),
        );
      }).toList(),
    );
  }
}

class _RisksTab extends StatelessWidget {
  const _RisksTab({required this.memory});

  final CaseMemory memory;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    if (memory.risks.isEmpty) {
      return const EmptyWidget(
        title: 'Risk yok',
        message: 'Kayıtlı risk bulunmuyor.',
        icon: Icons.gpp_good_outlined,
      );
    }
    return ListView(
      padding: const EdgeInsets.all(AppConstants.spacingMd),
      children: memory.risks.map((MemoryRisk r) {
        return Card(
          child: ListTile(
            leading: Icon(
              Icons.report_outlined,
              color: _riskColor(context, r.severity),
            ),
            title: Text(r.title),
            subtitle: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text('${r.riskType} · ${_riskLabel(r.severity)}'),
                if (r.rationale.isNotEmpty)
                  Text(r.rationale, style: theme.textTheme.bodySmall),
              ],
            ),
          ),
        );
      }).toList(),
    );
  }
}
