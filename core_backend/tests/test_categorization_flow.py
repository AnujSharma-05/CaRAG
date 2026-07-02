import asyncio
import os
import sys
import shutil

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.database import sessionLocal
from src import models
from src import services
from src.milvus_store import milvus_store

async def run_end_to_end_test():
    print("==================================================")
    print("STARTING CARAG CORE ENGINE CATEGORIZATION FLOW TEST")
    print("==================================================")

    db = sessionLocal()
    try:
        # Step 1: Ensure Milvus collections are initialized
        print("\n[Step 1] Initializing Milvus collections...")
        milvus_store.ensure_collection()

        # Step 2: Create a test document record in PostgreSQL
        print("\n[Step 2] Registering test document...")
        backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        test_pdf = os.path.join(backend_dir, "uploads", "Intern Letter.pdf")
        if not os.path.exists(test_pdf):
            print(f"Error: Test PDF '{test_pdf}' not found. Please place it in core_backend/uploads/.")
            return

        file_size = os.path.getsize(test_pdf)
        
        # We will name it specifically for testing
        test_doc = models.Document(
            filename="Test_Intern_Letter.pdf",
            file_path=test_pdf,
            file_size=file_size,
            status="uploaded",
        )
        db.add(test_doc)
        db.commit()
        db.refresh(test_doc)
        
        # Associate with general category
        db_category = db.query(models.Category).filter(models.Category.name == "general").first()
        if not db_category:
            db_category = models.Category(name="general", group_id=None)
            db.add(db_category)
            db.commit()
            db.refresh(db_category)
        test_doc.categories.append(db_category)
        db.commit()
        
        print(f"Registered document in DB: ID={test_doc.id}, Category={test_doc.categories[0].name if test_doc.categories else 'general'}")

        # Step 3: Run the ingestion pipeline (process_document_task)
        print("\n[Step 3] Running process_document_task...")
        # Since it is a background task, we run it directly here
        await services.process_document_task(test_doc.id, test_doc.filename)

        # Refresh from database to see changes
        db.refresh(test_doc)
        resolved_category = test_doc.categories[0].name if test_doc.categories else "general"
        print(f"Document ingestion complete.")
        print(f"Auto-Categorized Category: '{resolved_category}'")
        print(f"Ingestion Status: '{test_doc.status}'")

        assert test_doc.status == "ready", f"Ingestion failed! Status is {test_doc.status}"
        assert resolved_category != "general", "Categorization failed! Document is still categorized as 'general'"

        # Step 4: Verify that Category Summary exists in Milvus
        print("\n[Step 4] Checking category summary in Milvus...")
        # Embed the category name/first chunk to search
        query_vector = services._embed_query(resolved_category)
        matches = milvus_store.search_categories(query_vector, top_k=5)
        
        print(f"Found category summaries in Milvus:")
        found_our_category = False
        for m in matches:
            print(f" - Category: '{m['category_name']}', Score: {m['score']:.4f}, Summary: {m['summary']}")
            if m['category_name'].lower() == resolved_category.lower():
                found_our_category = True

        assert found_our_category, f"Category summary for '{resolved_category}' was not found in Milvus!"
        print("Category summary successfully created and verified in Milvus!")

        # Step 5: Clean up document and assets
        print("\n[Step 5] Cleaning up document and testing categorical description update...")
        # Keep track of category name
        category_name = test_doc.categories[0].name if test_doc.categories else "general"

        # Delete document from DB
        await services.delete_document_assets(document_id=test_doc.id, file_path=None) # Pass None to keep the physical file on disk
        db.delete(test_doc)
        db.commit()
        print("Deleted document record from DB and vector chunks from Milvus.")

        # Trigger update/deletion of summary
        other_docs_exist = db.query(models.Document).join(models.Document.categories).filter(
            models.Category.name == category_name,
            models.Document.status == "ready"
        ).first()

        if not other_docs_exist:
            milvus_store.delete_category_summary(category_name)
            print(f"Deleted category summary for '{category_name}' since no other documents remain in this category.")
        else:
            await services.update_categorical_summary(category_name)
            print(f"Updated category summary for '{category_name}' since other documents remain.")

        print("\n==================================================")
        print("TEST PASSED SUCCESSFULLY! ALL FLOWS WORKING FINE.")
        print("==================================================")

    except Exception as e:
        print(f"\nTEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(run_end_to_end_test())
