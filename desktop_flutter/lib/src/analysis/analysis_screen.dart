import 'dart:async';

import 'package:flutter/material.dart';

import '../api/inkmoment_api.dart';
import '../api/json_utils.dart';
import '../l10n/strings.dart';

class AnalysisScreen extends StatefulWidget {
  const AnalysisScreen({
    super.key,
    required this.api,
    required this.onReview,
    required this.onAuthInvalid,
  });

  final InkMomentApi api;
  final VoidCallback onReview;
  final ValueChanged<Object> onAuthInvalid;

  @override
  State<AnalysisScreen> createState() => _AnalysisScreenState();
}

class _AnalysisScreenState extends State<AnalysisScreen> {
  Timer? _timer;
  Map<String, dynamic> _job = emptyStringMap;
  String _error = '';

  @override
  void initState() {
    super.initState();
    _poll();
    _timer = Timer.periodic(const Duration(seconds: 1), (_) => _poll());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _poll() async {
    try {
      final job = await widget.api.getJob();
      if (!mounted) return;
      setState(() => _job = job);
      if (job['status'] == 'done') {
        _timer?.cancel();
        widget.onReview();
      }
    } catch (error) {
      if (!mounted) return;
      if (InkMomentApi.isAuthorizationFailure(error)) {
        widget.onAuthInvalid(error);
        return;
      }
      setState(() => _error = error.toString());
    }
  }

  Future<void> _cancel() async {
    try {
      await widget.api.cancelJob();
    } catch (error) {
      if (!mounted) return;
      if (InkMomentApi.isAuthorizationFailure(error)) {
        widget.onAuthInvalid(error);
        return;
      }
      setState(() => _error = error.toString());
    }
  }

  @override
  Widget build(BuildContext context) {
    final done = (_job['done'] as num?)?.toDouble() ?? 0;
    final total = (_job['total'] as num?)?.toDouble() ?? 0;
    final progress = total <= 0 ? 0.0 : (done / total).clamp(0.0, 1.0);
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('正在分析照片', style: TextStyle(fontSize: 24, fontWeight: FontWeight.w700)),
        const SizedBox(height: 18),
        LinearProgressIndicator(value: progress),
        const SizedBox(height: 12),
        Text('${_job['label'] ?? '准备中'} · ${done.toInt()} / ${total.toInt()}'),
        const SizedBox(height: 20),
        Expanded(
          child: GridView.builder(
            itemCount: 24,
            gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(crossAxisCount: 6, crossAxisSpacing: 8, mainAxisSpacing: 8),
            itemBuilder: (_, index) => Container(color: index / 24 < progress ? const Color(0xFF10B981) : const Color(0xFF242C27)),
          ),
        ),
        if (_error.isNotEmpty) Text(_error, style: const TextStyle(color: Color(0xFFFFB95F))),
        OutlinedButton(onPressed: _cancel, child: const Text(Zh.cancelAnalyze)),
      ]),
    );
  }
}
