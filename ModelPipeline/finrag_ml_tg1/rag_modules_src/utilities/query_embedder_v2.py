
import json
import logging
from dataclasses import dataclass
from typing import List, Optional

import boto3

logger = logging.getLogger(__name__)


# ------------------------------------------
# Exceptions
# ------------------------------------------

class QueryTooLongError(Exception):
    pass

class QueryTooShortError(Exception):
    pass

class QueryOutOfScopeError(Exception):
    pass

class EmbeddingProviderError(Exception):
    pass

class EmbeddingResponseFormatError(Exception):
    pass


# ------------------------------------------
# Embedding Runtime Config
# ------------------------------------------

@dataclass
class EmbeddingRuntimeConfig:
    provider: str             # "bedrock"
    region: str
    model_id: str
    dimensions: int
    input_type: str
    max_query_chars: int = 3000

    @classmethod
    def from_ml_config(cls, embedding_cfg_dict: dict):
        """
        embedding_cfg_dict -> embedding.bedrock config tree from ml_config.yaml
        """
        provider = embedding_cfg_dict.get("default_provider")

        if provider != "bedrock":
            raise ValueError("Only Bedrock provider is supported in V2.")

        bedrock_cfg = embedding_cfg_dict["bedrock"]
        region = bedrock_cfg["region"]

        default_model_key = bedrock_cfg["default_model"]
        model_cfg = bedrock_cfg["models"][default_model_key]

        return cls(
            provider=provider,
            region=region,
            model_id=model_cfg["model_id"],
            dimensions=model_cfg["dimensions"],
            input_type=model_cfg["input_type"],
        )


# ------------------------------------------
# QueryEmbedderV2
# ------------------------------------------

