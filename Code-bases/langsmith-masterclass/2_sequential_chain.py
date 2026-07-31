from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from llm_setup import llm

load_dotenv()

prompt1 = PromptTemplate(
    template='Generate a detailed report on {topic}',
    input_variables=['topic']
)

prompt2 = PromptTemplate(
    template='Generate a 5 pointer summary from the following text \n {text}',
    input_variables=['text']
)

model = llm

parser = StrOutputParser()

chain = prompt1 | model | parser | prompt2 | model | parser

config = {
    'run_name': 'sequential_chain_run',
    'tags': ['economy', 'employment', 'India'],
    'metadata': {'source': 'government reports', 'date': '2023-01-01'}
}

result = chain.invoke({'topic': 'Unemployment in India'}, config=config)

print(result)
