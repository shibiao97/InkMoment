import 'package:flutter/material.dart';

import '../api/inkmoment_api.dart';
import '../api/json_utils.dart';
import '../design/stitch_components.dart';
import '../design/stitch_layout.dart';
import '../design/stitch_tokens.dart';
import '../l10n/strings.dart';

class ReviewScreen extends StatefulWidget {
  const ReviewScreen({
    super.key,
    required this.api,
    required this.onSelect,
    required this.onAuthInvalid,
  });

  final InkMomentApi api;
  final VoidCallback onSelect;
  final ValueChanged<Object> onAuthInvalid;

  @override
  State<ReviewScreen> createState() => _ReviewScreenState();
}

class _ReviewScreenState extends State<ReviewScreen> {
  List<dynamic> _items = const [];
  List<dynamic> _groups = const [];
  String _error = '';

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final rejected = await widget.api.getAutoRejected();
      final preview = await widget.api.getPreviewGroups();
      if (!mounted) return;
      setState(() {
        _items = asList(rejected['items']);
        _groups = asList(preview['groups']);
      });
    } catch (error) {
      if (!mounted) return;
      if (InkMomentApi.isAuthorizationFailure(error)) {
        widget.onAuthInvalid(error);
        return;
      }
      setState(() => _error = error.toString());
    }
  }

  Future<void> _confirm() async {
    try {
      await widget.api.confirmPrescreen();
      if (!mounted) return;
      widget.onSelect();
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
    final compact = StitchLayout.compact(context);
    return SingleChildScrollView(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 1280),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                _hero(context),
                const SizedBox(height: 20),
                compact ? _compactLayout(context) : _desktopLayout(context),
                const SizedBox(height: 18),
                if (_error.isNotEmpty) StitchWarning(message: _error),
                if (_error.isNotEmpty) const SizedBox(height: 18),
                Align(
                  alignment: Alignment.centerRight,
                  child: FilledButton(
                    onPressed: _confirm,
                    child: const Text(Zh.confirmReview),
                  ),
                ),
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
            child: const Icon(Icons.fact_check_outlined, color: StitchColors.accentDeep, size: 30),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  Zh.reviewTitle,
                  style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                        color: StitchColors.textPrimary,
                        fontWeight: FontWeight.w800,
                      ),
                ),
                const SizedBox(height: 6),
                Text(
                  Zh.reviewSummary(_items.length, _groups.length),
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
                    StitchPill(label: Zh.prescreenRejectedSection, value: '${_items.length}'),
                    StitchPill(label: Zh.groupPreview, value: '${_groups.length}'),
                    const StitchPill(label: Zh.status, value: Zh.ready),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _desktopLayout(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(child: _rejectedGrid(context)),
        const SizedBox(width: 16),
        Expanded(child: _groupPreview(context)),
      ],
    );
  }

  Widget _compactLayout(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _rejectedGrid(context),
        const SizedBox(height: 16),
        _groupPreview(context),
      ],
    );
  }

  Widget _rejectedGrid(BuildContext context) {
    return StitchCard(
      padding: const EdgeInsets.all(22),
      backgroundColor: StitchColors.card,
      borderColor: StitchColors.borderSoft,
      radius: StitchRadius.xl,
      shadows: const [BoxShadow(color: Color(0x0E243527), blurRadius: 20, offset: Offset(0, 12))],
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          StitchSectionHeader(
            eyebrow: Zh.review,
            title: Zh.prescreenRejectedSection,
            description: Zh.noPrescreenRejectedPhotos,
          ),
          const SizedBox(height: 16),
          if (_items.isEmpty)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 42),
              child: StitchEmptyState(message: Zh.noPrescreenRejectedPhotos),
            )
          else
            GridView.builder(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              itemCount: _items.length,
              gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: 3,
                crossAxisSpacing: 10,
                mainAxisSpacing: 10,
                childAspectRatio: 0.82,
              ),
              itemBuilder: (_, index) {
                final item = asStringMap(_items[index]) ?? emptyStringMap;
                final signals = asStringMap(item['signals']);
                final url = widget.api.imageUrl(item['path'] ?? item['original']);
                return _PhotoTile(
                  imageUrl: url,
                  title: item['name']?.toString() ?? Zh.photoFallback,
                  subtitle: item['reason']?.toString() ?? Zh.smartPrescreen,
                  footer: Zh.scoreLabel(signals?['quality_score']),
                );
              },
            ),
        ],
      ),
    );
  }

  Widget _groupPreview(BuildContext context) {
    return StitchCard(
      padding: const EdgeInsets.all(22),
      backgroundColor: StitchColors.card,
      borderColor: StitchColors.borderSoft,
      radius: StitchRadius.xl,
      shadows: const [BoxShadow(color: Color(0x0E243527), blurRadius: 20, offset: Offset(0, 12))],
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          StitchSectionHeader(
            eyebrow: Zh.smartPrescreen,
            title: Zh.groupPreview,
            description: Zh.noGroupPreview,
          ),
          const SizedBox(height: 16),
          if (_groups.isEmpty)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 42),
              child: StitchEmptyState(message: Zh.noGroupPreview),
            )
          else
            ListView.separated(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              itemCount: _groups.length,
              separatorBuilder: (_, __) => const SizedBox(height: 10),
              itemBuilder: (_, index) {
                final group = asStringMap(_groups[index]) ?? emptyStringMap;
                final signals = asStringMap(asStringMap(group['signals'])?['best']);
                return StitchCard(
                  padding: const EdgeInsets.all(10),
                  backgroundColor: StitchColors.cardGlow,
                  borderColor: StitchColors.borderSoft,
                  radius: StitchRadius.lg,
                  shadows: const [],
                  child: Row(
                    children: [
                      SizedBox(
                        width: 98,
                        height: 72,
                        child: _NetworkPhoto(
                          url: widget.api.imageUrl(group['best_path'], width: 480),
                          fallback: Zh.representativePhoto,
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              Zh.groupSummary(index + 1, group['size'] ?? 0),
                              style: Theme.of(context).textTheme.titleSmall?.copyWith(
                                    color: StitchColors.textPrimary,
                                    fontWeight: FontWeight.w800,
                                  ),
                            ),
                            const SizedBox(height: 4),
                            Text(
                              Zh.recommendationLabel(signals?['ai_reason']),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                                    color: StitchColors.textMuted,
                                  ),
                            ),
                            Text(
                              Zh.clarityLabel(signals?['quality_score']),
                              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                                    color: StitchColors.accentDeep,
                                    fontWeight: FontWeight.w700,
                                  ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                );
              },
            ),
        ],
      ),
    );
  }
}

