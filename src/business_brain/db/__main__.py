"""Command line entry point for Neon database setup."""

from business_brain.db.ingestion import migrate_seed_verify


def main() -> None:
    report = migrate_seed_verify()
    print(f"Applied migrations: {report.migration_count}")
    print(f"Verified tables: {len(report.table_counts)}")
    print(f"Verified rows: {report.total_rows}")


if __name__ == "__main__":
    main()
