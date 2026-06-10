import 'package:flutter/material.dart';

import '../api/inkmoment_api.dart';
import '../l10n/strings.dart';

class ArenaScreen extends StatefulWidget {
  const ArenaScreen({
    super.key,
    required this.api,
    required this.onExport,
    required this.onAuthInvalid,
  });

  final InkMomentApi api;
  final VoidCallback onExport;
  final ValueChanged<Object> onAuthInvalid;

  @override
  State<ArenaScreen> createState() => _ArenaScreenState();
}

class _ArenaScreenState extends State<ArenaScreen> {
  Map<String, dynamic>? _group;
  String _error = '';

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final payload = await widget.api.getGroup();
      if (payload['done'] == true) {
        widget.onExport();
        return;
      }
      if (!mounted) return;
      setState(() => _group = payload['group'] as Map<String, dynamic>?);
    } catch (error) {
      _handleError(error);
    }
  }

  Future<void> _choose(String loser) async {
    try {
      final payload = await widget.api.choose(loser);
      if (payload['done'] == true) {
        widget.onExport();
      } else if (mounted) {
        setState(() => _group = payload['group'] as Map<String, dynamic>?);
      }
    } catch (error) {
      _handleError(error);
    }
  }

  Future<void> _reloadAfter(Future<Map<String, dynamic>> action) async {
    try {
      await action;
      await _load();
    } catch (error) {
      _handleError(error);
    }
  }

  void _handleError(Object error) {
    if (InkMomentApi.isAuthorizationFailure(error)) {
      widget.onAuthInvalid(error);
      return;
    }
    if (mounted) setState(() => _error = error.toString());
  }

  @override
  Widget build(BuildContext context) {
    final group = _group;
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('双图对比选片', style: TextStyle(fontSize: 24, fontWeight: FontWeight.w700)),
        const SizedBox(height: 12),
        Expanded(
          child: Row(children: [
            Expanded(child: _photoPane('左图', group?['left'], group?['left_signals'])),
            const SizedBox(width: 12),
            Expanded(child: _photoPane('右图', group?['right'], group?['right_signals'])),
          ]),
        ),
        if (_error.isNotEmpty) Text(_error, style: const TextStyle(color: Color(0xFFFFB95F))),
        Wrap(spacing: 10, children: [
          FilledButton(onPressed: () => _choose('right'), child: const Text(Zh.leftWins)),
          FilledButton(onPressed: () => _choose('left'), child: const Text(Zh.rightWins)),
          OutlinedButton(onPressed: () => _choose('neither'), child: const Text(Zh.keepBoth)),
          OutlinedButton(onPressed: () => _reloadAfter(widget.api.skipGroup()), child: const Text(Zh.skipGroup)),
          OutlinedButton(onPressed: () => _reloadAfter(widget.api.undo()), child: const Text(Zh.undo)),
        ]),
      ]),
    );
  }

  Widget _photoPane(String title, Object? path, Object? signals) {
    final signalMap = signals is Map ? signals : const {};
    final url = widget.api.imageUrl(path);
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(color: const Color(0xFF111815), border: Border.all(color: const Color(0xFF2F3632))),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(title, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
        const SizedBox(height: 8),
        Expanded(
          child: ClipRRect(
            borderRadius: BorderRadius.circular(6),
            child: url.isEmpty
                ? const Center(child: Text('无图'))
                : Image.network(
                    url,
                    width: double.infinity,
                    fit: BoxFit.contain,
                    errorBuilder: (_, __, ___) => Center(child: Text(path?.toString().split('/').last ?? '无图')),
                  ),
          ),
        ),
        Text('质量分：${signalMap['quality_score'] ?? Zh.noData}'),
        Text('AI 理由：${signalMap['ai_reason'] ?? Zh.noData}'),
      ]),
    );
  }
}
