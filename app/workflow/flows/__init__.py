from .scheduler import SchedulerWorkflow
from .update_task import UpdateTaskWorkflow
from .help import HelpWorkflow

# Registry of all available workflows
# New workflows should be added here
AVAILABLE_WORKFLOWS = [
    SchedulerWorkflow(),
    UpdateTaskWorkflow(),
    HelpWorkflow()
]
