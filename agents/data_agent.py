import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.llm_pick import pick_llm
from Models.schema import DataAgentSchema
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, START, END
from agents.etl_agent import etl_analyst
from agents.sql_analyst import sql_analyst


llm = pick_llm("high")

# ---------------------------- DATA AGENT GRAPH ---------------------------- #


def router_node(state:DataAgentSchema):

    message = state.messages[-1].content.lower()

    # Keep routing local and deterministic. Some Groq models do not reliably
    # honor LangChain's forced tool call used by with_structured_output().
    etl_intents = (
        "extract", "etl", "transform", "load", "api endpoint", "api data",
        "csv", "json", "parquet", "save the data", "save it to", "file",
    )
    sql_intents = (
        "sql", "database", "table", "query", "select", "join", "postgres",
    )
    has_etl_intent = any(term in message for term in etl_intents)
    has_sql_intent = any(term in message for term in sql_intents)

    if has_etl_intent and not has_sql_intent:
        route_response = "etl"
    elif has_sql_intent and not has_etl_intent:
        route_response = "sql"
    else:
        # SQL is the default for ambiguous data questions; explicit ETL words
        # still route to ETL above.
        route_response = "sql"

    state.route_response = route_response

    return state

def etl_node(state:DataAgentSchema):

    message = state.messages[-1].content

    response = etl_analyst.invoke(
             {"messages":[HumanMessage(content=f"""
            {message}
    """)]}
        ) 
    state.messages = state.messages + [response]

    return state

def sql_node(state:DataAgentSchema):

    message = state.messages[-1].content

    input_schema = {
        "messages": [],
        "user_question": f"{message}",
        "curated_ques": "",
        "prompt_query_context": "",
        "generated_sql_query": "",
        "is_safe": "No",
        "comments": "",
        "sql_query_execution_result": "",
        "final_answer": ""
    }

    response = sql_analyst.invoke(input_schema)

    state.messages = state.messages + [response]

    return state




data_agent_graph = StateGraph(DataAgentSchema)

data_agent_graph.add_node("router_node", router_node)
data_agent_graph.add_node("etl_node", etl_node)
data_agent_graph.add_node("sql_node", sql_node)

data_agent_graph.add_edge(START, "router_node")

def route_edge(state: DataAgentSchema) -> str:
    if state.route_response == "sql":
        return "sql_node"
    elif state.route_response == "etl":
        return "etl_node"
    else:
        raise ValueError(f"Invalid route response: {state.route_response}")


data_agent_graph.add_conditional_edges("router_node", route_edge,
                                      {
                                          "sql_node": "sql_node",
                                          "etl_node": "etl_node"
                                      })

data_agent = data_agent_graph.compile()

# Optional|
from IPython.display import display, Image
img = Image(data_agent.get_graph().draw_mermaid_png())
with open("data_agent_graph.png", "wb") as f:
    f.write(img.data)



if __name__ == "__main__":

    response = data_agent.invoke(
        {"messages":[HumanMessage(content="I want to extract the data from the API endpoint 'https://pokeapi.co/api/v2/pokemon' and save it to data/extract folder in the csv folder")],
         "route_response": ""}
    )

    print(response)



