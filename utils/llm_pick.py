import os
from dotenv import load_dotenv

# Python's SSL layer honors SSLKEYLOGFILE by writing TLS session secrets to
# that path. It is unnecessary for this app and can break HTTPS clients when
# the configured destination is inaccessible, so disable it in this process.
os.environ.pop("SSLKEYLOGFILE", None)

from langchain_groq import ChatGroq

load_dotenv()


def pick_llm(level: str):

    if level.lower() == "low":
        llm = ChatGroq(
            model="openai/gpt-oss-20b",
            temperature=0,
            api_key=os.getenv("GROQ_API_KEY")
        )

    elif level.lower() == "medium":
        llm = ChatGroq(
            model="qwen/qwen3.8-27b",
            temperature=0,
            api_key=os.getenv("GROQ_API_KEY")
        )

    elif level.lower() == "high":
        llm = ChatGroq(
            model="openai/gpt-oss-120b",
            temperature=0,
            api_key=os.getenv("GROQ_API_KEY")
        )

    else:
        raise ValueError(f"Unsupported level: {level}")

    return llm


if __name__ == "__main__":
    llm_obj = pick_llm("low")

    response = llm_obj.invoke(
        "What is the capital of France?"
    )

    print(response.content)
