import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';

import '../api/inkmoment_api.dart';
import '../design/stitch_components.dart';
import '../design/stitch_tokens.dart';
import '../l10n/strings.dart';

// engine value → (label, 依赖说明, 是否需要云端配置)
const _kModes = [
  ('fast',   '快速选片',   '依赖：OpenCV · imagehash（内置，无需下载）',     false),
  ('expert', '质感优选',   '依赖：PyTorch · DINO 模型（首次运行需下载）',    false),
  ('cloud',  '云端精评',   '依赖：ARK API Key · 需配置访问地址',             true),
];

class TaskSetupScreen extends StatefulWidget {
  const TaskSetupScreen({
    super.key,
    required this.api,
    required this.onStarted,
    required this.onAuthInvalid,
  });

  final InkMomentApi api;
  final ValueChanged<Map<String, dynamic>> onStarted;
  final ValueChanged<Object> onAuthInvalid;

  @override
  State<TaskSetupScreen> createState() => _TaskSetupScreenState();
}

class _TaskSetupScreenState extends State<TaskSetupScreen> {
  String _engine = 'fast';
  String _folder = '';
  Map<String, dynamic>? _peek;
  String _error = '';
  bool _busy = false;

  // 云端模式配置
  final _cloudUrlCtrl  = TextEditingController();
  final _cloudKeyCtrl  = TextEditingController();

  @override
  void dispose() {
    _cloudUrlCtrl.dispose();
    _cloudKeyCtrl.dispose();
    super.dispose();
  }

  String get _engineLabel =>
      _kModes.firstWhere((m) => m.$1 == _engine, orElse: () => _kModes[0]).$2;

  Future<void> _pickFolder() async {
    final path = await getDirectoryPath(confirmButtonText: Zh.chooseFolder);
    if (path == null) return;
    if (!mounted) return;
    setState(() {
      _folder = path;
      _busy = true;
      _error = '';
    });
    try {
      final peek = await widget.api.peekFolder(path);
      if (!mounted) return;
      setState(() => _peek = peek);
    } catch (error) {
      if (!mounted) return;
      if (InkMomentApi.isAuthorizationFailure(error)) {
        widget.onAuthInvalid(error);
        return;
      }
      setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _start() async {
    // 云端模式必须填写配置
    if (_engine == 'cloud') {
      final url = _cloudUrlCtrl.text.trim();
      final key = _cloudKeyCtrl.text.trim();
      if (url.isEmpty || key.isEmpty) {
        setState(() => _error = '云端精评模式需要填写 API 地址和 API Key');
        return;
      }
    }
    setState(() { _busy = true; _error = ''; });
    try {
      final jobPayload = {
        'folder': _folder,
        'mode': 'copy',
        'engine': _engine == 'fast' ? 'fast' : 'expert',
        'prescreen_enabled': true,
        if (_engine == 'cloud') ...{
          'ark_base_url': _cloudUrlCtrl.text.trim(),
          'ark_api_key':  _cloudKeyCtrl.text.trim(),
        },
      };
      final payload = await widget.api.startJob(jobPayload);
      if (!mounted) return;
      widget.onStarted({...payload, 'folder': _folder, 'engine_label': _engineLabel, 'engine': _engine});
    } catch (error) {
      if (!mounted) return;
      if (InkMomentApi.isAuthorizationFailure(error)) {
        widget.onAuthInvalid(error);
        return;
      }
      setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _hero(context),
          const SizedBox(height: 28),
          _folderPanel(context),
          const SizedBox(height: 28),
          _modePanel(context),
          if (_error.isNotEmpty) ...[
            const SizedBox(height: 18),
            StitchWarning(message: _error),
          ],
        ],
      ),
    );
  }

