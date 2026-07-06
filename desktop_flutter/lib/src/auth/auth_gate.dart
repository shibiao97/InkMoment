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
  List<_ClientNotice> _notices = const [];

  bool get _authenticated => widget.auth['authenticated'] == true;
  bool get _authorized => widget.auth['authorized'] == true;

  @override
  void initState() {
    super.initState();
    _loadNotices();
  }

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

  Future<void> _loadNotices() async {
    try {
      final payload = await widget.api.clientNotices();
      if (!mounted) return;
      setState(() {
        _notices = _ClientNotice.fromPayload(payload);
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _notices = const [];
      });
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
                child: !_authenticated
                    ? _formPanel(context)
                    : (compact
                          ? _compactLayout(context)
                          : Row(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Expanded(flex: 5, child: _brandPanel(context)),
                                Expanded(flex: 6, child: _formPanel(context)),
                              ],
                            )),
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
      constraints: const BoxConstraints(minHeight: 560),
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
                    color: _authColor,
                  ),
                  StitchPill(label: Zh.device, value: _deviceName),
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
                _authenticated ? _accountEmail : Zh.waitingTask,
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
              _authenticated ? _authSummaryText : Zh.chooseModeAndFolder,
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: StitchColors.textMuted,
                    height: 1.5,
                  ),
            ),
            const SizedBox(height: 22),
            if (!_authenticated)
              _accountForm(context)
            else ...[
              _statusRow(context),
              const SizedBox(height: 16),
              _noticePanel(context),
              const SizedBox(height: 22),
              _authorizedPanel(context),
            ],
            if (_message.isNotEmpty || widget.error.isNotEmpty) ...[
              const SizedBox(height: 18),
              StitchWarning(message: _message.isNotEmpty ? _message : widget.error),
            ],
            if (!_authenticated) ...[
              const SizedBox(height: 22),
              Text('当前诊断', style: StitchTextStyles.muted),
              const SizedBox(height: 10),
              _statusRow(context),
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
        StitchPill(label: Zh.authorization, value: _reasonText(widget.auth['reason']), color: _authColor),
        StitchPill(label: Zh.device, value: _deviceName),
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

  Widget _authorizedPanel(BuildContext context) {
    if (!_authorized) return _redeemForm(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _authMetaGrid(context),
        const SizedBox(height: 18),
        OutlinedButton(
          onPressed: _loading ? null : () => _run(() => widget.api.authStatus(force: true)),
          child: const Text(Zh.refreshAuth),
        ),
        const SizedBox(height: 10),
        TextButton(
          onPressed: _loading ? null : () => _run(() => widget.api.logout()),
          child: const Text(Zh.logout),
        ),
      ],
    );
  }

  Widget _redeemForm(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _authMetaGrid(context),
        const SizedBox(height: 18),
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
        Text(Zh.unbindPenaltyHint, style: StitchTextStyles.muted),
        const SizedBox(height: 8),
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

  Widget _authMetaGrid(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final columns = constraints.maxWidth > 620 ? 2 : 1;
        return GridView.count(
          crossAxisCount: columns,
          crossAxisSpacing: 10,
          mainAxisSpacing: 10,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          childAspectRatio: columns == 2 ? 3.6 : 5,
          children: [
            _authInfoTile(label: Zh.accountEmail, value: _accountEmail, accent: StitchColors.accentDeep),
            _authInfoTile(label: Zh.device, value: _deviceName, accent: _authColor),
            _authInfoTile(label: Zh.expiresAt, value: _formatAuthTime(_license['expires_at'], Zh.notOpened)),
            _authInfoTile(
              label: Zh.lastCheckedAt,
              value: _formatAuthTime(widget.auth['last_checked_at'], Zh.neverChecked),
            ),
          ],
        );
      },
    );
  }

  Widget _authInfoTile({
    required String label,
    required String value,
    Color accent = StitchColors.accentDeep,
  }) {
    return StitchCard(
      padding: const EdgeInsets.all(14),
      shadows: const [],
      backgroundColor: StitchColors.cardGlow,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Text(label, style: StitchTextStyles.muted, overflow: TextOverflow.ellipsis),
          const SizedBox(height: 4),
          Text(
            value,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(fontSize: 15, fontWeight: FontWeight.w800, color: accent),
          ),
        ],
      ),
    );
  }

  Widget _noticePanel(BuildContext context) {
    final notice = _firstEnabledNotice();
    if (notice == null) {
      return StitchCard(
        padding: const EdgeInsets.all(14),
        shadows: const [],
        backgroundColor: StitchColors.cardGlow,
        child: Text(Zh.noClientNotice, style: StitchTextStyles.muted),
      );
    }
    final tone = notice.severity == 'warning' ? StitchColors.warning : StitchColors.accentDeep;
    return StitchCard(
      padding: const EdgeInsets.all(16),
      shadows: const [],
      backgroundColor: notice.severity == 'warning' ? StitchColors.warningSoft : StitchColors.accentSoft,
      borderColor: tone.withValues(alpha: 0.26),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(notice.eyebrow, style: StitchTextStyles.eyebrow.copyWith(color: tone)),
          const SizedBox(height: 6),
          Text(notice.title, style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
          if (notice.message.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(notice.message, style: StitchTextStyles.muted),
          ],
          if (notice.version.isNotEmpty) ...[
            const SizedBox(height: 8),
            StitchPill(label: Zh.versionNotice, value: notice.version, color: tone),
          ],
        ],
      ),
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

  Color get _authColor {
    if (_authorized) return StitchColors.accentDeep;
    final reason = widget.auth['reason']?.toString() ?? _license['reason']?.toString() ?? '';
    if (reason == 'expired' || reason == 'revoked' || reason == 'disabled' || reason == 'device_mismatch') {
      return StitchColors.warning;
    }
    return StitchColors.accentDeep;
  }

  Map<String, dynamic> get _account => _mapValue(widget.auth['account']);
  Map<String, dynamic> get _license => _mapValue(widget.auth['license']);
  Map<String, dynamic> get _device {
    final device = _mapValue(widget.auth['device']);
    if (device.isNotEmpty) return device;
    return _mapValue(_account['device']);
  }

  String get _accountEmail {
    final value = _account['email']?.toString() ?? '';
    return value.isEmpty ? Zh.signedIn : value;
  }

  String get _deviceName {
    final value = _device['name']?.toString() ?? _device['hostname']?.toString() ?? _device['fingerprint']?.toString() ?? '';
    return value.isEmpty ? Zh.deviceUnknown : value;
  }

  String get _authSummaryText {
    if (_authorized) {
      final remainingSeconds = num.tryParse('${_license['remaining_seconds'] ?? ''}') ?? 0;
      final remainingDays = remainingSeconds <= 0 ? 0 : (remainingSeconds / 86400).ceil();
      return '${Zh.authValidFull} · ${Zh.remainingDays} $remainingDays';
    }
    return _reasonText(widget.auth['reason'] ?? _license['reason']);
  }

  Map<String, dynamic> _mapValue(Object? value) {
    return value is Map<String, dynamic> ? value : <String, dynamic>{};
  }

  String _formatAuthTime(Object? value, String fallback) {
    final seconds = int.tryParse(value?.toString() ?? '') ?? 0;
    if (seconds <= 0) return fallback;
    final time = DateTime.fromMillisecondsSinceEpoch(seconds * 1000);
    return '${time.year}-${_two(time.month)}-${_two(time.day)} ${_two(time.hour)}:${_two(time.minute)}';
  }

  String _two(int value) => value.toString().padLeft(2, '0');

  _ClientNotice? _firstEnabledNotice() {
    for (final notice in _notices) {
      if (notice.enabled) return notice;
    }
    return null;
  }
}

