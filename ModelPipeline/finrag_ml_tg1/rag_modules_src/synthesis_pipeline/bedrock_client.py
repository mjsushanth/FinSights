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
            analytical_results: Output from metric pipeline (can be None)
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
                     analytical_results: Optional[Dict],
                     rag_context: List[Dict]) -> str:
        """
        Construct the prompt for Claude.
        
        Args:
            user_query: User's question
            analytical_results: Structured financial data
            rag_context: Text chunks from SEC filings
            
        Returns:
            Formatted prompt string
        """
        prompt_parts = []
        
        # System context
        prompt_parts.append(
            "You are a financial analysis assistant. You have access to both "
            "structured financial data and contextual information from SEC filings. "
            "Provide accurate, comprehensive answers based on this information.\n"
        )
        
        # Add analytical data if available
        if analytical_results and analytical_results.get('data'):
            prompt_parts.append("=== STRUCTURED FINANCIAL DATA ===")
            prompt_parts.append(json.dumps(analytical_results, indent=2))
            prompt_parts.append("")
        
        # Add RAG context
        if rag_context:
            prompt_parts.append("=== CONTEXT FROM SEC FILINGS ===")
            for i, chunk in enumerate(rag_context[:5], 1):
                prompt_parts.append(f"\n[Context {i}]")
                prompt_parts.append(f"Company: {chunk.get('company', 'Unknown')}")
                prompt_parts.append(f"Year: {chunk.get('year', 'Unknown')}")
                prompt_parts.append(f"Section: {chunk.get('section', 'Unknown')}")
                prompt_parts.append(f"Text: {chunk.get('text', '')[:500]}...")
            prompt_parts.append("")
        
        # User query
        prompt_parts.append("=== USER QUESTION ===")
        prompt_parts.append(user_query)
        prompt_parts.append("")
        prompt_parts.append(
            "Please provide a comprehensive answer based on the structured data "
            "and context provided above. If the data conflicts, explain the discrepancy. "
            "If information is missing, acknowledge what you don't know."
        )
        
        return "\n".join(prompt_parts)