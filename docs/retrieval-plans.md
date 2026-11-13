# Retrieval query plans

`make explain-retrieval MATTER=<uuid> COPIES=150` runs `EXPLAIN (ANALYZE, BUFFERS)` on the exact
SQL the app uses (`retrieval_v3.lexical_sql`, `semantic_sql`, `challenge_sql`) against a scratch
matter holding 150 copies of the demo matter: 600 documents, 3,000 spans, 3,000 embeddings per
profile. Recorded at commit `14439d9`, PostgreSQL 16.15 in Docker on an Apple M5. The scratch
matter is deleted afterwards.

## Finding

| Query | Right after bulk insert (stale statistics) | After `ANALYZE` |
| --- | --- | --- |
| Lexical (`ts_rank_cd`, GIN) | 42.6 ms | 3.6 ms |
| Semantic (exact pgvector `<=>`, 384-d) | **481.9 ms** | **1.9 ms** |
| Counterevidence (anchors + challenge regex) | 29.6 ms | 4.8 ms |

With fresh rows the planner believed every table held about one matching row and chose nested
loops. For the semantic query it scanned ~1,500 embedding rows through
`ix_source_embeddings_matter` once per span (3,000 times) instead of hashing. After `ANALYZE`
all three queries use hash joins.

**Change made:** the worker (and the demo seed) runs `ANALYZE` on the evidence tables after each
publish (`evidence_versions.refresh_planner_statistics`). Autovacuum would fix this on its own
after a delay, but a bulk upload followed by an immediate investigation lands inside that delay.

**Not changed:** no ANN index (HNSW/IVFFlat). Exact search over 3,000 vectors takes 1.9 ms with
correct statistics, so an approximate index would add recall risk without a measured need.

## Full plans (3,000 spans)


### before ANALYZE (fresh rows, stale planner statistics)

#### lexical

```
Limit  (cost=14.07..14.08 rows=1 width=20) (actual time=42.605..42.607 rows=24 loops=1)
  Buffers: shared hit=13459
  ->  Sort  (cost=14.07..14.08 rows=1 width=20) (actual time=42.604..42.605 rows=24 loops=1)
        Sort Key: (ts_rank_cd(s.search, '''invoic'' | ''7a'' | ''approv'' | ''uncondit'' | ''march'' | ''18'''::tsquery)) DESC, s.id
        Sort Method: top-N heapsort  Memory: 27kB
        Buffers: shared hit=13459
        ->  Nested Loop  (cost=0.54..14.06 rows=1 width=20) (actual time=0.066..42.514 rows=1504 loops=1)
              Join Filter: (s.extraction_version_id = m.extraction_version_id)
              Rows Removed by Join Filter: 441380
              Buffers: shared hit=13456
              ->  Index Scan using ix_source_spans_extraction on source_spans s  (cost=0.28..8.01 rows=1 width=218) (actual time=0.004..0.648 rows=1504 loops=1)
                    Index Cond: (matter_id = '1609e1fe-90d4-4b9b-8dce-418c4c924128'::uuid)
                    Filter: (search @@ '''invoic'' | ''7a'' | ''approv'' | ''uncondit'' | ''march'' | ''18'''::tsquery)
                    Rows Removed by Filter: 1496
                    Buffers: shared hit=604
              ->  Index Scan using corpus_snapshot_members_pkey on corpus_snapshot_members m  (cost=0.27..6.04 rows=1 width=32) (actual time=0.001..0.017 rows=294 loops=1504)
                    Index Cond: (snapshot_id = '3acb27d5-05f6-4a76-b1ed-490616ea8cea'::uuid)
                    Filter: (matter_id = '1609e1fe-90d4-4b9b-8dce-418c4c924128'::uuid)
                    Buffers: shared hit=12852
Planning:
  Buffers: shared hit=32
Planning Time: 0.078 ms
Execution Time: 42.612 ms
```

#### semantic (hash-v1 vectors, exact <=>)

