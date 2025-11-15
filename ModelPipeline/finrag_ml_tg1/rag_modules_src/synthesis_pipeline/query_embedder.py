import boto3
import json
from typing import List
import logging

logger = logging.getLogger(__name__)


class QueryEmbedder:
    """Handles conversion of user queries to embeddings using Cohere via AWS Bedrock."""
    
    def __init__(self, region: str = "us-east-1", 
                 model_id: str = "cohere.embed-v4:0"):
        """
        Initialize Bedrock client for Cohere embeddings.
        
        Args:
            region: AWS region
            model_id: Cohere embedding model ID in Bedrock
        """
        self.client = boto3.client('bedrock-runtime', region_name=region)
        self.model_id = model_id
        logger.info(f"Initialized QueryEmbedder with Bedrock model: {model_id}")
    
    def embed_query(self, query: str, input_type: str = "search_query") -> List[float]:
        """
        Convert a single query to embedding vector via Bedrock.
        
        Args:
            query: User question text
            input_type: Type of input - "search_query" or "search_document"
            
        Returns:
            List of floats representing the embedding vector
        """
        try:
            body = json.dumps({
                "texts": [query],
                "input_type": input_type,
                "truncate": "END"
            })
            
            response = self.client.invoke_model(
                modelId=self.model_id,
                contentType="application/json",
                accept="application/json",
                body=body
            )
            
            # Parse response
            response_body = json.loads(response['body'].read())
            
            # Debug: Log the response structure
            logger.debug(f"Response body keys: {response_body.keys()}")
            logger.debug(f"Response body: {response_body}")
            
            # Check for errors in response
            if 'message' in response_body:
                logger.error(f"Bedrock API error: {response_body.get('message')}")
                raise Exception(f"Bedrock API error: {response_body.get('message')}")
            
            # Cohere embed v4 API response format
            if 'embeddings' not in response_body:
                logger.error(f"Unexpected response format: {response_body}")
                raise Exception(f"Missing 'embeddings' key in response. Got: {list(response_body.keys())}")
            
            embeddings = response_body['embeddings']
            
            # Handle different response formats
            # v4 format: {"embeddings": {"float": [[...]]}} or {"embeddings": [[...]]}
            # v3 format: {"embeddings": [[...]]}
            
            if isinstance(embeddings, dict):
                # v4 format with typed embeddings
                if 'float' in embeddings:
                    embeddings_list = embeddings['float']
                else:
                    logger.error(f"Unknown embeddings dict format: {embeddings.keys()}")
                    raise Exception(f"Unknown embeddings format. Keys: {list(embeddings.keys())}")
            elif isinstance(embeddings, list):
                # v3 format or direct list
                embeddings_list = embeddings
            else:
                logger.error(f"Invalid embeddings type: {type(embeddings)}")
                raise Exception(f"Invalid embeddings format received")
            
            # Check if embeddings_list has content
            if not isinstance(embeddings_list, list) or len(embeddings_list) == 0:
                logger.error(f"Empty embeddings list")
                raise Exception(f"Empty embeddings received")
            
            embedding = embeddings_list[0]
            
            logger.info(f"Generated embedding for query: '{query[:50]}...' (dimension: {len(embedding)})")
            return embedding
        
        except KeyError as e:
            logger.error(f"KeyError in response parsing: {e}")
            logger.error(f"Response body structure: {response_body if 'response_body' in locals() else 'Not available'}")
            raise
        except Exception as e:
            logger.error(f"Error generating embedding via Bedrock: {str(e)}")
            raise
    
    def embed_batch(self, queries: List[str], 
               input_type: str = "search_query") -> List[List[float]]:
        """
        Convert multiple queries to embeddings via Bedrock.
        
        Args:
            queries: List of query strings (max 96)
            input_type: Type of input
            
        Returns:
            List of embedding vectors
        """
        try:
            if len(queries) > 96:
                logger.warning(f"Batch size {len(queries)} exceeds limit. Processing in chunks.")
                return self._embed_large_batch(queries, input_type)
            
            body = json.dumps({
                "texts": queries,
                "input_type": input_type,
                "truncate": "END"
            })
            
            response = self.client.invoke_model(
                modelId=self.model_id,
                contentType="application/json",
                accept="application/json",
                body=body
            )
            
            response_body = json.loads(response['body'].read())
            
            if 'embeddings' not in response_body:
                logger.error(f"Missing 'embeddings' key. Response: {response_body}")
                raise Exception(f"Invalid response format")
            
            embeddings = response_body['embeddings']
            
            # Handle v4 format
            if isinstance(embeddings, dict):
                if 'float' in embeddings:
                    embeddings_list = embeddings['float']
                else:
                    raise Exception(f"Unknown embeddings format. Keys: {list(embeddings.keys())}")
            else:
                embeddings_list = embeddings
            
            logger.info(f"Generated embeddings for {len(queries)} queries")
            return embeddings_list
        
        except Exception as e:
            logger.error(f"Error generating batch embeddings via Bedrock: {str(e)}")
            raise
    
    def _embed_large_batch(self, queries: List[str], 
                          input_type: str) -> List[List[float]]:
        """Handle batches larger than 96 texts."""
        all_embeddings = []
        chunk_size = 96
        
        for i in range(0, len(queries), chunk_size):
            chunk = queries[i:i + chunk_size]
            embeddings = self.embed_batch(chunk, input_type)
            all_embeddings.extend(embeddings)
            logger.info(f"Processed chunk {i//chunk_size + 1}")
        
        return all_embeddings