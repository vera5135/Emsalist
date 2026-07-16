import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../auth/application/auth_providers.dart';
import '../data/legal_reasoning_repository.dart';
import '../domain/legal_reasoning_workspace.dart';

final Provider<LegalReasoningRepository> legalReasoningRepositoryProvider =
    Provider<LegalReasoningRepository>((ref) {
      return LegalReasoningRepository(
        ref.watch(authenticatedApiClientProvider),
      );
    });

final FutureProviderFamily<LegalReasoningWorkspace, String>
legalReasoningWorkspaceProvider =
    FutureProvider.family<LegalReasoningWorkspace, String>((ref, caseId) {
      return ref.watch(legalReasoningRepositoryProvider).load(caseId);
    });
