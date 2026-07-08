import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/case_model.dart';

class CaseState {
  const CaseState({required this.cases, this.activeCaseId});

  final List<CaseModel> cases;
  final String? activeCaseId;

  CaseModel? get activeCase {
    if (activeCaseId == null) {
      return cases.isNotEmpty ? cases.first : null;
    }
    for (final CaseModel c in cases) {
      if (c.id == activeCaseId) {
        return c;
      }
    }
    return cases.isNotEmpty ? cases.first : null;
  }

  List<CaseModel> get pinned =>
      cases.where((CaseModel c) => c.pinned && !c.archived).toList();

  List<CaseModel> get recent =>
      cases.where((CaseModel c) => !c.pinned && !c.archived).toList();

  List<CaseModel> get archived =>
      cases.where((CaseModel c) => c.archived).toList();

  CaseState copyWith({List<CaseModel>? cases, String? activeCaseId}) {
    return CaseState(
      cases: cases ?? this.cases,
      activeCaseId: activeCaseId ?? this.activeCaseId,
    );
  }
}

class CaseNotifier extends StateNotifier<CaseState> {
  CaseNotifier()
      : super(
          CaseState(
            cases: CaseModel.mockCases(),
            activeCaseId: CaseModel.mockCases().first.id,
          ),
        );

  void selectCase(String id) {
    state = state.copyWith(activeCaseId: id);
  }

  void addCase(CaseModel model) {
    state = state.copyWith(cases: <CaseModel>[model, ...state.cases]);
  }

  void togglePinned(String id) {
    state = state.copyWith(
      cases: state.cases
          .map((CaseModel c) => c.id == id ? c.copyWith(pinned: !c.pinned) : c)
          .toList(),
    );
  }
}

final StateNotifierProvider<CaseNotifier, CaseState> caseProvider =
    StateNotifierProvider<CaseNotifier, CaseState>(
  (Ref ref) => CaseNotifier(),
);
