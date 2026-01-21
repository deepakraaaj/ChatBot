
from typing import Dict, Any, Optional
from app.workflow.base import BaseWorkflow

class HelpWorkflow(BaseWorkflow):
    @property
    def name(self) -> str:
        return "help"

    async def step(
        self, 
        current_step: Optional[str], 
        user_input: str,
        user_id: str,
        company_id: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        
        # If this is the start (or just "what can you do")
        return {
            "workflow_step": "end", # One-shot workflow
            "context": context,
            "view": {
                "type": "menu",
                "payload": {
                    "text": f"Hello! I am your REMP Operations Assistant. Here's a quick guide to what I can do for you:",
                    "categories": [
                        {
                            "title": "⚡ Quick Actions",
                            "options": [
                                "Create a new schedule",
                                "Update task status"
                            ]
                        },
                        {
                            "title": "📊 Insights & Reports",
                            "options": [
                                "Show pending tasks",
                                "List all facilities",
                                "Recent completions summary"
                            ]
                        },
                        {
                            "title": "🔍 Search",
                            "options": [
                                "Find a specific task",
                                "Search for facility logs"
                            ]
                        }
                    ],
                    # Flattened options for simple UI clients
                    "options": [
                        "Create a new schedule",
                        "Update task status",
                        "Show pending tasks",
                        "List all facilities",
                        "Recent completions summary",
                        "Find a specific task",
                        "Search for facility logs"
                    ]
                }
            }
        }
