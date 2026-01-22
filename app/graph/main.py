
from typing import Literal
from langgraph.graph import StateGraph, END
from app.graph.state import GraphState
from app.graph.nodes.understanding import UnderstandingNode
from app.graph.nodes.vector_search_node import VectorSearchNode
from app.graph.nodes.reply import ReplyNode
from app.graph.nodes.workflow_node import WorkflowNode

# Initialize Nodes
understanding_node = UnderstandingNode()
vector_search_node = VectorSearchNode()
workflow_node = WorkflowNode()
reply_node = ReplyNode()

# Conditional Logic
def route_intent(state: GraphState) -> Literal["vector_search", "workflow", "reply"]:
    intent = state.get("intent")
    if intent == "sql":
        # Route "sql" intent (List/Status) to Vector Search for pure RAG
        return "vector_search"
    elif intent == "workflow":
        return "workflow"
    return "reply"

# Build Graph
workflow = StateGraph(GraphState)

workflow.add_node("understanding", understanding_node)
workflow.add_node("vector_search", vector_search_node)
workflow.add_node("workflow", workflow_node)
workflow.add_node("reply", reply_node)

# Set Entry Point
workflow.set_entry_point("understanding")

# Add Edges
workflow.add_conditional_edges(
    "understanding",
    route_intent,
    {
        "vector_search": "vector_search",
        "workflow": "workflow",
        "reply": "reply"
    }
)

workflow.add_edge("vector_search", "reply")
workflow.add_edge("workflow", "reply")
workflow.add_edge("reply", END)

# Compile
app_graph = workflow.compile()
