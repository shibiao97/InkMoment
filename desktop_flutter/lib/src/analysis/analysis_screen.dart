import 'dart:async';

import 'package:flutter/material.dart';

import '../api/inkmoment_api.dart';
import '../api/json_utils.dart';
import '../design/stitch_components.dart';
import '../design/stitch_layout.dart';
import '../design/stitch_tokens.dart';
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
    final compact = StitchLayout.compact(context);
    return SingleChildScrollView(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 1240),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                _hero(context, progress, done.toInt(), total.toInt()),
                const SizedBox(height: 20),
                compact ? _compactLayout(context, progress) : _desktopLayout(context, progress),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _hero(BuildContext context, double progress, int done, int total) {
    return StitchCard(
      padding: const EdgeInsets.all(24),
      backgroundColor: StitchColors.cardGlow,
      borderColor: StitchColors.borderSoft,
      radius: StitchRadius.xl,
      shadows: const [BoxShadow(color: Color(0x0E243527), blurRadius: 20, offset: Offset(0, 12))],
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 60,
            height: 60,
            decoration: BoxDecoration(
              color: StitchColors.accentSoft,
              borderRadius: BorderRadius.circular(StitchRadius.lg),
              border: Border.all(color: StitchColors.borderSoft),
            ),
            child: const Icon(Icons.auto_awesome_outlined, color: StitchColors.accentDeep, size: 30),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  Zh.analyzingPhotos,
                  style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                        color: StitchColors.textPrimary,
                        fontWeight: FontWeight.w800,
                      ),
                ),
                const SizedBox(height: 6),
                Text(
                  Zh.folderScanHint,
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                        color: StitchColors.textMuted,
                        height: 1.5,
                      ),
                ),
                const SizedBox(height: 14),
                Wrap(
                  spacing: 10,
                  runSpacing: 10,
                  children: [
                    StitchPill(label: Zh.status, value: _job['label']?.toString() ?? Zh.preparing),
                    StitchPill(label: Zh.noData, value: '$done / $total'),
                    StitchPill(
                      label: Zh.currentFlow,
                      value: _job['status']?.toString() ?? Zh.preparing,
                      color: progress >= 1 ? StitchColors.accentDeep : StitchColors.winner,
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _desktopLayout(BuildContext context, double progress) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          flex: 7,
          child: _progressCard(context, progress),
        ),
        const SizedBox(width: 16),
        Expanded(
          flex: 5,
          child: Column(
            children: [
              _metricsCard(context, progress),
              const SizedBox(height: 16),
              _actionsCard(context),
            ],
          ),
        ),
      ],
    );
  }

  Widget _compactLayout(BuildContext context, double progress) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _progressCard(context, progress),
        const SizedBox(height: 16),
        _metricsCard(context, progress),
        const SizedBox(height: 16),
        _actionsCard(context),
      ],
    );
  }

  Widget _progressCard(BuildContext context, double progress) {
    final done = (_job['done'] as num?)?.toDouble() ?? 0;
    final total = (_job['total'] as num?)?.toDouble() ?? 0;
    return StitchCard(
      padding: const EdgeInsets.all(22),
      backgroundColor: StitchColors.card,
      borderColor: StitchColors.borderSoft,
      radius: StitchRadius.xl,
      shadows: const [BoxShadow(color: Color(0x0E243527), blurRadius: 20, offset: Offset(0, 12))],
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            Zh.analyzingPhotos,
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  color: StitchColors.textPrimary,
                  fontWeight: FontWeight.w800,
                ),
          ),
          const SizedBox(height: 12),
          StitchProgressBar(value: progress),
          const SizedBox(height: 12),
          Text(
            '${_job['label'] ?? Zh.preparing} · ${done.toInt()} / ${total.toInt()}',
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: StitchColors.textSecondary,
                  fontWeight: FontWeight.w700,
                ),
          ),
          const SizedBox(height: 18),
          GridView.builder(
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            itemCount: 24,
            gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
              crossAxisCount: 6,
              crossAxisSpacing: 8,
              mainAxisSpacing: 8,
            ),
            itemBuilder: (_, index) {
              final active = index / 24 < progress;
              return AnimatedContainer(
                duration: const Duration(milliseconds: 180),
                decoration: BoxDecoration(
                  color: active ? StitchColors.accentSoft : StitchColors.cardGlow,
                  borderRadius: BorderRadius.circular(StitchRadius.sm),
                  border: Border.all(color: active ? StitchColors.accent : StitchColors.borderFaint),
                ),
                child: Icon(
                  Icons.photo_outlined,
                  size: 18,
                  color: active ? StitchColors.accentDeep : StitchColors.textFaint,
                ),
              );
            },
          ),
          if (_error.isNotEmpty) ...[
            const SizedBox(height: 16),
            StitchWarning(message: _error),
          ],
        ],
      ),
    );
  }

  Widget _metricsCard(BuildContext context, double progress) {
    final done = (_job['done'] as num?)?.toInt() ?? 0;
    final total = (_job['total'] as num?)?.toInt() ?? 0;
    return StitchCard(
      padding: const EdgeInsets.all(22),
      backgroundColor: StitchColors.cardGlow,
      borderColor: StitchColors.borderSoft,
      radius: StitchRadius.xl,
      shadows: const [BoxShadow(color: Color(0x0E243527), blurRadius: 20, offset: Offset(0, 12))],
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            Zh.currentFlow,
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  color: StitchColors.textPrimary,
                  fontWeight: FontWeight.w800,
                ),
          ),
          const SizedBox(height: 14),
          Row(
            children: [
              Expanded(
                child: StitchMetricCard(
                  label: Zh.status,
                  value: _job['label']?.toString() ?? Zh.preparing,
                  accent: StitchColors.accentDeep,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: StitchMetricCard(
                  label: Zh.completed,
                  value: '$done',
                  accent: StitchColors.winner,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: StitchMetricCard(
                  label: Zh.total,
                  value: '$total',
                  accent: StitchColors.accent,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: StitchMetricCard(
                  label: Zh.progress,
                  value: '${(progress * 100).toStringAsFixed(0)}%',
                  accent: StitchColors.warning,
                ),
              ),
            ],
          ),
          if (_error.isNotEmpty) ...[
            const SizedBox(height: 16),
            StitchWarning(message: _error),
          ],
        ],
      ),
    );
  }

  Widget _actionsCard(BuildContext context) {
    return StitchCard(
      padding: const EdgeInsets.all(22),
      backgroundColor: StitchColors.card,
      borderColor: StitchColors.borderSoft,
      radius: StitchRadius.xl,
      shadows: const [BoxShadow(color: Color(0x0E243527), blurRadius: 20, offset: Offset(0, 12))],
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            Zh.operationHint,
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  color: StitchColors.textPrimary,
                  fontWeight: FontWeight.w800,
                ),
          ),
          const SizedBox(height: 8),
          Text(
            Zh.operationHintText,
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: StitchColors.textMuted,
                  height: 1.5,
                ),
          ),
          const SizedBox(height: 18),
          FilledButton(
            onPressed: _cancel,
            child: Text(Zh.cancelAnalyze),
          ),
        ],
      ),
    );
  }
}