```
Limit  (cost=22.10..22.11 rows=1 width=32) (actual time=481.872..481.874 rows=24 loops=1)
  Buffers: shared hit=937496
  ->  Sort  (cost=22.10..22.11 rows=1 width=32) (actual time=481.872..481.873 rows=24 loops=1)
        Sort Key: ((e.embedding <=> '[0,0,-0.2581989,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,-0.2581989,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,-0.2581989,0,-0.2581989,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.2581989,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,-0.2581989,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,-0.2581989,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,-0.2581989,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,-0.2581989,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.2581989,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.2581989,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,-0.2581989,0,0,0,0,0.2581989,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.2581989,0,0,0,0,0,0.2581989,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]'::vector)), s.id
        Sort Method: top-N heapsort  Memory: 27kB
        Buffers: shared hit=937496
        ->  Nested Loop  (cost=0.82..22.09 rows=1 width=32) (actual time=0.338..481.658 rows=3000 loops=1)
              Join Filter: (s.extraction_version_id = m.extraction_version_id)
              Rows Removed by Join Filter: 899467
              Buffers: shared hit=937493
              ->  Nested Loop  (cost=0.55..16.04 rows=1 width=1592) (actual time=0.335..396.684 rows=3000 loops=1)
                    Join Filter: (s.id = e.source_span_id)
                    Rows Removed by Join Filter: 4498500
                    Buffers: shared hit=911477
                    ->  Index Scan using ix_source_spans_extraction on source_spans s  (cost=0.28..8.01 rows=1 width=48) (actual time=0.002..0.472 rows=3000 loops=1)
                          Index Cond: (matter_id = '1609e1fe-90d4-4b9b-8dce-418c4c924128'::uuid)
                          Buffers: shared hit=604
                    ->  Index Scan using ix_source_embeddings_matter on source_embeddings e  (cost=0.28..8.01 rows=1 width=1576) (actual time=0.001..0.086 rows=1500 loops=3000)
                          Index Cond: ((matter_id = '1609e1fe-90d4-4b9b-8dce-418c4c924128'::uuid) AND (embedding_profile_id = 'hash-v1'::text))
                          Buffers: shared hit=910873
              ->  Index Scan using corpus_snapshot_members_pkey on corpus_snapshot_members m  (cost=0.27..6.04 rows=1 width=32) (actual time=0.001..0.019 rows=301 loops=3000)
                    Index Cond: (snapshot_id = '3acb27d5-05f6-4a76-b1ed-490616ea8cea'::uuid)
                    Filter: (matter_id = '1609e1fe-90d4-4b9b-8dce-418c4c924128'::uuid)
                    Buffers: shared hit=26016
Planning:
  Buffers: shared hit=33
Planning Time: 0.093 ms
Execution Time: 481.912 ms
```

#### counterevidence challenge

```
Limit  (cost=14.08..14.08 rows=1 width=20) (actual time=29.548..29.549 rows=12 loops=1)
  Buffers: shared hit=8272
  ->  Sort  (cost=14.08..14.08 rows=1 width=20) (actual time=29.548..29.548 rows=12 loops=1)
        Sort Key: (ts_rank_cd(s.search, '''7a'' | ''invoic'''::tsquery)) DESC, s.id
        Sort Method: top-N heapsort  Memory: 26kB
        Buffers: shared hit=8272
        ->  Nested Loop  (cost=0.54..14.07 rows=1 width=20) (actual time=0.009..29.490 rows=900 loops=1)
              Join Filter: (s.extraction_version_id = m.extraction_version_id)
              Rows Removed by Join Filter: 263087
              Buffers: shared hit=8272
              ->  Index Scan using ix_source_spans_extraction on source_spans s  (cost=0.28..8.02 rows=1 width=218) (actual time=0.006..4.222 rows=900 loops=1)
                    Index Cond: (matter_id = '1609e1fe-90d4-4b9b-8dce-418c4c924128'::uuid)
                    Filter: ((search @@ '''7a'' | ''invoic'''::tsquery) AND (text ~* '\m(but|cancel|cancelled|cannot|condition|conditional|conditions|corrected|correction|denied|deny|dispute|disputed|except|exception|held|hold|however|instead|late|missing|never|no|not|notwithstanding|only|pending|provided|reject|rejected|rescind|revised|revoke|revoked|subject|unable|unless|unpaid|until|withdraw|withdrawn)\M'::text))
                    Rows Removed by Filter: 2100
                    Buffers: shared hit=604
              ->  Index Scan using corpus_snapshot_members_pkey on corpus_snapshot_members m  (cost=0.27..6.04 rows=1 width=32) (actual time=0.001..0.018 rows=293 loops=900)
                    Index Cond: (snapshot_id = '3acb27d5-05f6-4a76-b1ed-490616ea8cea'::uuid)
                    Filter: (matter_id = '1609e1fe-90d4-4b9b-8dce-418c4c924128'::uuid)
                    Buffers: shared hit=7668
Planning:
  Buffers: shared hit=9
Planning Time: 0.356 ms
Execution Time: 29.555 ms
```

