import 'package:flutter/material.dart';

import '../api/inkmoment_api.dart';
import '../design/stitch_components.dart';
import '../design/stitch_layout.dart';
import '../design/stitch_tokens.dart';
import '../l10n/strings.dart';

class AuthGate extends StatefulWidget {
  const AuthGate({
    super.key,
    required this.api,
    required this.auth,
    required this.onAuthorized,
    this.error = '',
  });

  final InkMomentApi api;
  final Map<String, dynamic> auth;
  final String error;
  final ValueChanged<Map<String, dynamic>> onAuthorized;

  @override
  State<AuthGate> createState() => _AuthGateState();
}

class _AuthGateState extends State<AuthGate> {
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _name = TextEditingController();
  final _cdk = TextEditingController();
  final _unbindReason = TextEditingController(text: Zh.defaultUnbindReason);
  bool _registerMode = false;
  bool _loading = false;
  String _message = '';

  bool get _authenticated => widget.auth['authenticated'] == true;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    _name.dispose();
    _cdk.dispose();
    _unbindReason.dispose();
    super.dispose();
  }

  Future<void> _run(Future<Map<String, dynamic>> Function() action) async {
    setState(() {
      _loading = true;
      _message = '';
    });
    try {
      final auth = await action();
      if (!mounted) return;
      widget.onAuthorized(auth);
      if (auth['authorized'] != true) {
        setState(() => _message = _reasonText(auth['reason']));
      }
    } catch (error) {
      if (mounted) setState(() => _message = error.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final compact = StitchLayout.compact(context);
    return Scaffold(
      body: StitchScaffold(
        padding: const EdgeInsets.all(24),
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 1120),
            child: DecoratedBox(
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(StitchRadius.xl),
                border: Border.all(color: StitchColors.borderSoft),
                boxShadow: StitchShadow.soft,
                color: StitchColors.card,
              ),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(StitchRadius.xl),
                child: IntrinsicHeight(
                  child: compact
                      ? _compactLayout(context)
                      : Row(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            Expanded(flex: 5, child: _brandPanel(context)),
                            Expanded(flex: 6, child: _formPanel(context)),
                          ],
                        ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _compactLayout(BuildContext context) {
    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _brandPanel(context),
          _formPanel(context),
        ],
      ),
    );
  }

  Widget _brandPanel(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [StitchColors.background, StitchColors.warmBackground],
        ),
      ),
      padding: const EdgeInsets.all(32),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const StitchPill(label: Zh.authBrand, selected: true),
              const SizedBox(height: 20),
              Text(
                Zh.loginTitle,
                style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                      fontWeight: FontWeight.w800,
                      color: StitchColors.textPrimary,
                      height: 1.12,
                    ),
              ),
              const SizedBox(height: 14),
              Text(
                Zh.operationHintText,
                style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                      color: StitchColors.textMuted,
                      height: 1.55,
                    ),
              ),
              const SizedBox(height: 22),
              Wrap(
                spacing: 10,
                runSpacing: 10,
                children: [
                  StitchPill(
                    label: Zh.account,
                    value: _authenticated ? Zh.signedIn : Zh.signedOut,
                  ),
                  StitchPill(
                    label: Zh.authorization,
                    value: _reasonText(widget.auth['reason']),
                    color: StitchColors.accentDeep,
                  ),
                  StitchPill(
                    label: Zh.service,
                    value: widget.auth['configured'] == false
                        ? Zh.serviceUnavailable
                        : Zh.serviceConfigured,
                  ),
                ],
              ),
            ],
          ),
          const SizedBox(height: 24),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                Zh.appName,
                style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      color: StitchColors.textPrimary,
                      fontWeight: FontWeight.w800,
                    ),
              ),
              const SizedBox(height: 8),
              Text(
                _authenticated ? Zh.authorizedAccount : Zh.waitingTask,
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: StitchColors.textMuted,
                    ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _formPanel(BuildContext context) {
    return Container(
      color: StitchColors.card,
      padding: const EdgeInsets.all(32),
      child: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    _authenticated ? Zh.authorized : Zh.loginTitle,
                    style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                          fontWeight: FontWeight.w800,
                          color: StitchColors.textPrimary,
                        ),
                  ),
                ),
                if (_loading)
                  const Padding(
                    padding: EdgeInsets.only(left: 12),
                    child: SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 10),
            Text(
              _authenticated ? Zh.authRefreshed : Zh.chooseModeAndFolder,
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: StitchColors.textMuted,
                    height: 1.5,
                  ),
            ),
            const SizedBox(height: 22),
            _statusRow(context),
            const SizedBox(height: 22),
            if (!_authenticated) _accountForm(context) else _redeemForm(context),
            if (_message.isNotEmpty || widget.error.isNotEmpty) ...[
              const SizedBox(height: 18),
              StitchWarning(message: _message.isNotEmpty ? _message : widget.error),
            ],
          ],
        ),
      ),
    );
  }

  Widget _statusRow(BuildContext context) {
    return Wrap(
      spacing: 10,
      runSpacing: 10,
      children: [
        StitchPill(label: Zh.account, value: _authenticated ? Zh.signedIn : Zh.signedOut),
        StitchPill(label: Zh.authorization, value: _reasonText(widget.auth['reason']), color: StitchColors.accentDeep),
        StitchPill(
          label: Zh.service,
          value: widget.auth['configured'] == false ? Zh.serviceUnavailable : Zh.serviceConfigured,
        ),
      ],
    );
  }

  Widget _accountForm(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _modeSwitcher(),
        const SizedBox(height: 18),
        _field(_email, Zh.email),
        _field(_password, Zh.password, obscure: true),
        if (_registerMode) _field(_name, Zh.displayName),
        const SizedBox(height: 10),
        FilledButton(
          onPressed: _loading
              ? null
              : () => _run(
                  () => _registerMode
                      ? widget.api.register(
                          _email.text.trim(),
                          _password.text,
                          _name.text.trim(),
                        )
                      : widget.api.login(_email.text.trim(), _password.text),
                ),
          child: Text(_registerMode ? Zh.registerAndBind : Zh.login),
        ),
      ],
    );
  }

  Widget _redeemForm(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _field(_cdk, Zh.cdk),
        FilledButton(
          onPressed: _loading ? null : () => _run(() => widget.api.redeem(_cdk.text.trim())),
          child: const Text(Zh.redeem),
        ),
        const SizedBox(height: 10),
        OutlinedButton(
          onPressed: _loading ? null : () => _run(() => widget.api.authStatus(force: true)),
          child: const Text(Zh.refreshAuth),
        ),
        const SizedBox(height: 18),
        _field(_unbindReason, Zh.unbindReason),
        OutlinedButton(
          onPressed: _loading
              ? null
              : () => _run(() => widget.api.unbindDevice(_unbindReason.text.trim())),
          child: const Text(Zh.unbindDevice),
        ),
        const SizedBox(height: 10),
        TextButton(
          onPressed: _loading ? null : () => _run(() => widget.api.logout()),
          child: const Text(Zh.logout),
        ),
      ],
    );
  }

  Widget _modeSwitcher() {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: StitchColors.cardGlow,
        borderRadius: BorderRadius.circular(StitchRadius.md),
        border: Border.all(color: StitchColors.borderSoft),
      ),
      child: Row(
        children: [
          Expanded(
            child: _switchButton(
              label: Zh.login,
              selected: !_registerMode,
              onTap: () => setState(() => _registerMode = false),
            ),
          ),
          Expanded(
            child: _switchButton(
              label: Zh.register,
              selected: _registerMode,
              onTap: () => setState(() => _registerMode = true),
            ),
          ),
        ],
      ),
    );
  }

  Widget _switchButton({
    required String label,
    required bool selected,
    required VoidCallback onTap,
  }) {
    final textColor = selected ? StitchColors.accentDeep : StitchColors.textMuted;
    return Material(
      color: selected ? StitchColors.accentSoft : Colors.transparent,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 13),
          child: Text(
            label,
            textAlign: TextAlign.center,
            style: TextStyle(
              color: textColor,
              fontWeight: FontWeight.w800,
            ),
          ),
        ),
      ),
    );
  }

  Widget _field(
    TextEditingController controller,
    String label, {
    bool obscure = false,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: TextField(
        controller: controller,
        obscureText: obscure,
        decoration: InputDecoration(labelText: label),
      ),
    );
  }

  String _reasonText(Object? reason) => switch (reason?.toString()) {
        'active' => Zh.authorized,
        'unauthenticated' => Zh.signedOut,
        'not_activated' => Zh.notActivated,
        'expired' => Zh.expired,
        'revoked' => Zh.revoked,
        'device_mismatch' => Zh.deviceMismatch,
        'auth_server_not_configured' => Zh.authServerNotConfigured,
        'auth_not_configured' => Zh.authServerNotConfigured,
        'auth_server_unavailable' => Zh.authServerUnavailable,
        'auth_check_failed' => Zh.authCheckFailed,
        null || '' => Zh.signedOut,
        _ => Zh.authPending,
      };
}
