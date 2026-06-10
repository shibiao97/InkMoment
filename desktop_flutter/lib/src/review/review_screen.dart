import 'package:flutter/material.dart';

import '../api/inkmoment_api.dart';
import '../api/json_utils.dart';
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
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('AI 初筛复核', style: TextStyle(fontSize: 24, fontWeight: FontWeight.w700)),
        const SizedBox(height: 12),
        Text('待复核 ${_items.length} 张，分组预览 ${_groups.length} 组'),
        const SizedBox(height: 16),
        Expanded(
          child: Row(children: [
            Expanded(child: _rejectedGrid()),
            const SizedBox(width: 16),
            Expanded(child: _groupPreview()),
          ]),
        ),
        if (_error.isNotEmpty) Text(_error, style: const TextStyle(color: Color(0xFFFFB95F))),
        Align(alignment: Alignment.centerRight, child: FilledButton(onPressed: _confirm, child: const Text(Zh.confirmReview))),
      ]),
    );
  }

  Widget _rejectedGrid() {
    if (_items.isEmpty) return const Center(child: Text('暂无初筛剔除照片'));
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('AI 初筛复核', style: TextStyle(fontWeight: FontWeight.w700)),
      const SizedBox(height: 8),
      Expanded(
        child: GridView.builder(
          itemCount: _items.length,
          gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(crossAxisCount: 3, crossAxisSpacing: 8, mainAxisSpacing: 8),
          itemBuilder: (_, index) {
            final item = asStringMap(_items[index]) ?? emptyStringMap;
            final signals = asStringMap(item['signals']);
            final url = widget.api.imageUrl(item['path'] ?? item['original']);
            return _PhotoTile(
              imageUrl: url,
              title: item['name']?.toString() ?? '照片',
              subtitle: item['reason']?.toString() ?? '智能初筛',
              footer: '评分：${signals?['quality_score'] ?? Zh.noData}',
            );
          },
        ),
      ),
    ]);
  }

  Widget _groupPreview() {
    if (_groups.isEmpty) return const Center(child: Text('暂无分组预览'));
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('分组预览', style: TextStyle(fontWeight: FontWeight.w700)),
      const SizedBox(height: 8),
      Expanded(
        child: ListView.separated(
          itemCount: _groups.length,
          separatorBuilder: (_, __) => const SizedBox(height: 8),
          itemBuilder: (_, index) {
            final group = asStringMap(_groups[index]) ?? emptyStringMap;
            final signals = asStringMap(asStringMap(group['signals'])?['best']);
            return Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(color: const Color(0xFF1A211D), borderRadius: BorderRadius.circular(6)),
              child: Row(children: [
                SizedBox(
                  width: 92,
                  height: 68,
                  child: _NetworkPhoto(url: widget.api.imageUrl(group['best_path'], width: 480), fallback: '代表图'),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text('第 ${index + 1} 组 · ${group['size'] ?? 0} 张'),
                    Text('推荐：${signals?['ai_reason'] ?? Zh.noData}', maxLines: 1, overflow: TextOverflow.ellipsis),
                    Text('清晰度：${signals?['quality_score'] ?? Zh.noData}'),
                  ]),
                ),
              ]),
            );
          },
        ),
      ),
    ]);
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
    return Container(
      padding: const EdgeInsets.all(8),
      decoration: BoxDecoration(color: const Color(0xFF1A211D), borderRadius: BorderRadius.circular(6)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Expanded(child: _NetworkPhoto(url: imageUrl, fallback: title)),
        const SizedBox(height: 6),
        Text(title, overflow: TextOverflow.ellipsis),
        Text(subtitle, maxLines: 1, overflow: TextOverflow.ellipsis),
        Text(footer),
      ]),
    );
  }
}

class _NetworkPhoto extends StatelessWidget {
  const _NetworkPhoto({required this.url, required this.fallback});

  final String url;
  final String fallback;

  @override
  Widget build(BuildContext context) {
    if (url.isEmpty) return Center(child: Text(fallback, overflow: TextOverflow.ellipsis));
    return ClipRRect(
      borderRadius: BorderRadius.circular(4),
      child: Image.network(
        url,
        fit: BoxFit.cover,
        errorBuilder: (_, __, ___) => Center(child: Text(fallback, overflow: TextOverflow.ellipsis)),
      ),
    );
  }
}
