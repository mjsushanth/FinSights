"""
LLM client for AWS Bedrock with streaming support and token tracking.
"""
import json
import time
import boto3
import botocore.config
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from config.settings import aws_config, pricing_config


@dataclass
class LLMResponse:
    """Container for LLM response with metadata"""
    content: str
    input_tokens: int
    output_tokens: int
    latency_seconds: float
    cost_usd: float
    model_id: str
    
    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class BedrockLLMClient:
    """
    AWS Bedrock client for Claude models with comprehensive tracking.
    """
    
    def __init__(
        self,
        region: str = None,
        model_id: str = None,
        temperature: float = None,
        max_tokens: int = None
    ):
        """
        Initialize Bedrock client.
        
        Args:
            region: AWS region (defaults to config)
            model_id: Model identifier (defaults to config)
            temperature: Sampling temperature (defaults to config)
            max_tokens: Max output tokens (defaults to config)
        """
        self.region = region or aws_config.REGION
        self.model_id = model_id or aws_config.MODEL_ID
        self.temperature = temperature if temperature is not None else aws_config.TEMPERATURE
        self.max_tokens = max_tokens or aws_config.MAX_TOKENS
        
        # Create Bedrock client with retry configuration
        config = botocore.config.Config(
            retries={
                "max_attempts": aws_config.MAX_RETRIES,
                "mode": aws_config.RETRY_MODE
            },
            read_timeout=120,  # Increase read timeout
            connect_timeout=10
        )
        
        self.client = boto3.client(
            "bedrock-runtime",
            region_name=self.region,
            config=config
        )
        
        print(f"✅ LLM Client initialized: {self.model_id}")
    
    def generate(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> LLMResponse:
        """
        Generate response from Claude.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            system_prompt: Optional system prompt
            temperature: Override default temperature
            max_tokens: Override default max tokens
            
        Returns:
            LLMResponse object
        """
        start_time = time.time()
        
        # Build request payload
        payload = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": temperature if temperature is not None else self.temperature,
            "messages": messages
        }
        
        if system_prompt:
            payload["system"] = system_prompt
        
        # Make API call
        try:
            response = self.client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(payload)
            )
            
            # Parse response
            response_body = json.loads(response["body"].read())
            
            end_time = time.time()
            latency = end_time - start_time
            
            # Extract token usage
            usage = response_body.get("usage", {})
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            
            # Calculate cost
            cost = pricing_config.calculate_cost(input_tokens, output_tokens)
            
            # Extract content - FIX: Only get text blocks, don't concatenate duplicates
            content = ""
            if "content" in response_body:
                content_blocks = []
                for block in response_body["content"]:
                    if block.get("type") == "text":
                        text = block.get("text", "")
                        if text:  # Only add non-empty text
                            content_blocks.append(text)
                
                # Join with newlines if multiple blocks, but typically just one
                content = "\n\n".join(content_blocks)
            
            return LLMResponse(
                content=content,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_seconds=round(latency, 2),
                cost_usd=cost,
                model_id=self.model_id
            )
            
        except Exception as e:
            print(f"❌ LLM Error: {e}")
            raise
    
    def generate_with_prompt(
        self,
        user_message: str,
        system_prompt: Optional[str] = None
    ) -> LLMResponse:
        """
        Convenience method for single-turn generation.
        
        Args:
            user_message: User's input
            system_prompt: Optional system prompt
            
        Returns:
            LLMResponse object
        """
        messages = [{"role": "user", "content": user_message}]
        return self.generate(messages, system_prompt)
    
    def test_connection(self) -> bool:
        """
        Test Bedrock connection with a simple query.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            response = self.generate_with_prompt("Say 'OK'")
            print(f"✅ Bedrock Connection Test: {response.content}")
            return True
        except Exception as e:
            print(f"❌ Bedrock Connection Failed: {e}")
            return False


def create_llm_client(**kwargs) -> BedrockLLMClient:
    """
    Factory function to create LLM client.
    
    Args:
        **kwargs: Optional overrides for client configuration
        
    Returns:
        BedrockLLMClient instance
    """
    return BedrockLLMClient(**kwargs)