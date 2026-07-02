import asyncio
import traceback
import os
import sys

# Ensure backend directory is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.llm_service import generate_answer

async def main():
    print("Testing Gemini generate_answer...")
    try:
        ans = await generate_answer(
            question="Hi, testing RAG capability",
            context="This is a test context with a ligature \ufb01 character."
        )
        print("Success! Response:")
        print(ans)
    except Exception as e:
        print("Error encountered:")
        print(str(e))
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
