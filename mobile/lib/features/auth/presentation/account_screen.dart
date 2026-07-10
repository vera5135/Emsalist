import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/constants/app_constants.dart';
import '../../../core/widgets/state_widgets.dart';
import '../application/auth_providers.dart';
import 'auth_error_messages.dart';

/// Account screen: shows Apple link status and offers unlink (password-gated)
/// and logout.
class AccountScreen extends ConsumerStatefulWidget {
  const AccountScreen({super.key});

  @override
  ConsumerState<AccountScreen> createState() => _AccountScreenState();
}

class _AccountScreenState extends ConsumerState<AccountScreen> {
  bool _loading = true;
  bool _linked = false;
  String? _loadError;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _loadStatus();
  }

  Future<void> _loadStatus() async {
    setState(() {
      _loading = true;
      _loadError = null;
    });
    try {
      final bool linked = await ref
          .read(authRepositoryProvider)
          .appleLinkStatus();
      if (!mounted) {
        return;
      }
      setState(() {
        _linked = linked;
        _loading = false;
      });
    } on Object catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _loadError = AuthErrorMessages.forAccount(error);
        _loading = false;
      });
    }
  }

  Future<void> _logout() async {
    if (_busy) {
      return;
    }
    setState(() => _busy = true);
    await ref.read(authControllerProvider.notifier).logout();
    // Router redirects to login on unauthenticated state.
  }

  Future<void> _unlink() async {
    if (_busy) {
      return;
    }
    final String? password = await _promptPassword();
    if (password == null || password.isEmpty) {
      return;
    }
    setState(() => _busy = true);
    try {
      await ref
          .read(authRepositoryProvider)
          .unlinkApple(currentPassword: password);
      if (!mounted) {
        return;
      }
      setState(() => _linked = false);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Apple bağlantısı kaldırıldı.')),
      );
    } on Object catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(AuthErrorMessages.forAccount(error))),
      );
    } finally {
      if (mounted) {
        setState(() => _busy = false);
      }
    }
  }

  Future<String?> _promptPassword() {
    final TextEditingController controller = TextEditingController();
    return showDialog<String>(
      context: context,
      builder: (BuildContext ctx) {
        return AlertDialog(
          title: const Text('Parolanızı doğrulayın'),
          content: TextField(
            controller: controller,
            obscureText: true,
            autofocus: true,
            decoration: const InputDecoration(
              labelText: 'Parola',
              border: OutlineInputBorder(),
            ),
          ),
          actions: <Widget>[
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(),
              child: const Text('Vazgeç'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(ctx).pop(controller.text),
              child: const Text('Onayla'),
            ),
          ],
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('Hesap')),
      body: SafeArea(child: _buildBody(theme)),
    );
  }

  Widget _buildBody(ThemeData theme) {
    if (_loading) {
      return const LoadingWidget(message: 'Hesap bilgileri yükleniyor');
    }
    if (_loadError != null) {
      return AppErrorWidget(message: _loadError, onRetry: _loadStatus);
    }
    return ListView(
      padding: const EdgeInsets.all(AppConstants.spacingMd),
      children: <Widget>[
        ListTile(
          leading: const Icon(Icons.apple),
          title: const Text('Apple ile Giriş'),
          subtitle: Text(_linked ? 'Bağlı' : 'Bağlı değil'),
          trailing: _linked
              ? TextButton(
                  onPressed: _busy ? null : _unlink,
                  child: const Text('Bağlantıyı Kaldır'),
                )
              : null,
        ),
        const Divider(),
        const SizedBox(height: AppConstants.spacingMd),
        FilledButton.tonalIcon(
          onPressed: _busy ? null : _logout,
          icon: const Icon(Icons.logout),
          label: const Text('Çıkış Yap'),
        ),
      ],
    );
  }
}
