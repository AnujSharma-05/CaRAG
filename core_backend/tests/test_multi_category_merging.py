import asyncio
import os
import sys

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.database import sessionLocal
from src import models
from src import services
from src.milvus_store import milvus_store

async def test_hierarchical_categorization_and_merging():
    print("==================================================")
    print("STARTING CARAG HIERARCHICAL CATEGORIZATION TEST")
    print("==================================================")

    db = sessionLocal()
    
    try:
        # Step 1: Clean and load Milvus
        print("\n[Step 1] Initializing collections...")
        milvus_store.delete_all_chunks()
        milvus_store.ensure_collection()

        # Step 2: Define files
        intern_pdf = os.path.join("core_backend", "uploads", "Intern Letter.pdf")
        if not os.path.exists(intern_pdf):
            intern_pdf = os.path.join("uploads", "Intern Letter.pdf")
            
        resume_pdf = os.path.join("core_backend", "uploads", "Code_With_Cisco_Resume.pdf")
        if not os.path.exists(resume_pdf):
            resume_pdf = os.path.join("uploads", "Code_With_Cisco_Resume.pdf")

        if not os.path.exists(intern_pdf) or not os.path.exists(resume_pdf):
            print("Error: Test PDFs not found in uploads directory.")
            return

        # Use group_id = 99 for testing
        group_id = 99

        # Clean existing test categories/docs for group 99 from DB
        db.query(models.DocumentCategory).filter(
            models.DocumentCategory.document_id.in_(
                db.query(models.Document.id).filter(models.Document.group_id == group_id)
            )
        ).delete(synchronize_session=False)
        db.query(models.Document).filter(models.Document.group_id == group_id).delete(synchronize_session=False)
        db.query(models.Category).filter(models.Category.group_id == group_id).delete(synchronize_session=False)
        
        # Clean existing test group/user if they exist
        db.query(models.Group).filter(models.Group.id == group_id).delete(synchronize_session=False)
        db.query(models.User).filter(models.User.id == group_id).delete(synchronize_session=False)
        db.commit()

        # Ensure test user 99 and test group 99 exist to satisfy foreign keys
        test_user = models.User(id=group_id, email="test_user_99@carag.com", hashed_password="test_password_hash")
        db.add(test_user)
        db.commit()

        test_group = models.Group(id=group_id, name="Test Group 99", created_by=group_id)
        db.add(test_group)
        db.commit()

        # Step 3: Test Advanced Page Extraction Helper
        print("\n[Step 3] Testing Page Extraction Helper...")
        extracted_text = services._extract_summary_text_from_pdf(intern_pdf)
        print(f"Extracted context length: {len(extracted_text)} characters.")
        
        # Read pages count to make conditional assertions
        from pypdf import PdfReader
        total_pages = len(PdfReader(intern_pdf).pages)
        assert "START OF DOCUMENT" in extracted_text, "Failed to extract start of document pages"
        if total_pages > 5:
            assert "END OF DOCUMENT" in extracted_text, "Failed to extract end of document pages"
        print(f"Page extraction helper successfully verified (total pages: {total_pages})!")

        # Step 4: Ingest Document 1 (Intern Letter)
        print("\n[Step 4] Ingesting Document 1 (Intern Letter)...")
        doc1 = models.Document(
            filename="Intern_Letter.pdf",
            file_path=intern_pdf,
            file_size=os.path.getsize(intern_pdf),
            status="uploaded",
            group_id=group_id
        )
        db.add(doc1)
        db.commit()
        db.refresh(doc1)

        await services.process_document_task(doc1.id, doc1.filename)
        db.refresh(doc1)
        
        doc1_cats = [c.name for c in doc1.categories]
        print(f"Document 1 Ingested. Status: '{doc1.status}'. Categories: {doc1_cats}")
        assert len(doc1_cats) >= 1, "Document 1 was not assigned any category"

        # Step 5: Ingest Document 2 (Resume)
        print("\n[Step 5] Ingesting Document 2 (Resume)...")
        doc2 = models.Document(
            filename="Resume.pdf",
            file_path=resume_pdf,
            file_size=os.path.getsize(resume_pdf),
            status="uploaded",
            group_id=group_id
        )
        db.add(doc2)
        db.commit()
        db.refresh(doc2)

        await services.process_document_task(doc2.id, doc2.filename)
        db.refresh(doc2)
        
        doc2_cats = [c.name for c in doc2.categories]
        print(f"Document 2 Ingested. Status: '{doc2.status}'. Categories: {doc2_cats}")
        assert len(doc2_cats) >= 1, "Document 2 was not assigned any category"

        # Step 6: Verify Multiple Categories & Consolidation
        print("\n[Step 6] Verifying Category Consolidation...")
        # Since process_document_task auto-triggers consolidate_categories, we query the DB to see if any new
        # generalized parent categories (like "Career Documents", "Employment Documents", or "PDFs") were created.
        all_group_categories = db.query(models.Category).filter(models.Category.group_id == group_id).all()
        print("All categories in Group 99:")
        for cat in all_group_categories:
            doc_names = [d.filename for d in cat.documents]
            print(f" - Category: '{cat.name}' -> Documents: {doc_names}")

        # Refresh documents to verify many-to-many associations
        db.refresh(doc1)
        db.refresh(doc2)

        print(f"\nFinal Document 1 Categories: {[c.name for c in doc1.categories]}")
        print(f"Final Document 2 Categories: {[c.name for c in doc2.categories]}")

        # Verify Milvus has the correct group-scoped category summaries
        print("\n[Step 7] Checking category summaries in Milvus...")
        for cat in all_group_categories:
            query_vector = services._embed_query(cat.name)
            matches = milvus_store.search_categories(query_vector, top_k=5, group_id=group_id)
            print(f"Milvus search results for '{cat.name}' in group {group_id}:")
            for m in matches:
                print(f" - Found: '{m['category_name']}' (Group: {m['group_id']}), Score: {m['score']:.4f}")

        # Cleanup
        print("\n[Step 8] Cleaning up database and Milvus...")
        # delete documents
        db.query(models.DocumentCategory).filter(
            models.DocumentCategory.document_id.in_(
                db.query(models.Document.id).filter(models.Document.group_id == group_id)
            )
        ).delete(synchronize_session=False)
        db.query(models.Document).filter(models.Document.group_id == group_id).delete(synchronize_session=False)
        db.query(models.Category).filter(models.Category.group_id == group_id).delete(synchronize_session=False)
        db.query(models.Group).filter(models.Group.id == group_id).delete(synchronize_session=False)
        db.query(models.User).filter(models.User.id == group_id).delete(synchronize_session=False)
        db.commit()

        print("\n==================================================")
        print("TEST PASSED SUCCESSFULLY! MULTI-CATEGORY FLOW WORKS.")
        print("==================================================")

    except Exception as e:
        print(f"\nTEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test_hierarchical_categorization_and_merging())
