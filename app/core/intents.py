
# Valid Intents (used by LLM)
CREATE_SCHEDULE = "create_schedule"
UPDATE_TASK = "update_task"

# Intent Metadata for LLM System Prompt
INTENT_DESCRIPTIONS = {
    CREATE_SCHEDULE: "Create a new maintenance schedule or assign a task",
    UPDATE_TASK: "Update the status or details of an existing task"
}

# Mapping from Intent to Internal Workflow Name (keys in engine registry)
INTENT_WORKFLOW_MAP = {
    CREATE_SCHEDULE: "scheduler",
    UPDATE_TASK: "update_task"
}