class _ClientNotice {
  const _ClientNotice({
    required this.kind,
    required this.title,
    required this.message,
    this.version = '',
    this.severity = 'info',
    this.enabled = true,
  });

  final String kind;
  final String title;
  final String message;
  final String version;
  final String severity;
  final bool enabled;

  String get eyebrow => switch (kind) {
        'version_update' || 'version' => Zh.versionNotice,
        'maintenance' => Zh.maintenanceNotice,
        _ => Zh.systemNotice,
      };

  static List<_ClientNotice> fromPayload(Map<String, dynamic> payload) {
    final notices = <_ClientNotice>[];
    for (final key in const ['maintenance', 'version_update']) {
      final notice = _fromMap(payload[key], key);
      if (notice != null) notices.add(notice);
    }
    final remote = payload['remote_notices'];
    if (remote is List) {
      for (final item in remote) {
        final notice = _fromMap(item, 'notice');
        if (notice != null) notices.add(notice);
      }
    }
    notices.sort((left, right) => _priority(right).compareTo(_priority(left)));
    return notices;
  }

  static int _priority(_ClientNotice notice) {
    if (!notice.enabled) return 0;
    if (notice.severity == 'warning') return 3;
    if (notice.kind == 'maintenance') return 2;
    return 1;
  }

  static _ClientNotice? _fromMap(Object? raw, String fallbackKind) {
    if (raw is! Map) return null;
    final enabled = raw['enabled'] == true;
    if (!enabled) return null;
    final title = raw['title']?.toString().trim() ?? '';
    final message = (raw['message'] ?? raw['body'] ?? '').toString().trim();
    if (title.isEmpty && message.isEmpty) return null;
    return _ClientNotice(
      kind: raw['kind']?.toString() ?? fallbackKind,
      title: title.isEmpty ? Zh.systemNotice : title,
      message: message,
      version: raw['version']?.toString() ?? '',
      severity: raw['severity']?.toString() ?? 'info',
      enabled: enabled,
    );
  }
}
