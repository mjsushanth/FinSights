"""
Semantic query variant generator using cheap LLM (Haiku).

Generates alternative phrasings of user queries to improve retrieval recall
without changing the semantic intent or entities.

! WHAT SHOULD HAPPEN:
    Query → VariantGenerator → ["query1", "query2", "query3"]
    ↓
    Each variant → EntityAdapter.extract() → EntityExtractionResult
    ↓
    Each variant + entities → QueryEmbedderV2.embed_query() → embedding
    ↓
    [base_embedding] + [variant1_emb, variant2_emb, variant3_emb] → S3Retriever

"""

from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


class VariantGenerator:
    """
    Generates semantic variants of queries using AWS Bedrock Claude Haiku.
    
    Uses a simple prompt to rephrase queries while preserving:
    - Company names
    - Years/time periods
    - Section references
    - Core intent
    
    Usage:
        generator = VariantGenerator(config, bedrock_client)
        variants = generator.generate(query="What was NVIDIA's revenue in 2021?")
        # Returns: ["How much revenue did NVIDIA report in 2021?", ...]
    """
    
    def __init__(self, variant_config: dict, bedrock_client):
        """
        Initialize variant generator.
        
        Args:
            variant_config: Dict from ml_config.yaml['semantic_variants']
            bedrock_client: boto3 bedrock-runtime client
        """
        self.enabled = variant_config.get("enabled", False)
        self.model_id = variant_config.get("model_id", "anthropic.claude-3-haiku-20240307-v1:0")
        self.max_tokens = variant_config.get("max_tokens", 150)
        self.temperature = variant_config.get("temperature", 0.7)
        self.count = variant_config.get("count", 3)
        self.prompt_template = variant_config.get("prompt_template", "")
        
        self.bedrock_client = bedrock_client
        
        logger.info(f"VariantGenerator initialized (enabled={self.enabled}, model={self.model_id})")
    
    def generate(self, query: str) -> List[str]:
        """
        Generate semantic variants of the query.
        
        Args:
            query: Original user query
        
        Returns:
            List of variant queries (empty list if disabled or generation fails)
        """
        if not self.enabled:
            logger.debug("Variant generation disabled, returning empty list")
            return []
        
        if not query or len(query.strip()) < 10:
            logger.warning("Query too short for variant generation")
            return []
        
        try:
            # Build prompt
            prompt = self.prompt_template.format(query=query, count=self.count)
            
            # Call Bedrock
            response = self._call_bedrock(prompt)
            
            # Parse variants (one per line)
            variants = self._parse_variants(response)
            
            logger.info(f"Generated {len(variants)} variants for query")
            return variants
        
        except Exception as e:
            logger.error(f"Variant generation failed: {e}")
            return []  # Graceful degradation - continue without variants
    
    def _call_bedrock(self, prompt: str) -> str:
        """
        Call Bedrock Claude Haiku with the variant prompt.
        
        Args:
            prompt: Formatted prompt string
        
        Returns:
            Raw LLM response text
        """
        import json
        
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        })
        
        response = self.bedrock_client.invoke_model(
            modelId=self.model_id,
            body=body
        )
        
        response_body = json.loads(response['body'].read())
        return response_body['content'][0]['text']
    
    def _parse_variants(self, response: str) -> List[str]:
        """
        Parse LLM response into clean variant list.
        
        Expects one variant per line. Filters out:
        - Empty lines
        - Lines with numbering (1., 2., etc.)
        - Very short lines (<10 chars)
        
        Args:
            response: Raw LLM response
        
        Returns:
            List of cleaned variant strings
        """
        lines = response.strip().split('\n')
        variants = []
        
        for line in lines:
            # Clean up line
            line = line.strip()
            
            # Remove leading numbering (1., 2., etc.)
            if line and line[0].isdigit() and '.' in line[:3]:
                line = line.split('.', 1)[1].strip()
            
            # Keep if valid
            if line and len(line) >= 10 and line not in variants:
                variants.append(line)
        
        # Limit to requested count
        return variants[:self.count]