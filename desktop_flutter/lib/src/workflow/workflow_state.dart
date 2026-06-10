enum WorkflowStep { modeFolder, analyze, review, select, export }

extension WorkflowStepText on WorkflowStep {
  String get label => switch (this) {
        WorkflowStep.modeFolder => '模式 / 文件夹',
        WorkflowStep.analyze => '分析',
        WorkflowStep.review => '复核',
        WorkflowStep.select => '选片',
        WorkflowStep.export => '导出',
      };
}