  Widget _hero(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(Zh.taskHeroEyebrow, style: StitchTextStyles.eyebrow),
              const SizedBox(height: 14),
              const Text(Zh.taskHeroTitle, style: StitchTextStyles.pageTitle),
              const SizedBox(height: 14),
              Text(Zh.folderScanHint, style: StitchTextStyles.body.copyWith(fontSize: 17, height: 1.5)),
            ],
          ),
        ),
        const SizedBox(width: 24),
        Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(Zh.style, style: StitchTextStyles.muted.copyWith(fontSize: 16)),
            const SizedBox(width: 10),
            Container(
              width: 210,
              height: 38,
              padding: const EdgeInsets.symmetric(horizontal: 12),
              decoration: BoxDecoration(
                color: StitchColors.card,
                borderRadius: BorderRadius.circular(StitchRadius.sm),
                border: Border.all(color: StitchColors.borderSoft),
              ),
              child: DropdownButtonHideUnderline(
                child: DropdownButton<String>(
                  value: 'mint',
                  items: const [DropdownMenuItem(value: 'mint', child: Text(Zh.clearMint))],
                  onChanged: (_) {},
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }

  Widget _folderPanel(BuildContext context) {
    final count = _peek?['count'] ?? _peek?['total'];
    return StitchCard(
      padding: const EdgeInsets.all(28),
      backgroundColor: StitchColors.card,
      borderColor: StitchColors.borderSoft,
      radius: StitchRadius.md,
      shadows: const [],
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(Zh.importPhotos, style: StitchTextStyles.muted.copyWith(fontWeight: FontWeight.w800)),
                    const SizedBox(height: 10),
                    Text(Zh.chooseFolder, style: StitchTextStyles.sectionTitle.copyWith(fontSize: 24)),
                  ],
                ),
              ),
              Text(Zh.baseRuntimeBundle, style: StitchTextStyles.muted),
            ],
          ),
          const SizedBox(height: 30),
          Text(Zh.photoFolder, style: StitchTextStyles.muted.copyWith(fontWeight: FontWeight.w700)),
          const SizedBox(height: 14),
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: StitchColors.cardGlow,
              borderRadius: BorderRadius.circular(StitchRadius.sm),
              border: Border.all(color: StitchColors.accent),
            ),
            child: Row(
              children: [
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 12),
                    child: Text(
                      _folder.isEmpty ? Zh.pasteFolderPath : _folder,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        color: _folder.isEmpty ? StitchColors.textFaint : StitchColors.textPrimary,
                        fontSize: 17,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ),
                ),
                OutlinedButton(onPressed: _busy ? null : _pickFolder, child: const Text(Zh.chooseFolder)),
                const SizedBox(width: 10),
                FilledButton(onPressed: _folder.isEmpty || _busy ? null : _start, child: Text(_busy ? Zh.processing : Zh.start)),
              ],
            ),
          ),
          if (count != null) ...[
            const SizedBox(height: 14),
            Text(Zh.scannedPhotos(count), style: StitchTextStyles.muted),
          ],
        ],
      ),
    );
  }

  Widget _modePanel(BuildContext context) {
    return StitchCard(
      padding: const EdgeInsets.all(24),
      backgroundColor: StitchColors.card,
      borderColor: StitchColors.borderSoft,
      radius: StitchRadius.md,
      shadows: const [],
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(Zh.filterPlan, style: StitchTextStyles.muted.copyWith(fontWeight: FontWeight.w800)),
          const SizedBox(height: 6),
          Text('选择分析模式', style: StitchTextStyles.sectionTitle.copyWith(fontSize: 20)),
          const SizedBox(height: 20),
          LayoutBuilder(
            builder: (context, constraints) {
              final compact = constraints.maxWidth < 720;
              final cards = _kModes.map((m) => _modeCard(context, m.$1, m.$2, m.$3)).toList();
              if (compact) {
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [for (final c in cards) ...[c, const SizedBox(height: 10)]],
                );
              }
              return Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  for (var i = 0; i < cards.length; i++) ...[
                    Expanded(child: cards[i]),
                    if (i != cards.length - 1) const SizedBox(width: 14),
                  ],
                ],
              );
            },
          ),
          // 云端模式配置：选中时展开
          AnimatedSize(
            duration: const Duration(milliseconds: 200),
            child: _engine == 'cloud'
                ? Padding(
                    padding: const EdgeInsets.only(top: 20),
                    child: _cloudConfigFields(context),
                  )
                : const SizedBox.shrink(),
          ),
        ],
      ),
    );
  }

  // value, label, resourceHint — 由 _kModes 传入
  Widget _modeCard(BuildContext context, String value, String label, String resourceHint) {
    final selected = _engine == value;
    return GestureDetector(
      onTap: _busy ? null : () => setState(() => _engine = value),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 180),
        constraints: const BoxConstraints(minHeight: 130),
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: selected ? StitchColors.accentSoft : StitchColors.card,
          border: Border.all(
            color: selected ? StitchColors.accentDeep : StitchColors.borderSoft,
            width: selected ? 2 : 1,
          ),
          borderRadius: BorderRadius.circular(StitchRadius.sm),
          boxShadow: selected ? StitchShadow.soft : const [],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                AnimatedContainer(
                  duration: const Duration(milliseconds: 180),
                  width: 8, height: 8,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: selected ? StitchColors.accentDeep : StitchColors.borderSoft,
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    label,
                    style: StitchTextStyles.sectionTitle.copyWith(
                      fontSize: 16,
                      color: selected ? StitchColors.accentDeep : StitchColors.textPrimary,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            // 资源说明
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
              decoration: BoxDecoration(
                color: selected ? StitchColors.card : StitchColors.cardGlow,
                borderRadius: BorderRadius.circular(6),
              ),
              child: Text(
                resourceHint,
                style: StitchTextStyles.muted.copyWith(fontSize: 11, height: 1.5),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _cloudConfigFields(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: StitchColors.cardGlow,
        borderRadius: BorderRadius.circular(StitchRadius.sm),
        border: Border.all(color: StitchColors.accent),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('云端精评配置', style: StitchTextStyles.eyebrow),
          const SizedBox(height: 12),
          _configField(context, 'API 地址', 'https://ark.cn-beijing.volces.com/api/v3',
              _cloudUrlCtrl, false),
          const SizedBox(height: 10),
          _configField(context, 'API Key', '粘贴你的 ARK API Key', _cloudKeyCtrl, true),
        ],
      ),
    );
  }

  Widget _configField(BuildContext context, String label, String hint,
      TextEditingController ctrl, bool obscure) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: StitchTextStyles.muted.copyWith(fontWeight: FontWeight.w700, fontSize: 12)),
        const SizedBox(height: 6),
        TextField(
          controller: ctrl,
          obscureText: obscure,
          style: const TextStyle(fontSize: 13),
          decoration: InputDecoration(
            hintText: hint,
            hintStyle: TextStyle(color: StitchColors.textFaint, fontSize: 13),
            contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            filled: true,
            fillColor: StitchColors.card,
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(StitchRadius.sm),
              borderSide: const BorderSide(color: StitchColors.borderSoft),
            ),
            enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(StitchRadius.sm),
              borderSide: const BorderSide(color: StitchColors.borderSoft),
            ),
            focusedBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(StitchRadius.sm),
              borderSide: const BorderSide(color: StitchColors.accentDeep, width: 2),
            ),
          ),
        ),
      ],
    );
  }
}
