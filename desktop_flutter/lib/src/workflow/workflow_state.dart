import '../l10n/strings.dart';

enum WorkflowStep { modeFolder, analyze, review, select, export }

extension WorkflowStepText on WorkflowStep {
  String get label => switch (this) {
    WorkflowStep.modeFolder => Zh.modeFolderStep,
    WorkflowStep.analyze => Zh.analyze,
    WorkflowStep.review => Zh.review,
    WorkflowStep.select => Zh.select,
    WorkflowStep.export => Zh.export,
  };
}