### after ANALYZE

#### lexical

```
Limit  (cost=293.86..293.92 rows=24 width=20) (actual time=3.603..3.605 rows=24 loops=1)
  Buffers: shared hit=160
  ->  Sort  (cost=293.86..299.28 rows=2166 width=20) (actual time=3.603..3.604 rows=24 loops=1)
        Sort Key: (ts_rank_cd(s.search, '''invoic'' | ''7a'' | ''approv'' | ''uncondit'' | ''march'' | ''18'''::tsquery)) DESC, s.id
        Sort Method: top-N heapsort  Memory: 27kB
        Buffers: shared hit=160
        ->  Hash Join  (cost=23.52..233.38 rows=2166 width=20) (actual time=0.078..3.529 rows=1504 loops=1)
              Hash Cond: (s.extraction_version_id = m.extraction_version_id)
              Buffers: shared hit=160
              ->  Seq Scan on source_spans s  (cost=0.00..198.48 rows=2255 width=159) (actual time=0.010..0.444 rows=1504 loops=1)
                    Filter: ((id <> ALL ('{}'::uuid[])) AND (search @@ '''invoic'' | ''7a'' | ''approv'' | ''uncondit'' | ''march'' | ''18'''::tsquery) AND (matter_id = '1609e1fe-90d4-4b9b-8dce-418c4c924128'::uuid))
                    Rows Removed by Filter: 1528
                    Buffers: shared hit=153
              ->  Hash  (cost=16.12..16.12 rows=592 width=32) (actual time=0.064..0.064 rows=600 loops=1)
                    Buckets: 1024  Batches: 1  Memory Usage: 46kB
                    Buffers: shared hit=7
                    ->  Seq Scan on corpus_snapshot_members m  (cost=0.00..16.12 rows=592 width=32) (actual time=0.001..0.033 rows=600 loops=1)
                          Filter: ((matter_id = '1609e1fe-90d4-4b9b-8dce-418c4c924128'::uuid) AND (snapshot_id = '3acb27d5-05f6-4a76-b1ed-490616ea8cea'::uuid))
                          Rows Removed by Filter: 8
                          Buffers: shared hit=7
Planning:
  Buffers: shared hit=89
Planning Time: 0.137 ms
Execution Time: 3.612 ms
```

#### semantic (hash-v1 vectors, exact <=>)

