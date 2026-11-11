-- 010: Provenance columns so the loaded corpus revision is checkable.
--
-- source_sha is a hash of a document's extracted text. Comparing it against the
-- local file answers "are this document's vectors current?" without re-reading
-- the corpus. That is what makes certification per-document rather than
-- per-corpus: after editing 3 of 200 policies, you validate 3.
--
-- ingested_at records when the row was last refreshed.
--
-- No BEGIN/COMMIT: the Data API runner owns the transaction.

ALTER TABLE policy_documents ADD COLUMN IF NOT EXISTS source_sha text;
ALTER TABLE policy_documents ADD COLUMN IF NOT EXISTS ingested_at timestamptz;
ALTER TABLE policy_chunks    ADD COLUMN IF NOT EXISTS ingested_at timestamptz;

COMMENT ON COLUMN policy_documents.source_sha IS
  'Hash of the extracted document text. Mismatch means re-ingest this document.';
COMMENT ON COLUMN policy_chunks.chunk_id IS
  'sha256(document_id|section_id|chunk_index). Identity from location, so an
   edited section overwrites its row instead of orphaning it.';
