from ingest.ingest_db_standard_manual import main as ingest_db_standard_manual
from ingest.ingest_public_standard import main as ingest_public_standard
from ingest.srs_ingest_glossary import main as ingest_glossary
from ingest.srs_ingest_requirement_examples import main as ingest_requirement_examples
from ingest.srs_ingest_requirement_reference import main as ingest_requirement_reference
from ingest.srs_ingest_requirement_sources import main as ingest_requirement_sources


def main():
    ingest_public_standard()
    ingest_db_standard_manual()
    ingest_glossary()
    ingest_requirement_reference()
    ingest_requirement_sources()
    ingest_requirement_examples()


if __name__ == "__main__":
    main()