class _PhotoTile extends StatelessWidget {
  const _PhotoTile({
    required this.imageUrl,
    required this.title,
    required this.subtitle,
    required this.footer,
  });

  final String imageUrl;
  final String title;
  final String subtitle;
  final String footer;

  @override
  Widget build(BuildContext context) {
    return StitchCard(
      padding: const EdgeInsets.all(8),
      backgroundColor: StitchColors.cardGlow,
      borderColor: StitchColors.borderSoft,
      radius: StitchRadius.lg,
      shadows: const [],
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(child: _NetworkPhoto(url: imageUrl, fallback: title)),
          const SizedBox(height: 8),
          Text(
            title,
            overflow: TextOverflow.ellipsis,
            style: Theme.of(context).textTheme.titleSmall?.copyWith(
                  color: StitchColors.textPrimary,
                  fontWeight: FontWeight.w800,
                ),
          ),
          Text(
            subtitle,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: Theme.of(context).textTheme.bodySmall?.copyWith(color: StitchColors.textMuted),
          ),
          Text(
            footer,
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: StitchColors.accentDeep,
                  fontWeight: FontWeight.w700,
                ),
          ),
        ],
      ),
    );
  }
}

class _NetworkPhoto extends StatelessWidget {
  const _NetworkPhoto({required this.url, required this.fallback});

  final String url;
  final String fallback;

  @override
  Widget build(BuildContext context) {
    final child = url.isEmpty
        ? Center(child: Text(fallback, overflow: TextOverflow.ellipsis))
        : Image.network(
            url,
            width: double.infinity,
            height: double.infinity,
            fit: BoxFit.cover,
            errorBuilder: (_, __, ___) => Center(
              child: Text(fallback, overflow: TextOverflow.ellipsis),
            ),
          );
    return ClipRRect(
      borderRadius: BorderRadius.circular(StitchRadius.md),
      child: ColoredBox(color: StitchColors.warmBackground, child: child),
    );
  }
}
