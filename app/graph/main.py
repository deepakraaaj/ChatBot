
from typing import Literal
from langgraph.graph import StateGraph, END
from app.graph.state import GraphState
from app.graph.nodes.understanding import UnderstandingNode
from app.graph.nodes.sql_planning import SQLPlanningNode
from app.graph.nodes.sql_execution import SQLExecutionNode
from app.graph.nodes.reply import ReplyNode
from app.graph.nodes.workflow_node import WorkflowNode

# Initialize Nodes
understanding_node = UnderstandingNode()
sql_planning_node = SQLPlanningNode()
sql_execution_node = SQLExecutionNode()
workflow_node = WorkflowNode()
reply_node = ReplyNode()

# Conditional Logic
def route_intent(state: GraphState) -> Literal["sql_planning", "workflow", "reply"]:
    intent = state.get("intent")
    if intent == "sql":
        return "sql_planning"
    elif intent == "workflow":
        return "workflow"
    return "reply"

def route_sql_success(state: GraphState) -> Literal["sql_execution", "reply"]:
    if state.get("sql_error"):
        return "reply" # Skip execution, go to reply to explain error
    return "sql_execution"

# Build Graph
workflow = StateGraph(GraphState)

workflow.add_node("understanding", understanding_node)
workflow.add_node("sql_planning", sql_planning_node)
workflow.add_node("sql_execution", sql_execution_node)
workflow.add_node("workflow", workflow_node)
workflow.add_node("reply", reply_node)

# Set Entry Point
workflow.set_entry_point("understanding")

# Add Edges
workflow.add_conditional_edges(
    "understanding",
    route_intent,
    {
        "sql_planning": "sql_planning",
        "workflow": "workflow",
        "reply": "reply"
    }
)

workflow.add_conditional_edges(
    "sql_planning",
    route_sql_success,
    {
        "sql_execution": "sql_execution",
        "reply": "reply" # plan failed
    }
)

workflow.add_edge("sql_execution", "reply")
workflow.add_edge("workflow", "reply")
workflow.add_edge("reply", END)

# Compile
app_graph = workflow.compile()
