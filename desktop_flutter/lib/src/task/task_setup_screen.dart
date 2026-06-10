import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';

import '../api/inkmoment_api.dart';
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
        'engine': _engine,
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
    return _Panel(
      title: '选择模式与照片文件夹',
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Wrap(spacing: 12, runSpacing: 12, children: [
          _modeCard('快速选片', '基础分析，适合先跑一遍大批量照片', 'fast'),
          _modeCard('AI 初筛', '启用智能初筛，先找出明显问题照片', 'expert'),
          _modeCard('完整流程', '分析、复核、选片、导出全部串联', 'expert'),
        ]),
        const SizedBox(height: 22),
        Row(children: [
          Expanded(child: Text(_folder.isEmpty ? '尚未选择照片文件夹' : _folder, overflow: TextOverflow.ellipsis)),
          const SizedBox(width: 12),
          OutlinedButton(onPressed: _busy ? null : _pickFolder, child: const Text(Zh.chooseFolder)),
        ]),
        const SizedBox(height: 16),
        _scanSummary(),
        const Spacer(),
        if (_error.isNotEmpty) Text(_error, style: const TextStyle(color: Color(0xFFFFB95F))),
        Align(
          alignment: Alignment.centerRight,
          child: FilledButton(
            onPressed: _folder.isEmpty || _busy ? null : _start,
            child: Text(_busy ? '处理中' : Zh.startAnalyze),
          ),
        ),
      ]),
    );
  }

  Widget _modeCard(String title, String description, String value) {
    final selected = _engine == value;
    return InkWell(
      onTap: () => setState(() => _engine = value),
      child: Container(
        width: 220,
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: selected ? const Color(0xFF123C2A) : const Color(0xFF1A211D),
          border: Border.all(color: selected ? const Color(0xFF10B981) : const Color(0xFF2F3632)),
          borderRadius: BorderRadius.circular(6),
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(title, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          Text(description, style: const TextStyle(color: Color(0xFFBBCABF))),
        ]),
      ),
    );
  }

  Widget _scanSummary() {
    if (_peek == null) return const Text('选择文件夹后会显示照片数量与预览摘要。');
    final count = _peek?['count'] ?? _peek?['total'] ?? 0;
    return Text('已扫描 $count 张照片');
  }
}

class _Panel extends StatelessWidget {
  const _Panel({required this.title, required this.child});
  final String title;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(title, style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w700)),
        const SizedBox(height: 18),
        Expanded(child: child),
      ]),
    );
  }
}
