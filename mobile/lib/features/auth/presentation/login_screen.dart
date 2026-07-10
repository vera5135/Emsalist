import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/constants/app_constants.dart';
import '../application/auth_providers.dart';
import '../data/auth_repository.dart';
import 'account_link_screen.dart';
import 'auth_error_messages.dart';

/// Sign-in screen: email/password plus "Continue with Apple".
///
/// Handles loading, error and disabled states. When Apple returns
/// `link_required`, routes to [AccountLinkScreen] with the opaque link ticket.
class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final TextEditingController _emailController = TextEditingController();
  final TextEditingController _passwordController = TextEditingController();
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();

  bool _busy = false;
  String? _error;
  bool _obscurePassword = true;

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _submitPassword() async {
    if (_busy) {
      return;
    }
    final FormState? form = _formKey.currentState;
    if (form == null || !form.validate()) {
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref
          .read(authControllerProvider.notifier)
          .loginWithPassword(
            email: _emailController.text,
            password: _passwordController.text,
          );
      // On success the router redirects; nothing else to do here.
    } on Object catch (error) {
      if (!mounted) {
        return;
      }
      setState(() => _error = AuthErrorMessages.forLogin(error));
    } finally {
      if (mounted) {
        setState(() => _busy = false);
      }
    }
  }

  Future<void> _continueWithApple() async {
    if (_busy) {
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final AppleSignInResult result = await ref
          .read(authRepositoryProvider)
          .signInWithApple();
      if (!mounted) {
        return;
      }
      switch (result) {
        case AppleAuthenticated(:final session):
          await ref
              .read(authControllerProvider.notifier)
              .completeAppleAuthenticated(session);
        case AppleLinkRequired(:final String linkTicket):
          await Navigator.of(context).push<void>(
            MaterialPageRoute<void>(
              builder: (BuildContext ctx) =>
                  AccountLinkScreen(linkTicket: linkTicket),
            ),
          );
        case AppleSignInCancelled():
          // User cancelled — no error UI.
          break;
      }
    } on Object catch (error) {
      if (!mounted) {
        return;
      }
      setState(() => _error = AuthErrorMessages.forLogin(error));
    } finally {
      if (mounted) {
        setState(() => _busy = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final bool appleAvailable = ref.watch(
      authControllerProvider.select((s) => s.appleAvailable),
    );

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(AppConstants.spacingLg),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Form(
                key: _formKey,
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: <Widget>[
                    Text(
                      AppConstants.appName,
                      textAlign: TextAlign.center,
                      style: theme.textTheme.headlineMedium,
                    ),
                    const SizedBox(height: AppConstants.spacingSm),
                    Text(
                      'Hesabınıza giriş yapın',
                      textAlign: TextAlign.center,
                      style: theme.textTheme.bodyMedium?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                    const SizedBox(height: AppConstants.spacingXl),
                    TextFormField(
                      controller: _emailController,
                      enabled: !_busy,
                      keyboardType: TextInputType.emailAddress,
                      autocorrect: false,
                      textInputAction: TextInputAction.next,
                      decoration: const InputDecoration(
                        labelText: 'E-posta',
                        border: OutlineInputBorder(),
                      ),
                      validator: (String? value) {
                        if (value == null || value.trim().isEmpty) {
                          return 'E-posta gerekli';
                        }
                        return null;
                      },
                    ),
                    const SizedBox(height: AppConstants.spacingMd),
                    TextFormField(
                      controller: _passwordController,
                      enabled: !_busy,
                      obscureText: _obscurePassword,
                      textInputAction: TextInputAction.done,
                      onFieldSubmitted: (_) => _submitPassword(),
                      decoration: InputDecoration(
                        labelText: 'Parola',
                        border: const OutlineInputBorder(),
                        suffixIcon: IconButton(
                          tooltip: _obscurePassword
                              ? 'Parolayı göster'
                              : 'Parolayı gizle',
                          icon: Icon(
                            _obscurePassword
                                ? Icons.visibility_outlined
                                : Icons.visibility_off_outlined,
                          ),
                          onPressed: _busy
                              ? null
                              : () => setState(
                                  () => _obscurePassword = !_obscurePassword,
                                ),
                        ),
                      ),
                      validator: (String? value) {
                        if (value == null || value.isEmpty) {
                          return 'Parola gerekli';
                        }
                        return null;
                      },
                    ),
                    if (_error != null) ...<Widget>[
                      const SizedBox(height: AppConstants.spacingMd),
                      _ErrorBanner(message: _error!),
                    ],
                    const SizedBox(height: AppConstants.spacingLg),
                    FilledButton(
                      onPressed: _busy ? null : _submitPassword,
                      child: _busy
                          ? const SizedBox(
                              height: 20,
                              width: 20,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Text('Giriş Yap'),
                    ),
                    if (appleAvailable) ...<Widget>[
                      const SizedBox(height: AppConstants.spacingMd),
                      const _OrDivider(),
                      const SizedBox(height: AppConstants.spacingMd),
                      OutlinedButton.icon(
                        onPressed: _busy ? null : _continueWithApple,
                        icon: const Icon(Icons.apple),
                        label: const Text('Apple ile Devam Et'),
                      ),
                    ],
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _ErrorBanner extends StatelessWidget {
  const _ErrorBanner({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Semantics(
      liveRegion: true,
      label: 'Hata: $message',
      child: Container(
        padding: const EdgeInsets.all(AppConstants.spacingMd),
        decoration: BoxDecoration(
          color: theme.colorScheme.errorContainer,
          borderRadius: BorderRadius.circular(AppConstants.radiusSm),
        ),
        child: Row(
          children: <Widget>[
            Icon(
              Icons.error_outline,
              color: theme.colorScheme.onErrorContainer,
            ),
            const SizedBox(width: AppConstants.spacingSm),
            Expanded(
              child: Text(
                message,
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: theme.colorScheme.onErrorContainer,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _OrDivider extends StatelessWidget {
  const _OrDivider();

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Row(
      children: <Widget>[
        const Expanded(child: Divider()),
        Padding(
          padding: const EdgeInsets.symmetric(
            horizontal: AppConstants.spacingSm,
          ),
          child: Text(
            'veya',
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
        ),
        const Expanded(child: Divider()),
      ],
    );
  }
}
