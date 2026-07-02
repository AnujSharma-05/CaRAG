"""
gemini_testing.py — Gemini RAG Answer Generation Test
-------------------------------------------------------
Purpose : Tests the end-to-end answer generation pipeline.
Checks  : Calls generate_answer() with a hardcoded question + context
          and prints the Gemini response.
Run     : python gemini_testing.py
Expect  : A short text response from Gemini about FastAPI.
"""
import asyncio
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.llm_service import generate_answer

async def main():
    response = await generate_answer(
        question="What is FastAPI?",
        context="""
FastAPI is a modern Python web framework.
"""
    )
    print(response)

if __name__ == "__main__":
    asyncio.run(main())