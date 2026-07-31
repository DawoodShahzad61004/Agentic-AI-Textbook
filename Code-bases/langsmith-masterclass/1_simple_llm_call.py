from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from llm_setup import llm

load_dotenv()

# Simple one-line prompt
prompt = PromptTemplate.from_template("{question}")

model = llm
parser = StrOutputParser()

# Chain: prompt → model → parser
chain = prompt | model | parser

# Run it
result = chain.invoke({"question": "What is the capital of Pakistan?"})
print(result)
