-- 011: Record which embedding model produced the stored vectors.
--
-- Why: cosine similarity is only meaningful when the query vector and the
-- stored vectors come from the same model. Changing BEDROCK_EMBEDDING_MODEL
-- without re-ingesting produces plausible-looking scores that are unrelated to
-- the question. Recording the model turns that silent failure into one query:
--
--   SELECT DISTINCT embedding_model FROM policy_documents;
--
-- search_policy_documents refuses to search when this disagrees with the
-- configured model, so a mismatch surfaces instead of degrading quietly.
--
-- No BEGIN/COMMIT: the Data API runner owns the transaction.

ALTER TABLE policy_documents ADD COLUMN IF NOT EXISTS embedding_model text;

COMMENT ON COLUMN policy_documents.embedding_model IS
  'Model id that produced this document''s vectors. Must match
   BEDROCK_EMBEDDING_MODEL at query time or retrieval is meaningless.';
