"""하이브리드 검색 — pgvector 벡터 + BM25 키워드 → RRF 결합.

벡터 검색만 사용하면 고유명사 쿼리에 약하므로 BM25 와 결합한다.
"""
from sqlalchemy import text
from rank_bm25 import BM25Okapi

from app.db.session import SessionLocal
from app.services.embedder import embed_query


def hybrid_search(user_id: str, query: str, top_k: int = 5) -> list[dict]:
    """벡터 + BM25 하이브리드 검색.

    Returns:
        [{"id", "title", "summary", "thumbnail_url", "category", "score"}, ...]
    """
    # 1) 쿼리 임베딩
    emb = embed_query(query)
    emb_str = "[" + ",".join(str(v) for v in emb) + "]"

    with SessionLocal() as db:
        # 2) 벡터 검색 — 코사인 거리 기준 상위 K*2
        vec_sql = text("""
            SELECT id, title, summary, thumbnail_url, category, url,
                   1 - (embedding <=> CAST(:emb AS vector)) AS score
            FROM contents
            WHERE user_id = :uid
            ORDER BY embedding <=> CAST(:emb AS vector)
            LIMIT :k
        """)
        vec_rows = db.execute(
            vec_sql, {"emb": emb_str, "uid": user_id, "k": top_k * 2}
        ).mappings().all()

        # 3) BM25 키워드 검색 — 같은 사용자의 모든 콘텐츠 텍스트에 대해
        all_rows = db.execute(
            text("""
                SELECT id, title, summary, thumbnail_url, category, url
                FROM contents WHERE user_id = :uid
            """),
            {"uid": user_id},
        ).mappings().all()

    bm25_top: list[tuple] = []
    if all_rows:
        corpus = [f"{r['title']} {r['summary']}".split() for r in all_rows]
        bm25 = BM25Okapi(corpus)
        scores = bm25.get_scores(query.split())
        bm25_top = sorted(
            zip(all_rows, scores),
            key=lambda x: x[1],
            reverse=True,
        )[:top_k * 2]

    # 4) Reciprocal Rank Fusion 으로 결합
    rrf: dict[str, float] = {}
    for rank, row in enumerate(vec_rows):
        rrf[str(row["id"])] = rrf.get(str(row["id"]), 0) + 1 / (60 + rank)
    for rank, (row, _) in enumerate(bm25_top):
        rrf[str(row["id"])] = rrf.get(str(row["id"]), 0) + 1 / (60 + rank)

    # 5) 메타 조인 후 Top-K 반환
    meta_map = {str(r["id"]): dict(r) for r in vec_rows}
    for r, _ in bm25_top:
        meta_map.setdefault(str(r["id"]), dict(r))

    sorted_ids = sorted(rrf, key=rrf.get, reverse=True)[:top_k]
    results = []
    for cid in sorted_ids:
        if cid in meta_map:
            item = meta_map[cid]
            item["score"] = round(rrf[cid], 4)
            # UUID → str 직렬화 안전
            item["id"] = str(item["id"])
            results.append(item)
    return results
