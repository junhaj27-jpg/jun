from phase1_config import get_qdrant
from phase1_config import CONFIG

qdrant = get_qdrant()

for col in [CONFIG["rfp_collection"], CONFIG["req_collection"]]:
    count = qdrant.count(collection_name=col).count
    print(f"컬렉션 '{col}' 데이터 개수: {count}")