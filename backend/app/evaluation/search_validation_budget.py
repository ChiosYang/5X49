"""Explicit, bounded continuation on the original ledger; never a new account.

The supplemental grant preserves expired authorization, historical halt and every
old receipt. Standard SearchBudget callers still fail closed. Activation is an
operator action after a new user authorization, never an automatic retry.
"""
import json
import re

from app.services.search_budget import SearchBudget
from app.services.openrouter_embeddings import _decimal
from app.services.search_providers import EMBEDDING
from app.services.semantic_search import SemanticError, _hash

PREFIX = 'bounded_validation_v1_'


class ValidationBudget(SearchBudget):
    @classmethod
    def view(cls, original):
        value = cls.__new__(cls)
        value.__dict__ = original.__dict__.copy()
        return value

    def historical_meta(self):
        return {k: v for k, v in self.db.execute('SELECT key,value FROM search_budget_meta')
                if not k.startswith(PREFIX)}

    def activate(self, grant):
        """Append a single supplemental grant; never replace the old grant."""
        saved = self._value(PREFIX + 'grant')
        if saved:
            if json.loads(saved) != grant:
                raise SemanticError('search_validation_grant_changed')
            return self._grant()
        try:
            self.db.execute('BEGIN IMMEDIATE')
            self._check(grant)
            rows = self._rows()
            if len(rows) != grant['baseline']:
                raise SemanticError('search_validation_already_attempted')
            self.db.execute('INSERT INTO search_budget_meta VALUES (?,?)',
                            (PREFIX + 'grant', json.dumps(grant)))
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return grant

    def _rows(self):
        return [dict(r) for r in self.db.execute('SELECT * FROM search_budget_receipts ORDER BY number')]

    def _check(self, grant):
        try:
            rows = self._rows()
            old = rows[:grant['baseline']]
            batches = grant['document_batches']
            if (grant['version'] != 'bounded-validation-grant.v1'
                    or grant['original_grant'] != self.authorization.fingerprint
                    or self._value('authorization') != self.authorization.fingerprint
                    or grant['baseline'] != 137 or grant['max_attempts'] != 191
                    or self.authorization.max_posts != 320 or _decimal(self.authorization.limit_usd) != 0
                    or type(grant['expires']) is not int or type(grant['issued']) is not int
                    or not 0 < grant['expires'] - grant['issued'] <= 86400
                    or not grant['issued'] <= self.clock() < grant['expires']
                    or _hash(old) != grant['original_rows_sha256']
                    or _hash(self.historical_meta()) != grant['historical_meta_sha256']
                    or len(old) != 137 or old[-1]['number'] != 137
                    or [(r['number'], r['state']) for r in old if r['state'] not in {'reported', 'not_sent'}]
                        != [(50, 'uncertain'), (137, 'uncertain')]
                    or old[-1]['scope'] != 'persistent-test-library.v1' or old[-1]['purpose'] != 'document'
                    or old[-1]['cost'] is not None or _decimal(old[-1]['reservation']) != 0
                    or any(_decimal(r['cost'] or 0) != 0 for r in old)
                    or len(batches) != 4 or len(set(batches)) != 4
                    or any(not isinstance(v, str) or not re.fullmatch('[a-f0-9]{64}', v) for v in batches)
                    or batches[0] != old[-1]['input_hash']):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise SemanticError('search_validation_grant_invalid') from None

    def _grant(self):
        try:
            grant = json.loads(self._value(PREFIX + 'grant') or 'null')
            self._check(grant)
            return grant
        except (TypeError, ValueError):
            raise SemanticError('search_validation_not_authorized') from None

    def reserve(self, purpose, scope, *, input_hash, tokens, reservation):
        if (purpose not in {'document', 'query', 'decision', 'rerank'}
                or scope not in {'public-evaluation.v2', 'persistent-test-library.v1'}
                or not isinstance(input_hash, str) or not re.fullmatch('[a-f0-9]{64}', input_hash)
                or type(tokens) is not int or not 0 < tokens <= 100000 or _decimal(reservation) != 0):
            raise SemanticError('search_reservation_invalid')
        try:
            self.db.execute('BEGIN IMMEDIATE')
            grant = self._grant()
            rows = self._rows(); new = rows[grant['baseline']:]
            if (len(rows) >= grant['max_attempts'] or self._value(PREFIX + 'halt')
                    or any(r['state'] not in {'reported', 'not_sent'} or _decimal(r['cost'] or 0) != 0 for r in new)):
                raise SemanticError('search_budget_blocked')
            if not self._value(PREFIX + 'repeat_complete'):
                if (new or purpose != 'document' or scope != rows[136]['scope']
                        or input_hash != rows[136]['input_hash'] or tokens != rows[136]['tokens']):
                    raise SemanticError('search_recovery_repeat_mismatch')
            if purpose == 'document':
                used = [r for r in new if r['purpose'] == 'document']
                if (scope != 'persistent-test-library.v1' or len(used) >= 4
                        or input_hash != grant['document_batches'][len(used)]):
                    raise SemanticError('search_validation_document_mismatch')
            else:
                used = [r for r in new if r['purpose'] != 'document' and r['scope'] == scope]
                if len(used) >= (30 if scope == 'persistent-test-library.v1' else 20):
                    raise SemanticError('search_validation_stage_limit')
            cursor = self.db.execute('''INSERT INTO search_budget_receipts
                (purpose,scope,input_hash,tokens,reservation,state,evidence)
                VALUES (?,?,?,?,'0','pending','{}')''', (purpose, scope, input_hash, tokens))
            self.db.commit()
            return cursor.lastrowid
        except Exception:
            self.db.rollback()
            raise

    def fail(self, number, code, elapsed):
        if not isinstance(code, str) or not re.fullmatch('[a-z_0-9]{1,80}', code):
            code = 'search_provider_unavailable'
        with self.db:
            self.db.execute("UPDATE search_budget_receipts SET state=CASE WHEN state='reported' THEN state ELSE 'uncertain' END,elapsed_ms=? WHERE number=?",
                            (round(elapsed * 1000, 3), number))
            self.db.execute('INSERT OR REPLACE INTO search_budget_meta VALUES (?,?)',
                            (PREFIX + 'halt', json.dumps({'number': number, 'code': code})))

    def complete_repeat(self, store, spec, texts):
        grant = self._grant()
        rows = self._rows(); row = rows[137] if len(rows) > 137 else None
        body = {'input': list(texts), 'encoding_format': 'float', 'input_type': 'passage'}
        evidence = json.loads(row['evidence']) if row else {}
        if (self._value(PREFIX + 'repeat_complete') or self._value(PREFIX + 'halt') or not row
                or row['number'] != 138 or row['state'] != 'reported' or _decimal(row['cost']) != 0
                or row['input_hash'] != grant['document_batches'][0]
                or _hash([body, 'document']) != row['input_hash'] or not evidence.get('id')
                or evidence.get('model') not in {EMBEDDING.model, EMBEDDING.model.removesuffix(':free')}
                or evidence.get('provider') not in {None, EMBEDDING.provider, EMBEDDING.provider_name}
                or any(store.cached_vector(t, spec, query=False) is None for t in texts)):
            raise SemanticError('search_recovery_incomplete')
        proof = {'unknown_number': 137, 'repeat_number': 138, 'input_hash': row['input_hash'],
                 'cached_text_hashes': [_hash(t) for t in texts], 'spec': spec.fingerprint,
                 'original_status': 'uncertain', 'original_cost': None}
        with self.db:
            self.db.execute('INSERT INTO search_budget_meta VALUES (?,?)',
                            (PREFIX + 'repeat_complete', json.dumps(proof)))
        return proof

    def summary(self):
        result = super().summary()
        result['historical_halted'] = result['halted']
        result['supplemental_complete'] = bool(self._value(PREFIX + 'repeat_complete'))
        result['total_cost_finalized'] = False
        try:
            grant = self._grant()
            newer = result['receipts'][grant['baseline']:]
            halt = self._value(PREFIX + 'halt')
            if halt:
                result['halted'] = json.loads(halt)['code']
            elif result['supplemental_complete'] and all(r['state'] in {'reported', 'not_sent'} for r in newer):
                result['halted'] = None
        except SemanticError:
            pass
        return result
