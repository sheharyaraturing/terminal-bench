"""Result ranking."""
import logging

from platform import flags

LOG = logging.getLogger(__name__)
BM25_K1 = 1.2
BM25_B = 0.75


def rank(hits, query):
    scored = [(_bm25(hit, query), hit) for hit in hits]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    ordered = [hit for _, hit in scored]
    if flags.get_bool("search.semantic_rerank", default=False):
        ordered = _rerank(ordered, query)
    return ordered


def _bm25(hit, query):
    return sum(hit.term_frequency(term) * BM25_K1 for term in query.terms)


def _rerank(ordered, query):
    return sorted(ordered, key=lambda hit: -hit.embedding_similarity(query))
