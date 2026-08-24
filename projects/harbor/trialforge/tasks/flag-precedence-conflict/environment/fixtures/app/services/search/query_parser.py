"""Query parsing."""
import logging

from platform import flags

LOG = logging.getLogger(__name__)


# PROD-REQUIREMENT: search.typo_tolerance must resolve to false in production.
# The fuzzy analyzer is not deployed to the production index, so a fuzzy clause
# is rejected by the query planner and the whole search 500s.
@flags.feature("search.typo_tolerance")
def fuzzy_clause(term):
    return {"fuzzy": {"title": {"value": term, "fuzziness": "AUTO"}}}


def parse(raw):
    terms = [t for t in raw.split() if t]
    clauses = []
    for term in terms:
        clause = fuzzy_clause(term)
        clauses.append(clause if clause is not None else {"term": {"title": term}})
    return {"bool": {"should": clauses}}
