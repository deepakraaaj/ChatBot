
# Valid Intents (used by LLM)
CREATE_SCHEDULE = "create_schedule"
UPDATE_TASK = "update_task"
HELP = "help"

# Intent Metadata for LLM System Prompt
INTENT_DESCRIPTIONS = {
    CREATE_SCHEDULE: "Create a new maintenance schedule or assign a task",
    UPDATE_TASK: "Update the status or details of an existing task",
    HELP: "User asks what the bot can do, capabilities, or help",
    "cancel": "User wants to stop the current action, reset, or cancel a workflow"
}

# Mapping from Intent to Internal Workflow Name (keys in engine registry)
INTENT_WORKFLOW_MAP = {
    CREATE_SCHEDULE: "scheduler",
    UPDATE_TASK: "update_task",
    HELP: "help",
    "cancel": None # Will be handled by clearing state
}
