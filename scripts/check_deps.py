import llama_index.core
import chromadb
import httpx
import bs4
import openai
import tiktoken

print("llama-index.core: OK")
print("chromadb:", chromadb.__version__)
print("httpx:", httpx.__version__)
print("bs4:", bs4.__version__)
print("openai:", openai.__version__)
print("tiktoken:", tiktoken.__version__)
print("All imports OK!")