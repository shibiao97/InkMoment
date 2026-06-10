import 'package:flutter/material.dart';

import '../api/inkmoment_api.dart';
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
  final _unbindReason = TextEditingController(text: '用户自助换机');
  bool _registerMode = false;
  bool _loading = false;
  String _message = '';

  bool get _authenticated => widget.auth['authenticated'] == true;

  Future<void> _run(Future<Map<String, dynamic>> Function() action) async {
    setState(() {
      _loading = true;
      _message = '';
    });
    try {
      final auth = await action();
      if (!mounted) return;
      widget.onAuthorized(auth);
      if (auth['authorized'] == true) {
        return;
      } else {
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
    return Scaffold(
      body: Center(
        child: SizedBox(
          width: 520,
          child: DecoratedBox(
            decoration: BoxDecoration(
              color: const Color(0xFF161D19),
              border: Border.all(color: const Color(0xFF2F3632)),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Padding(
              padding: const EdgeInsets.all(28),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('InkMoment 授权', style: TextStyle(color: Color(0xFF4EDEA3), fontSize: 13)),
                  const SizedBox(height: 8),
                  const Text(Zh.loginTitle, style: TextStyle(fontSize: 26, fontWeight: FontWeight.w700)),
                  const SizedBox(height: 18),
                  _statusRow(),
                  const SizedBox(height: 18),
                  if (!_authenticated) _accountForm() else _redeemForm(),
                  if (_message.isNotEmpty || widget.error.isNotEmpty) ...[
                    const SizedBox(height: 16),
                    Text(_message.isNotEmpty ? _message : widget.error, style: const TextStyle(color: Color(0xFFFFB95F))),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _statusRow() {
    final reason = _reasonText(widget.auth['reason']);
    return Row(
      children: [
        _pill('账号', _authenticated ? '已登录' : '未登录'),
        const SizedBox(width: 8),
        _pill('授权', reason),
        const SizedBox(width: 8),
        _pill('服务', widget.auth['configured'] == false ? '不可用' : '已配置'),
      ],
    );
  }

  Widget _accountForm() {
    return Column(
      children: [
        Row(
          children: [
            ChoiceChip(label: const Text(Zh.login), selected: !_registerMode, onSelected: (_) => setState(() => _registerMode = false)),
            const SizedBox(width: 8),
            ChoiceChip(label: const Text(Zh.register), selected: _registerMode, onSelected: (_) => setState(() => _registerMode = true)),
          ],
        ),
        const SizedBox(height: 12),
        _field(_email, Zh.email),
        _field(_password, Zh.password, obscure: true),
        if (_registerMode) _field(_name, Zh.displayName),
        const SizedBox(height: 12),
        SizedBox(
          width: double.infinity,
          child: FilledButton(
            onPressed: _loading
                ? null
                : () => _run(() => _registerMode
                    ? widget.api.register(_email.text.trim(), _password.text, _name.text.trim())
                    : widget.api.login(_email.text.trim(), _password.text)),
            child: Text(_loading ? '处理中' : (_registerMode ? '注册并绑定本机' : Zh.login)),
          ),
        ),
      ],
    );
  }

  Widget _redeemForm() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _field(_cdk, Zh.cdk),
        FilledButton(onPressed: _loading ? null : () => _run(() => widget.api.redeem(_cdk.text.trim())), child: const Text(Zh.redeem)),
        const SizedBox(height: 8),
        OutlinedButton(onPressed: _loading ? null : () => _run(() => widget.api.authStatus(force: true)), child: const Text(Zh.refreshAuth)),
        _field(_unbindReason, '解绑原因'),
        OutlinedButton(onPressed: _loading ? null : () => _run(() => widget.api.unbindDevice(_unbindReason.text.trim())), child: const Text('解除设备绑定')),
        OutlinedButton(onPressed: _loading ? null : () => _run(() => widget.api.logout()), child: const Text(Zh.logout)),
      ],
    );
  }

  Widget _field(TextEditingController controller, String label, {bool obscure = false}) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: TextField(
        controller: controller,
        obscureText: obscure,
        decoration: InputDecoration(labelText: label, border: const OutlineInputBorder()),
      ),
    );
  }

  Widget _pill(String label, String value) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(border: Border.all(color: const Color(0xFF2F3632)), borderRadius: BorderRadius.circular(6)),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(label, style: const TextStyle(fontSize: 11, color: Color(0xFFBBCABF))),
          Text(value, overflow: TextOverflow.ellipsis),
        ]),
      ),
    );
  }

  String _reasonText(Object? reason) => switch (reason?.toString()) {
        'active' => '已开通',
        'unauthenticated' => '未登录',
        'not_activated' => '未开通',
        'expired' => '已过期',
        'revoked' => '已撤销',
        'device_mismatch' => '设备不匹配',
        'auth_server_not_configured' => '授权服务未配置',
        'auth_not_configured' => '授权服务未配置',
        'auth_server_unavailable' => '授权服务不可用',
        'auth_check_failed' => '授权检查失败',
        null || '' => '未登录',
        _ => '授权尚未完成',
      };
}
