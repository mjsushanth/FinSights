# ModelPipeline\finrag_ml_tg1\rag_modules_src\synthesis_pipeline\bedrock_client.py

import boto3
import json
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class BedrockClient:
    """Handles interaction with AWS Bedrock Claude API."""
    
    def __init__(self, region: str, model_id: str, 
                 max_tokens: int = 4096, temperature: float = 0.7):
        """
        Initialize Bedrock client.
        
        Args:
            region: AWS region
            model_id: Bedrock model identifier
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
        """
        self.client = boto3.client('bedrock-runtime', region_name=region)
        self.model_id = model_id
        self.max_tokens = max_tokens
        self.temperature = temperature
        logger.info(f"Initialized Bedrock client with model: {model_id}")
    
    def generate_response(self, 
                         user_query: str,
                         analytical_results: Optional[Dict],
                         rag_context: List[Dict]) -> str:
        """
        Generate final response using analytical data and RAG context.
        
        Args:
            user_query: Original user question
            analytical_results: Compact output from metric pipeline (can be None)
            rag_context: Relevant chunks from vector search
            
        Returns:
            Generated response text
        """
        prompt = self._build_prompt(user_query, analytical_results, rag_context)
        
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }
        
        try:
            response = self.client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(body)
            )
            
            response_body = json.loads(response['body'].read())
            answer = response_body['content'][0]['text']
            
            logger.info("Generated response from Bedrock")
            return answer
        
        except Exception as e:
            logger.error(f"Error calling Bedrock: {str(e)}")
            raise
    
    def _build_prompt(self, 
                 user_query: str,
                 analytical_results: Optional[str],
                 rag_context: List[Dict]) -> str:
        """
        Construct the prompt for Claude - PURE STRING FORMAT.
        
        Args:
            user_query: User's question
            analytical_results: Ultra-compact string format
            rag_context: Text chunks from SEC filings
            
        Returns:
            Formatted prompt string (token-optimized)
        """
        prompt_parts = []
        
        # System context (minimal)
        prompt_parts.append(
            "Financial assistant with KPI data and SEC excerpts. Answer accurately.\n"
        )
        
        # Add analytical data if available (PURE STRING)
        if analytical_results:
            prompt_parts.append("FINANCIALS:")
            prompt_parts.append(analytical_results)
            prompt_parts.append("")
        
        # Add RAG context (COMPACT)
        if rag_context:
            prompt_parts.append("CONTEXT:")
            for i, chunk in enumerate(rag_context, 1):
                co = chunk.get('company', '?')
                yr = chunk.get('year', '?')
                sec = chunk.get('section', '?').replace('ITEM_', '')
                text = chunk.get('text', '')[:350]
                
                prompt_parts.append(f"[{i}] {co} {yr} {sec}: {text}")
            prompt_parts.append("")
        
        # User query
        prompt_parts.append("Q: " + user_query)
        prompt_parts.append("A:")
        
        final_prompt = "\n".join(prompt_parts)
        
        # Log token estimate
        token_estimate = len(final_prompt) // 4
        logger.info(f"Prompt: ~{token_estimate} tokens")
        
        return final_prompt
    
    def _format_value_compact(self, value: float) -> str:
        """
        Format financial values ultra-compactly.
        
        Args:
            value: Raw financial value
            
        Returns:
            Compact string representation (e.g., "$27.0B", "$3.5M", "$1.2K")
        """
        if abs(value) >= 1_000_000_000:
            return f"${value/1_000_000_000:.1f}B"
        elif abs(value) >= 1_000_000:
            return f"${value/1_000_000:.1f}M"
        elif abs(value) >= 1_000:
            return f"${value/1_000:.0f}K"
        else:
            return f"${value:.0f}"