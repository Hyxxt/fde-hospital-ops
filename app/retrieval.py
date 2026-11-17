import json
import math
import os
import re
from collections import Counter
from pathlib import Path

import numpy as np
import onnxruntime as ort
from psycopg.rows import dict_row
from tokenizers import Tokenizer

HERE = Path(__file__).resolve().parent
KNOWLEDGE = json.loads((HERE / "knowledge.json").read_text("utf-8"))
EVAL_CASES = json.loads((HERE / "eval_cases.json").read_text("utf-8"))
QUERY_PREFIX = "为这个句子生成表示以用于检索相关文章："


class Embedder:
    def __init__(self):
        directory = Path(os.getenv("MODEL_DIR", "models"))
        self.tokenizer = Tokenizer.from_file(str(directory / "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=256)
        self.tokenizer.enable_padding()
        options = ort.SessionOptions()
        options.intra_op_num_threads = int(os.getenv("ORT_THREADS", "2"))
        options.inter_op_num_threads = 1
        options.enable_cpu_mem_arena = False
        self.model = ort.InferenceSession(
            str(directory / "model.onnx"), options, providers=["CPUExecutionProvider"]
        )

    def encode(self, texts):
        tokens = self.tokenizer.encode_batch(texts)
        values = {
            "input_ids": [token.ids for token in tokens],
            "attention_mask": [token.attention_mask for token in tokens],
            "token_type_ids": [token.type_ids for token in tokens],
        }
        inputs = {
            field.name: np.asarray(values[field.name], dtype=np.int64)
            for field in self.model.get_inputs()
        }
        vectors = self.model.run(None, inputs)[0][:, 0, :]
        return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


def vector_literal(vector):
    return "[" + ",".join(str(float(value)) for value in vector) + "]"


def seed(pool, embedder):
    with pool.connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(904368153)")
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS hospital_clauses (
                id text PRIMARY KEY, topic text NOT NULL, title text NOT NULL,
                scope text NOT NULL CHECK (scope IN ('staff','ops')),
                body text NOT NULL, embedding vector(512) NOT NULL
            )
        """)
        for clause in KNOWLEDGE:
            current = conn.execute(
                "SELECT topic, title, scope, body FROM hospital_clauses WHERE id = %s",
                (clause["id"],),
            ).fetchone()
            fields = tuple(clause[key] for key in ("topic", "title", "scope", "text"))
            if current == fields:
                continue
            vector = embedder.encode([f'{clause["title"]}。{clause["text"]}'])[0]
            conn.execute("""
                INSERT INTO hospital_clauses (id, topic, title, scope, body, embedding)
                VALUES (%s, %s, %s, %s, %s, %s::vector)
                ON CONFLICT (id) DO UPDATE SET topic = EXCLUDED.topic,
                  title = EXCLUDED.title, scope = EXCLUDED.scope,
                  body = EXCLUDED.body, embedding = EXCLUDED.embedding
            """, (clause["id"], *fields, vector_literal(vector)))
        ids = [clause["id"] for clause in KNOWLEDGE]
        conn.execute("DELETE FROM hospital_clauses WHERE NOT id = ANY(%s)", (ids,))
        conn.execute("""
            CREATE INDEX IF NOT EXISTS hospital_clauses_embedding_hnsw
            ON hospital_clauses USING hnsw (embedding vector_cosine_ops)
        """)


def terms(value):
    for token in re.findall(r"[\u3400-\u9fff]+|[a-z0-9]+", value.lower()):
        if len(token) > 1 and "\u3400" <= token[0] <= "\u9fff":
            yield from (token[index:index + 2] for index in range(len(token) - 1))
        else:
            yield token


def bm25(query, clauses):
    query_terms = set(terms(query))
    counts = [Counter(terms(f'{row["title"]} {row["body"]}')) for row in clauses]
    if not counts:
        return []
    sizes = [sum(count.values()) for count in counts]
    frequencies = Counter(token for count in counts for token in count)
    average_size = sum(sizes) / len(sizes)
    scores = []
    for row, count, size in zip(clauses, counts, sizes):
        normalizer = 1.5 * (0.25 + 0.75 * size / average_size)
        score = sum(
            math.log1p((len(clauses) - frequencies[term] + 0.5)
                       / (frequencies[term] + 0.5))
            * count[term] * 2.5 / (count[term] + normalizer)
            for term in query_terms if count[term]
        )
        if score > 0:
            scores.append((row["id"], score))
    return [item[0] for item in sorted(scores, key=lambda item: (-item[1], item[0]))]


def rank(pool, embedder, query, operations=False):
    vector = vector_literal(embedder.encode([QUERY_PREFIX + query])[0])
    scopes = ["staff", "ops"] if operations else ["staff"]
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cursor:
        rows = cursor.execute("""
            SELECT id, topic, title, body, 1 - (embedding <=> %(vector)s::vector) AS cosine
            FROM hospital_clauses
            WHERE scope = ANY(%(scopes)s)
            ORDER BY embedding <=> %(vector)s::vector
            LIMIT 32
        """, {"vector": vector, "scopes": scopes}).fetchall()
    dense = [row["id"] for row in rows]
    lexical = bm25(query, rows)
    fusion = Counter()
    for weight, ordering in ((0.72, dense), (0.28, lexical)):
        for index, clause_id in enumerate(ordering, start=1):
            fusion[clause_id] += weight / (6 + index)
    combined = sorted(dense, key=lambda key: -fusion[key])
    return {row["id"]: row for row in rows}, {
        "bm25": lexical, "vector": dense, "hybrid": combined
    }
