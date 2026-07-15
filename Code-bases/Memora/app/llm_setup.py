import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI


load_dotenv()

llm = ChatOpenAI(
    base_url=os.getenv("CUSTOM_API_BASE"),
    api_key=os.getenv("CUSTOM_API_KEY"),
    model=os.getenv("CUSTOM_API_MODEL_NAME", "llama-3.1-8b-instruct"),
    temperature=0.1,
    max_tokens=2048,
    max_retries=0,
)

merge_llm = ChatOpenAI(
    base_url=os.getenv("CUSTOM_API_BASE"),
    api_key=os.getenv("CUSTOM_API_KEY"),
    model=os.getenv("CUSTOM_API_MODEL_NAME", "llama-3.1-8b-instruct"),
    temperature=0.0,
    max_tokens=2048,
    max_retries=0,
)

judge_llm = ChatOpenAI(
    base_url=os.getenv("CUSTOM_API_BASE"),
    api_key=os.getenv("CUSTOM_API_KEY"),
    model=os.getenv("CUSTOM_API_MODEL_NAME", "llama-3.1-8b-instruct"),
    temperature=0.0,
    max_tokens=1024,
    max_retries=0,
)

json_fix_llm = ChatOpenAI(
    base_url=os.getenv("CUSTOM_API_BASE"),
    api_key=os.getenv("CUSTOM_API_KEY"),
    model=os.getenv("CUSTOM_API_MODEL_NAME", "Qwen/Qwen2.5-Coder-3B-Instruct"),
    temperature=0.0,
    max_tokens=1024,
    max_retries=0,
)



# import os
# from dotenv import load_dotenv
# from langchain_groq import ChatGroq
# from langchain_openai import ChatOpenAI


# load_dotenv()

# llm = ChatGroq(
#     api_key=os.getenv("GROQ_API_KEY"),
#     model_name=os.getenv("MODEL_NAME", "llama-3.1-8b-instant"),
#     temperature=0.1,
#     max_tokens=2048,
#     max_retries=0,
# )

# merge_llm = ChatGroq(
#     api_key=os.getenv("GROQ_API_KEY"),
#     model_name=os.getenv("MODEL_NAME", "llama-3.1-8b-instant"),
#     temperature=0.0,
#     max_tokens=2048,
#     max_retries=0,
# )

# judge_llm = ChatGroq(
#     api_key=os.getenv("GROQ_API_KEY"),
#     model_name=os.getenv("MODEL_NAME", "llama-3.1-8b-instant"),
#     temperature=0.0,
#     max_tokens=1024,
#     max_retries=0,
# )

# json_fix_llm = ChatOpenAI(
#     base_url=os.getenv("HF_API_BASE"),
#     api_key=os.getenv("HF_TOKEN"),
#     model=os.getenv("JSON_FIX_MODEL_NAME", "Qwen/Qwen2.5-Coder-3B-Instruct"),
#     temperature=0.0,
#     max_tokens=1024,
#     max_retries=0,
# )


