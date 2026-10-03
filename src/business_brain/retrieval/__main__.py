"""Run the deterministic document-ingestion pipeline."""

from business_brain.retrieval.qdrant_ingestion import ingest_documents


def main() -> None:
    report = ingest_documents()
    print(f"Collection: {report.collection_name}")
    print(f"Verified documents: {report.document_count}")
    print(f"Verified points: {report.point_count}")


if __name__ == "__main__":
    main()