```
Limit  (cost=1059.57..1059.63 rows=24 width=32) (actual time=1.860..1.863 rows=24 loops=1)
  Buffers: shared hit=805
  ->  Sort  (cost=1059.57..1066.70 rows=2852 width=32) (actual time=1.860..1.861 rows=24 loops=1)
        Sort Key: ((e.embedding <=> '[0,0,-0.2581989,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,-0.2581989,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,-0.2581989,0,-0.2581989,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.2581989,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,-0.2581989,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,-0.2581989,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,-0.2581989,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,-0.2581989,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.2581989,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.2581989,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,-0.2581989,0,0,0,0,0.2581989,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.2581989,0,0,0,0,0,0.2581989,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]'::vector)), s.id
        Sort Method: top-N heapsort  Memory: 28kB
        Buffers: shared hit=805
        ->  Hash Join  (cost=251.92..979.92 rows=2852 width=32) (actual time=0.418..1.720 rows=3000 loops=1)
              Hash Cond: (s.extraction_version_id = m.extraction_version_id)
              Buffers: shared hit=805
              ->  Hash Join  (cost=228.40..927.16 rows=2969 width=1592) (actual time=0.355..0.926 rows=3000 loops=1)
                    Hash Cond: (e.source_span_id = s.id)
                    Buffers: shared hit=798
                    ->  Seq Scan on source_embeddings e  (cost=0.00..690.96 rows=2969 width=1576) (actual time=0.020..0.328 rows=3000 loops=1)
                          Filter: ((matter_id = '1609e1fe-90d4-4b9b-8dce-418c4c924128'::uuid) AND (embedding_profile_id = 'hash-v1'::text))
                          Rows Removed by Filter: 64
                          Buffers: shared hit=645
                    ->  Hash  (cost=190.90..190.90 rows=3000 width=48) (actual time=0.334..0.334 rows=3000 loops=1)
                          Buckets: 4096  Batches: 1  Memory Usage: 267kB
                          Buffers: shared hit=153
                          ->  Seq Scan on source_spans s  (cost=0.00..190.90 rows=3000 width=48) (actual time=0.003..0.187 rows=3000 loops=1)
                                Filter: ((id <> ALL ('{}'::uuid[])) AND (matter_id = '1609e1fe-90d4-4b9b-8dce-418c4c924128'::uuid))
                                Rows Removed by Filter: 32
                                Buffers: shared hit=153
              ->  Hash  (cost=16.12..16.12 rows=592 width=32) (actual time=0.060..0.061 rows=600 loops=1)
                    Buckets: 1024  Batches: 1  Memory Usage: 46kB
                    Buffers: shared hit=7
                    ->  Seq Scan on corpus_snapshot_members m  (cost=0.00..16.12 rows=592 width=32) (actual time=0.001..0.033 rows=600 loops=1)
                          Filter: ((matter_id = '1609e1fe-90d4-4b9b-8dce-418c4c924128'::uuid) AND (snapshot_id = '3acb27d5-05f6-4a76-b1ed-490616ea8cea'::uuid))
                          Rows Removed by Filter: 8
                          Buffers: shared hit=7
Planning:
  Buffers: shared hit=59
Planning Time: 0.132 ms
Execution Time: 1.871 ms
```

#### counterevidence challenge

```
Limit  (cost=253.92..253.95 rows=12 width=20) (actual time=4.771..4.772 rows=12 loops=1)
  Buffers: shared hit=160
  ->  Sort  (cost=253.92..256.08 rows=864 width=20) (actual time=4.771..4.771 rows=12 loops=1)
        Sort Key: (ts_rank_cd(s.search, '''7a'' | ''invoic'''::tsquery)) DESC, s.id
        Sort Method: top-N heapsort  Memory: 26kB
        Buffers: shared hit=160
        ->  Hash Join  (cost=23.52..234.11 rows=864 width=20) (actual time=0.135..4.721 rows=900 loops=1)
              Hash Cond: (s.extraction_version_id = m.extraction_version_id)
              Buffers: shared hit=160
              ->  Seq Scan on source_spans s  (cost=0.00..206.06 rows=899 width=159) (actual time=0.073..4.037 rows=900 loops=1)
                    Filter: ((id <> ALL ('{}'::uuid[])) AND (search @@ '''7a'' | ''invoic'''::tsquery) AND (text ~* '\m(but|cancel|cancelled|cannot|condition|conditional|conditions|corrected|correction|denied|deny|dispute|disputed|except|exception|held|hold|however|instead|late|missing|never|no|not|notwithstanding|only|pending|provided|reject|rejected|rescind|revised|revoke|revoked|subject|unable|unless|unpaid|until|withdraw|withdrawn)\M'::text) AND (matter_id = '1609e1fe-90d4-4b9b-8dce-418c4c924128'::uuid))
                    Rows Removed by Filter: 2132
                    Buffers: shared hit=153
              ->  Hash  (cost=16.12..16.12 rows=592 width=32) (actual time=0.060..0.060 rows=600 loops=1)
                    Buckets: 1024  Batches: 1  Memory Usage: 46kB
                    Buffers: shared hit=7
                    ->  Seq Scan on corpus_snapshot_members m  (cost=0.00..16.12 rows=592 width=32) (actual time=0.001..0.033 rows=600 loops=1)
                          Filter: ((matter_id = '1609e1fe-90d4-4b9b-8dce-418c4c924128'::uuid) AND (snapshot_id = '3acb27d5-05f6-4a76-b1ed-490616ea8cea'::uuid))
                          Rows Removed by Filter: 8
                          Buffers: shared hit=7
Planning:
  Buffers: shared hit=14
Planning Time: 0.338 ms
Execution Time: 4.777 ms
```