class QueryEmbedderV2:
    """
    Config-driven query embedder.
    Implements:
      - guardrails
      - Bedrock invocation
      - v3/v4 Cohere response parsing
    """

    ## boto3 is using its default credential chain: might fail. pass a boto_client explicitly
    ## Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN, etc.)
    ## ModelPipeline\finrag_ml_tg1\.aws_secrets\aws_credentials.env

    def __init__(self, cfg: EmbeddingRuntimeConfig, boto_client=None):
        self.cfg = cfg
        self.client = boto_client or boto3.client(
            "bedrock-runtime",
            region_name=cfg.region
        )
        logger.info(
            f"[QueryEmbedderV2] Initialized with model={cfg.model_id}, "
            f"region={cfg.region}, dim={cfg.dimensions}"
        )

    # --------------------------------------
    # Guardrails
    # --------------------------------------

    def validate_query(self, query: str):
        """Hard block oversized queries."""
        if len(query) > self.cfg.max_query_chars:
            raise QueryTooLongError(
                f"Query has {len(query)} characters; "
                f"limit is {self.cfg.max_query_chars}."
            )


    # --------------------------------------
    # Guardrails
    # --------------------------------------

    def _entities_empty(self, entities) -> bool:
        """
        Determine if EntityExtractionResult is 'empty' in the sense of:
          - no companies
          - no years
          - no metrics
          - no sections
          - no risk_topics
        Works whether nested objects are dataclasses or simple dicts.
        """
        # Companies
        companies = getattr(entities, "companies", None)
        has_companies = False
        if companies is not None:
            if isinstance(companies, dict):
                has_companies = bool(companies.get("ciks_int") or companies.get("tickers"))
            else:
                has_companies = bool(
                    getattr(companies, "ciks_int", []) or
                    getattr(companies, "tickers", [])
                )

        # Years
        years = getattr(entities, "years", None)
        has_years = False
        if years is not None:
            if isinstance(years, dict):
                has_years = bool(years.get("years"))
            else:
                has_years = bool(getattr(years, "years", []))

        # Metrics
        metrics = getattr(entities, "metrics", None)
        has_metrics = False
        if metrics is not None:
            if isinstance(metrics, dict):
                has_metrics = bool(metrics.get("metrics"))
            else:
                has_metrics = bool(getattr(metrics, "metrics", []))

        # Sections
        sections = getattr(entities, "sections", None)
        has_sections = False
        if sections is not None:
            if isinstance(sections, dict):
                has_sections = bool(sections.get("items") or sections.get("primary"))
            else:
                has_sections = bool(
                    getattr(sections, "items", []) or
                    getattr(sections, "primary", None)
                )

        # Risk topics
        risk_topics = getattr(entities, "risk_topics", [])
        if isinstance(risk_topics, dict):
            has_risks = bool(risk_topics.get("topics"))
        else:
            has_risks = bool(risk_topics)

        return not (has_companies or has_years or has_metrics or has_sections or has_risks)


    def validate_scope(self, query: str, entities) -> None:
        """
        Entities is EntityExtractionResult.
        If everything is empty AND query extremely short → block.
        Otherwise, if everything is empty → out-of-scope.
        """
        is_empty = self._entities_empty(entities)

        if len(query.strip()) < 4 and is_empty:
            raise QueryTooShortError("Query too short and no entities detected.")

        if is_empty:
            # Semantic out-of-domain
            raise QueryOutOfScopeError(
                "Query does not reference any financial/SEC concepts."
            )


    # --------------------------------------
    # Public: embed single query
    # --------------------------------------

    def embed_query(self, query: str, entities) -> List[float]:
        """
        entities: EntityExtractionResult (already computed upstream)
        """
        self.validate_query(query)
        self.validate_scope(query, entities)

        # Invoke model
        raw = self._invoke_bedrock_raw(query)
        embedding = self._parse_bedrock_response(raw)

        if len(embedding) != self.cfg.dimensions:
            raise EmbeddingResponseFormatError(
                f"Embedding dim mismatch. Expected {self.cfg.dimensions}, "
                f"got {len(embedding)}."
            )

        return embedding

    # --------------------------------------
    # Bedrock invocation
    # --------------------------------------

    def _invoke_bedrock_raw(self, query: str) -> dict:
        """Send a single-query embedding request to Bedrock (v4-style)."""
        body = json.dumps({
            "texts": [query],
            "input_type": self.cfg.input_type,   # e.g. "search_document" or "search_query"
            "embedding_types": ["float"],
            "output_dimension": self.cfg.dimensions,  # <<< enforce 1024-d like ingestion
            "max_tokens": 128000,
            "truncate": "RIGHT",
        })

        try:
            resp = self.client.invoke_model(
                modelId=self.cfg.model_id,
                contentType="application/json",
                accept="application/json",
                body=body,
            )
            return json.loads(resp["body"].read())
        except Exception as ex:
            raise EmbeddingProviderError(f"Bedrock invoke failed: {ex}")


    # --------------------------------------
    # Response parsing for v3/v4
    # --------------------------------------

    def _parse_bedrock_response(self, body: dict) -> List[float]:
        """
        Handles:
          - v4: {"embeddings": {"float": [[...]]}}
          - v3: {"embeddings": [[...]]}
        """
        if "embeddings" not in body:
            raise EmbeddingResponseFormatError(
                f"Missing 'embeddings' in response. Keys={list(body.keys())}"
            )

        emb = body["embeddings"]

        # v4 typed
        if isinstance(emb, dict):
            if "float" in emb:
                list_2d = emb["float"]
            else:
                raise EmbeddingResponseFormatError(
                    f"Unknown embeddings dict format. Keys={list(emb.keys())}"
                )
        # v3 or simple list
        elif isinstance(emb, list):
            list_2d = emb
        else:
            raise EmbeddingResponseFormatError(
                f"Invalid embeddings type: {type(emb)}"
            )

        if not list_2d or not isinstance(list_2d[0], list):
            raise EmbeddingResponseFormatError(
                "Embeddings list is empty or malformed."
            )

        return list_2d[0]


