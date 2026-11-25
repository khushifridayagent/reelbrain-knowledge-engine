"""Serverless retrieval over persistent Postgres evidence, without a local index."""
from psycopg.types.json import Jsonb
from .core import terms

class HostedIndex:
    def __init__(self, db):
        self.db = db

    def _rows(self, queries, filters, selected, offset, limit):
        words = list(dict.fromkeys(w for q in queries for w in terms(q)))[:24]
        return self.db._call(
            'select * from reelbrain_studio.hosted_search(%s,%s,%s,%s,%s)',
            (words, Jsonb(filters), selected, offset, limit),
        )

    def search(self, q, queries, filters, limit=8, enumerate_all=False, offset=0):
        rows = self._rows(queries, filters, None, offset, limit)
        cards = [row['card'] for row in rows]
        if not enumerate_all:
            return cards
        total = rows[0]['total'] if rows else 0
        return {'results': cards, 'total_keyword_matches': total,
                'next_offset': offset + limit if offset + limit < total else None}

    def contextual_sources(self, question, queries, selected):
        rows = self._rows(queries, {}, selected, 0, len(selected))
        by_url = {row['card']['source']: row['card'] for row in rows}
        return [by_url[url] for url in selected if url in by_url]
