"""
================================================================================================
# Model Contracts for Synthesis Pipeline
================================================================================================

QueryResponse
├── query: str
├── answer: str
├── context: str
└── metadata: ResponseMetadata
    ├── llm: LLMMetadata
    │   ├── model_id
    │   ├── input_tokens
    │   ├── output_tokens
    │   ├── total_tokens
    │   ├── cost
    │   └── stop_reason
    ├── context: ContextMetadata
    │   ├── kpi_included
    │   ├── rag_included
    │   ├── context_length
    │   ├── kpi_entities (optional)
    │   ├── rag_entities (optional)
    │   └── retrieval_stats (optional)
    ├── timestamp
    └── processing_time_ms (optional)

ErrorResponse
├── query: str
├── error: str
├── error_type: str
├── stage: str
├── timestamp: str
├── answer: None
├── context: None
└── metadata: None


================================================================================================

## Field Sweep - Data Flow Analysis for Notes:


Field: model_id
Data Source: MLConfig → passed to BedrockClient constructor

Example Data Flow:
```
MLConfig.get_default_serving_model()['model_id']
  → BedrockClient.__init__(model_id=...)
  → BedrockClient.invoke() returns {'model_id': self.model_id}
  → Orchestrator extracts it
  → LLMMetadata(model_id=llm_response['model_id'])
```

Field: input_tokens, output_tokens? 
    Data Source: AWS Bedrock API Response (response_body['usage']['input_tokens'])

Field: cost
    Calculated using rates from MLConfig
    Populated By: BedrockClient._calculate_cost() potentially !

    
==============================================================================================

{
    'timestamp': str,           # ISO 8601
    'query': str,               # User question
    'model_id': str,            # Which model was used
    'input_tokens': int,        # From AWS
    'output_tokens': int,       # From AWS
    'total_tokens': int,        # Sum
    'cost': float,              # USD
    'context_length': int,      # Characters
    'processing_time_ms': float,# Optional
    'error': str,               # None if success, error message if failed
    'error_type': str,          # None if success, exception type if failed
    'stage': str,               # None if success, failure stage if failed
    'context_file': str,        # Filename of saved context
    'response_file': str        # Filename of saved response (optional)
}


==============================================================================================
# Orchestrator just wires components:

config = MLConfig()                          # Config service
rag_components = init_rag_components(...)    # Supply lines
prompt_loader = PromptLoader()               # Prompt system
llm_client = create_bedrock_client(...)      # Bedrock API
query_logger = QueryLogger()                 # Logging system


# Then just passes data through pipeline:

context, meta = build_combined_context(...)  # Supply lines work
system = prompt_loader.load_system_prompt()  # Prompt loader work
user = prompt_loader.format_query_template(...)
llm_response = llm_client.invoke(...)        # Bedrock work
response = create_success_response(...)      # Factory work
result = response.to_dict()                  # Model work
exports = query_logger.log_query(...)        # Logger work


==============================================================================================


synthesis_pipeline/main.py  (Entry Point - Orchestrates Everything)
         ↓
    orchestrator.py  (Wiring Layer)
         ↓
    ┌────┴────┬────────┬────────┬────────┐
    ↓         ↓        ↓        ↓        ↓
entity_   metric_  rag_    prompts/  utilities/
adapter/  pipeline/ pipeline/



==============================================================================================

         ┌─────────────────────────────────────┐
         │   synthesis_pipeline/main.py        │  Entry Point (User Interface)
         │   (CLI, REST API, Streamlit)        │
         └──────────────┬──────────────────────┘
                        ↓
         ┌──────────────────────────────────────┐
         │      orchestrator.py                 │  Application Layer
         │      (Business Logic)                │
         └──────┬───────┬──────┬───────┬────────┘
                ↓       ↓      ↓       ↓
         ┌──────┴───────────────────────────────┐
         │  Domain Layer (Core Logic)           │
         │  - entity_adapter/                   │
         │  - metric_pipeline/                  │
         │  - rag_pipeline/                     │
         │  - prompts/                          │
         └──────────────────────────────────────┘

"""