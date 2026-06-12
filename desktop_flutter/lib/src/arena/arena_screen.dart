import 'package:flutter/material.dart';

import '../api/inkmoment_api.dart';
import '../api/json_utils.dart';
import '../design/stitch_components.dart';
import '../design/stitch_layout.dart';
import '../design/stitch_tokens.dart';
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
      if (!mounted) return;
      if (payload['done'] == true) {
        widget.onExport();
        return;
      }
      setState(() => _group = asStringMap(payload['group']));
    } catch (error) {
      _handleError(error);
    }
  }

  Future<void> _choose(String loser) async {
    try {
      final payload = await widget.api.choose(loser);
      if (!mounted) return;
      if (payload['done'] == true) {
        widget.onExport();
      } else {
        setState(() => _group = asStringMap(payload['group']));
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
    if (!mounted) return;
    if (InkMomentApi.isAuthorizationFailure(error)) {
      widget.onAuthInvalid(error);
      return;
    }
    setState(() => _error = error.toString());
  }

  @override
  Widget build(BuildContext context) {
    final group = _group;
    final compact = StitchLayout.compact(context);
    return SingleChildScrollView(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 1320),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                _hero(context),
                const SizedBox(height: 20),
                compact
                    ? _compactPhotos(context, group)
                    : Row(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Expanded(
                            child: _photoPane(
                              context,
                              Zh.leftPhoto,
                              group?['left'],
                              group?['left_signals'],
                            ),
                          ),
                          const SizedBox(width: 14),
                          _vsBadge(context),
                          const SizedBox(width: 14),
                          Expanded(
                            child: _photoPane(
                              context,
                              Zh.rightPhoto,
                              group?['right'],
                              group?['right_signals'],
                            ),
                          ),
                        ],
                      ),
                const SizedBox(height: 18),
                if (_error.isNotEmpty) ...[
                  StitchWarning(message: _error),
                  const SizedBox(height: 18),
                ],
                _actionBar(context),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _hero(BuildContext context) {
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
            child: const Icon(Icons.compare_outlined, color: StitchColors.accentDeep, size: 30),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  Zh.arenaTitle,
                  style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                        color: StitchColors.textPrimary,
                        fontWeight: FontWeight.w800,
                      ),
                ),
                const SizedBox(height: 6),
                Text(
                  Zh.operationHintText,
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                        color: StitchColors.textMuted,
                        height: 1.5,
                      ),
                ),
                const SizedBox(height: 14),
                const Wrap(
                  spacing: 10,
                  runSpacing: 10,
                  children: [
                    StitchPill(label: Zh.select, value: Zh.arenaTitle),
                    StitchPill(label: Zh.status, value: Zh.ready),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _compactPhotos(BuildContext context, Map<String, dynamic>? group) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _photoPane(context, Zh.leftPhoto, group?['left'], group?['left_signals']),
        const SizedBox(height: 14),
        _vsBadge(context),
        const SizedBox(height: 14),
        _photoPane(context, Zh.rightPhoto, group?['right'], group?['right_signals']),
      ],
    );
  }

  Widget _vsBadge(BuildContext context) {
    return Center(
      child: Container(
        width: 58,
        height: 58,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: StitchColors.winner.withOpacity(0.18),
          borderRadius: BorderRadius.circular(999),
          border: Border.all(color: StitchColors.winner.withOpacity(0.46)),
        ),
        child: Text(
          'VS',
          style: Theme.of(context).textTheme.titleMedium?.copyWith(
                color: StitchColors.textPrimary,
                fontWeight: FontWeight.w900,
              ),
        ),
      ),
    );
  }

  Widget _photoPane(BuildContext context, String title, Object? path, Object? signals) {
    final signalMap = asStringMap(signals) ?? emptyStringMap;
    final url = widget.api.imageUrl(path);
    final fallback = path?.toString().split('/').last ?? Zh.noImage;
    return StitchCard(
      padding: const EdgeInsets.all(16),
      backgroundColor: StitchColors.card,
      borderColor: StitchColors.borderSoft,
      radius: StitchRadius.xl,
      shadows: const [BoxShadow(color: Color(0x0E243527), blurRadius: 20, offset: Offset(0, 12))],
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(
                title,
                style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      color: StitchColors.textPrimary,
                      fontWeight: FontWeight.w800,
                    ),
              ),
              const Spacer(),
              StitchPill(label: Zh.quality, value: '${signalMap['quality_score'] ?? Zh.noData}'),
            ],
          ),
          const SizedBox(height: 12),
          AspectRatio(
            aspectRatio: 4 / 3,
            child: StitchPhotoFrame(
              padding: const EdgeInsets.all(6),
              child: url.isEmpty
                  ? Center(child: Text(fallback, overflow: TextOverflow.ellipsis))
                  : Image.network(
                      url,
                      width: double.infinity,
                      height: double.infinity,
                      fit: BoxFit.contain,
                      errorBuilder: (_, __, ___) => Center(
                        child: Text(fallback, overflow: TextOverflow.ellipsis),
                      ),
                    ),
            ),
          ),
          const SizedBox(height: 12),
          Text(
            Zh.qualityScoreLabel(signalMap['quality_score']),
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: StitchColors.accentDeep,
                  fontWeight: FontWeight.w700,
                ),
          ),
          const SizedBox(height: 4),
          Text(
            Zh.aiReasonLabel(signalMap['ai_reason']),
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: StitchColors.textMuted,
                  height: 1.45,
                ),
          ),
        ],
      ),
    );
  }

  Widget _actionBar(BuildContext context) {
    return StitchCard(
      padding: const EdgeInsets.all(16),
      backgroundColor: StitchColors.cardGlow,
      borderColor: StitchColors.borderSoft,
      radius: StitchRadius.xl,
      shadows: const [],
      child: Wrap(
        spacing: 10,
        runSpacing: 10,
        alignment: WrapAlignment.end,
        children: [
          FilledButton(
            onPressed: () => _choose('right'),
            child: const Text(Zh.leftWins),
          ),
          FilledButton(
            onPressed: () => _choose('left'),
            child: const Text(Zh.rightWins),
          ),
          OutlinedButton(
            onPressed: () => _choose('neither'),
            child: const Text(Zh.keepBoth),
          ),
          OutlinedButton(
            onPressed: () => _reloadAfter(widget.api.skipGroup()),
            child: const Text(Zh.skipGroup),
          ),
          OutlinedButton(
            onPressed: () => _reloadAfter(widget.api.undo()),
            child: const Text(Zh.undo),
          ),
        ],
      ),
    );
  }
}
