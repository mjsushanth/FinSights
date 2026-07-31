"""
S3 Vectors index creation for FinRAG.

Creates the vector bucket and index that embedding_generation.py's downstream S3 Vectors
bulk-insertion step (s3vectors_bulk_insertion.py) and the retrieval path
(rag_pipeline/s3_retriever.py) both assume already exist. Neither of those modules creates
these resources -- s3vectors_bulk_insertion.py's _validate_index_configuration() only
validates an existing index.

Idempotent: safe to run multiple times. Mirrors the exists-check / force-recreate pattern
used in data_preparation.py's _initialize_meta_table() / _initialize_vectors_table().

Investigation scope (2026-07-28): creates the bucket + index only. Does NOT insert any
vectors and does NOT build the Stage 3 join table -- see EMBEDDINGS_VECTORS_REVIVAL_PLAN.md
for why that's deferred.
"""
import sys
from pathlib import Path


def _find_model_pipeline_root() -> Path:
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        if parent.name == "ModelPipeline":
            return parent
    raise RuntimeError(f"Cannot find ModelPipeline root directory.\n  Searched from: {current}")


MODEL_PIPELINE_ROOT = _find_model_pipeline_root()
sys.path.insert(0, str(MODEL_PIPELINE_ROOT))

from finrag_ml_tg1.loaders.ml_config_loader import MLConfig
from botocore.exceptions import ClientError

# Non-filterable metadata keys for the eventual Stage 3 schema
# (finrag_embeddings_s3vectors_cohere_1024d.parquet): embedding_id (audit/lineage),
# section_sentence_count (not useful as a search filter), sentenceID (human-readable
# identifier kept alongside the mmh3 surrogate used as the vector's actual insertion key).
# Everything else (cik_int, report_year, section_name, sic, sentence_pos) is filterable by
# default -- S3 Vectors only requires declaring the NON-filterable keys up front; they can
# never be converted to filterable later, so this list must be right before creation.
NON_FILTERABLE_METADATA_KEYS = ["embedding_id", "section_sentence_count", "sentenceID"]


def _vector_bucket_exists(client, bucket_name: str) -> bool:
    try:
        client.get_vector_bucket(vectorBucketName=bucket_name)
        return True
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "NotFoundException":
            return False
        raise


def _index_exists(client, bucket_name: str, index_name: str) -> bool:
    try:
        client.get_index(vectorBucketName=bucket_name, indexName=index_name)
        return True
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "NotFoundException":
            return False
        raise


def create_vector_bucket_and_index(force_recreate: bool = False) -> dict:
    """
    Create the S3 Vectors bucket + index used by this project, reading names/dimension
    from ml_config.yaml (retrieval.*) via MLConfig -- never hardcode them here (this is
    exactly the P1 bug already found in s3vectors_bulk_insertion.py: hardcoded names that
    only matched config by coincidence).

    force_recreate: if True, deletes and recreates an existing INDEX only. The vector
        bucket itself is never deleted by this function.

    Returns a status dict. Does NOT insert any vectors.
    """
    config = MLConfig()
    retrieval = config.get_retrieval_config()
    bucket_name = retrieval["vector_bucket"]
    index_name = retrieval["index_name"]
    dimension = retrieval["dimensions"]

    client = config.get_s3vectors_client()
    status = {"bucket": bucket_name, "index": index_name, "dimension": dimension}

    print(f"\n[S3 Vectors Bucket] {bucket_name}")
    if _vector_bucket_exists(client, bucket_name):
        print("  Already exists.")
        status["bucket_created"] = False
    else:
        client.create_vector_bucket(vectorBucketName=bucket_name)
        print("  Created.")
        status["bucket_created"] = True

    print(f"\n[S3 Vectors Index] {index_name}")
    index_exists = _index_exists(client, bucket_name, index_name)

    if index_exists and force_recreate:
        print("  Exists -- force_recreate=True, deleting first.")
        client.delete_index(vectorBucketName=bucket_name, indexName=index_name)
        index_exists = False

    if index_exists:
        print("  Already exists. Set force_recreate=True to recreate.")
        status["index_created"] = False
    else:
        client.create_index(
            vectorBucketName=bucket_name,
            indexName=index_name,
            dataType="float32",
            dimension=dimension,
            distanceMetric="cosine",
            metadataConfiguration={"nonFilterableMetadataKeys": NON_FILTERABLE_METADATA_KEYS},
        )
        print("  Created.")
        print(f"  dataType=float32, dimension={dimension}, distanceMetric=cosine")
        print(f"  non-filterable metadata keys: {NON_FILTERABLE_METADATA_KEYS}")
        status["index_created"] = True

    detail = client.get_index(vectorBucketName=bucket_name, indexName=index_name)
    status["index_detail"] = detail.get("index", detail)
    return status


if __name__ == "__main__":
    result = create_vector_bucket_and_index()
    print("\n" + "=" * 70)
    print("RESULT:")
    for k, v in result.items():
        print(f"  {k}: {v}")
