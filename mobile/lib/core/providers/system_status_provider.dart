import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../config/app_environment.dart';
import '../data/system/system_repository.dart';
import 'api_client_provider.dart';

/// The active build environment, exposed for the System Status UI.
final Provider<AppEnvironment> appEnvironmentProvider =
    Provider<AppEnvironment>((ref) => AppEnvironment.current());

/// Loads the backend [SystemStatus].
///
/// Errors (network, timeout, server, and configuration) propagate as the
/// provider's error state so the UI can render them safely. Reading
/// [systemRepositoryProvider] may throw [ApiConfigurationException] for
/// staging/production without `API_BASE_URL`; that surfaces here as an error.
final FutureProvider<SystemStatus> systemStatusProvider =
    FutureProvider<SystemStatus>((ref) async {
      final SystemRepository repository = ref.watch(systemRepositoryProvider);
      return repository.fetchStatus();
    });
