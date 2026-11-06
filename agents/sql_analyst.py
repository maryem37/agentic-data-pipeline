import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils.llm_pick import pick_llm

llm = pick_llm("low")
print(llm.invoke("What is the capital of France?").content)