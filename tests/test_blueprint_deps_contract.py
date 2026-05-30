import inspect
import unittest

from server.routes.auth import AuthDeps, create_auth_blueprint
from server.routes.dependencies import DependenciesDeps, create_dependencies_blueprint
from server.routes.folder import FolderDeps, create_folder_blueprint
from server.routes.grouping import GroupingDeps, create_grouping_blueprint
from server.routes.image import ImageDeps, create_image_blueprint
from server.routes.job import JobDeps, create_job_blueprint
from server.routes.llm import LlmDeps, create_llm_blueprint
from server.routes.results import ResultsDeps, create_results_blueprint
from server.routes.selection import SelectionHandlers, create_selection_blueprint
from server.routes.session import SessionDeps, create_session_blueprint
from server.routes.start import StartDeps, create_start_blueprint
from server.routes.system import SystemDeps, create_system_blueprint
from server.routes.task_history import TaskHistoryDeps, create_task_history_blueprint
from server.routes.watermark import WatermarkDeps, create_watermark_blueprint


class BlueprintDepsContractTest(unittest.TestCase):
    def test_blueprint_factories_accept_one_typed_dependency_object(self):
        factories = [
            (create_auth_blueprint, AuthDeps),
            (create_dependencies_blueprint, DependenciesDeps),
            (create_folder_blueprint, FolderDeps),
            (create_grouping_blueprint, GroupingDeps),
            (create_image_blueprint, ImageDeps),
            (create_job_blueprint, JobDeps),
            (create_llm_blueprint, LlmDeps),
            (create_results_blueprint, ResultsDeps),
            (create_selection_blueprint, SelectionHandlers),
            (create_session_blueprint, SessionDeps),
            (create_start_blueprint, StartDeps),
            (create_system_blueprint, SystemDeps),
            (create_task_history_blueprint, TaskHistoryDeps),
            (create_watermark_blueprint, WatermarkDeps),
        ]

        for factory, deps_type in factories:
            with self.subTest(factory=factory.__name__):
                params = list(inspect.signature(factory).parameters.values())
                self.assertEqual(len(params), 1)
                self.assertEqual(params[0].default, inspect.Parameter.empty)
                self.assertIs(params[0].annotation, deps_type)


if __name__ == "__main__":
    unittest.main()
