import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';

import '../api/inkmoment_api.dart';
import '../design/stitch_components.dart';
import '../design/stitch_tokens.dart';
import '../l10n/strings.dart';

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
    setState(() {
      _busy = true;
      _error = '';
    });
    try {
      final payload = await widget.api.startJob({
        'folder': _folder,
        'mode': 'copy',
        'engine': _engine == 'fast' ? 'fast' : 'expert',
        'prescreen_enabled': true,
      });
      if (!mounted) return;
      widget.onStarted({...payload, 'folder': _folder});
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
                    Text(Zh.filterPlan, style: StitchTextStyles.muted.copyWith(fontWeight: FontWeight.w800)),
                    const SizedBox(height: 10),
                    Text(Zh.quickSelection, style: StitchTextStyles.sectionTitle.copyWith(fontSize: 24)),
                  ],
                ),
              ),
              Text(Zh.noConfigNeeded, style: StitchTextStyles.muted),
            ],
          ),
          const SizedBox(height: 28),
          LayoutBuilder(
            builder: (context, constraints) {
              final compact = constraints.maxWidth < 760;
              final cards = [
                _modeCard(context, Zh.quickSelection, Zh.quickSelectionDesc, 'fast'),
                _modeCard(context, Zh.textureFirst, Zh.textureFirstDesc, 'expert'),
                _modeCard(context, Zh.cloudReview, Zh.cloudReviewDesc, 'cloud'),
              ];
              if (compact) {
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    for (final card in cards) ...[card, const SizedBox(height: 12)],
                  ],
                );
              }
              return Row(
                children: [
                  for (var i = 0; i < cards.length; i++) ...[
                    Expanded(child: cards[i]),
                    if (i != cards.length - 1) const SizedBox(width: 18),
                  ],
                ],
              );
            },
          ),
        ],
      ),
    );
  }

  Widget _modeCard(BuildContext context, String title, String description, String value) {
    final selected = _engine == value;
    return GestureDetector(
      onTap: _busy ? null : () => setState(() => _engine = value),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 180),
        constraints: const BoxConstraints(minHeight: 170),
        padding: const EdgeInsets.all(24),
        decoration: BoxDecoration(
          color: selected ? StitchColors.cardGlow : StitchColors.cardGlow,
          border: Border.all(color: selected ? StitchColors.accentDeep : StitchColors.borderSoft, width: selected ? 2 : 1),
          borderRadius: BorderRadius.circular(StitchRadius.sm),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: StitchTextStyles.sectionTitle.copyWith(fontSize: 21)),
            const SizedBox(height: 14),
            Text(description, style: StitchTextStyles.body.copyWith(fontSize: 16, height: 1.5)),
          ],
        ),
      ),
    );
  }
}
