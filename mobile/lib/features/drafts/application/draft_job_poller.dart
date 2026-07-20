import 'dart:async';
import 'dart:math';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_exception.dart';
import '../data/draft_repository.dart';
import '../domain/draft_item.dart';
import 'draft_providers.dart';

class DraftGenerationJobState {
  const DraftGenerationJobState({
    this.status = '',
    this.stage = '',
    this.progressPercent = 0,
    this.jobId,
    this.draftId,
    this.safeErrorCode,
    this.isPolling = false,
    this.enqueueError,
    this.clientRequestId,
  });

  final String status;
  final String stage;
  final int progressPercent;
  final String? jobId;
  final String? draftId;
  final String? safeErrorCode;
  final bool isPolling;
  final String? enqueueError;
  final String? clientRequestId;

  bool get isTerminal =>
      status == 'succeeded' || status == 'failed' || enqueueError != null;

  DraftGenerationJobState copyWith({
    String? status,
    String? stage,
    int? progressPercent,
    String? jobId,
    bool clearJobId = false,
    String? draftId,
    bool clearDraftId = false,
    String? safeErrorCode,
    bool clearSafeErrorCode = false,
    bool? isPolling,
    String? enqueueError,
    bool clearEnqueueError = false,
    String? clientRequestId,
    bool clearClientRequestId = false,
  }) {
    return DraftGenerationJobState(
      status: status ?? this.status,
      stage: stage ?? this.stage,
      progressPercent: progressPercent ?? this.progressPercent,
      jobId: clearJobId ? null : (jobId ?? this.jobId),
      draftId: clearDraftId ? null : (draftId ?? this.draftId),
      safeErrorCode: clearSafeErrorCode
          ? null
          : (safeErrorCode ?? this.safeErrorCode),
      isPolling: isPolling ?? this.isPolling,
      enqueueError: clearEnqueueError
          ? null
          : (enqueueError ?? this.enqueueError),
      clientRequestId: clearClientRequestId
          ? null
          : (clientRequestId ?? this.clientRequestId),
    );
  }
}

class DraftGenerationJobNotifier
    extends StateNotifier<DraftGenerationJobState> {
  DraftGenerationJobNotifier(
    this._repo,
    this._ref, {
    this.pollInterval = const Duration(seconds: 3),
    Timer? timer,
  }) : _timer = timer,
       super(const DraftGenerationJobState());

  final DraftRepository _repo;
  final Ref _ref;
  final Duration pollInterval;
  Timer? _timer;

  Future<void> enqueue({
    required String caseId,
    required String draftId,
    required int draftVersion,
    String? clientRequestId,
    List<String>? selectedIssueIds,
    List<String>? selectedSourceUsageIds,
  }) async {
    final String requestId =
        clientRequestId ?? state.clientRequestId ?? _generateClientRequestId();
    state = state.copyWith(
      draftId: draftId,
      clientRequestId: requestId,
      clearEnqueueError: true,
    );

    try {
      final DraftGenerationJobItem job = await _repo.enqueueGenerationJob(
        caseId,
        draftId,
        draftVersion: draftVersion,
        clientRequestId: requestId,
        selectedIssueIds: selectedIssueIds,
        selectedSourceUsageIds: selectedSourceUsageIds,
      );

      state = state.copyWith(
        status: job.status,
        stage: job.stage,
        progressPercent: job.progressPercent,
        jobId: job.jobId,
        draftId: job.draftId,
        safeErrorCode: job.safeErrorCode,
        isPolling: !job.isTerminal,
      );

      if (!job.isTerminal) {
        _startPolling(caseId, draftId);
      }
    } on ApiException catch (e) {
      if (e.statusCode == 409) {
        state = state.copyWith(
          enqueueError:
              'Bu taslak için zaten bir oluşturma işlemi devam ediyor.',
        );
      } else {
        state = state.copyWith(enqueueError: e.message);
      }
    } on Object {
      state = state.copyWith(enqueueError: 'Oluşturma işlemi başlatılamadı.');
    }
  }

  Future<void> _poll(String caseId, String draftId) async {
    final String? jobId = state.jobId;
    if (jobId == null) {
      _stopPolling();
      return;
    }

    try {
      final DraftGenerationJobItem job = await _repo.getGenerationJob(
        caseId,
        draftId,
        jobId,
      );

      state = state.copyWith(
        status: job.status,
        stage: job.stage,
        progressPercent: job.progressPercent,
        safeErrorCode: job.safeErrorCode,
      );

      if (job.isTerminal) {
        _stopPolling();

        if (job.status == 'succeeded') {
          _ref.invalidate(
            draftDetailProvider((caseId: caseId, draftId: draftId)),
          );
        }
      }
    } on ApiException {
      _stopPolling();
      state = state.copyWith(safeErrorCode: 'poll_failed');
    } on Object {
      // Continue polling on transient errors.
    }
  }

  void _startPolling(String caseId, String draftId) {
    _timer?.cancel();
    _timer = Timer.periodic(pollInterval, (_) => _poll(caseId, draftId));
  }

  void _stopPolling() {
    _timer?.cancel();
    _timer = null;
    state = state.copyWith(isPolling: false);
  }

  @override
  void dispose() {
    _timer?.cancel();
    _timer = null;
    super.dispose();
  }

  String _generateClientRequestId() {
    final Random random = Random();
    final String ts = DateTime.now().microsecondsSinceEpoch.toRadixString(36);
    final String rand = List<String>.generate(
      8,
      (_) => random.nextInt(16).toRadixString(16),
    ).join();
    return '$ts$rand';
  }
}

final draftGenerationJobProvider = StateNotifierProvider.autoDispose
    .family<
      DraftGenerationJobNotifier,
      DraftGenerationJobState,
      ({String caseId, String draftId})
    >((ref, params) {
      return DraftGenerationJobNotifier(
        ref.watch(draftRepositoryProvider),
        ref,
      );
    });
