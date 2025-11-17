"""
Response generation orchestrator combining retrieval and LLM.
"""
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from config.prompts import PromptTemplates
from generation.llm_client import BedrockLLMClient, LLMResponse
from retrieval.kpi_retrieval import kpi_retriever, KPIResult
from retrieval.vector_search import vector_search, SearchResults
from retrieval.trend_calculator import trend_calculator, TrendResult
from retrieval.entity_extractor import entity_extractor, ExtractedEntities


@dataclass
class QueryContext:
    """Context assembled from various retrieval sources"""
    entities: ExtractedEntities
    kpi_data: List[str] = None
    trend_data: List[str] = None
    narrative_data: List[str] = None
    
    def __post_init__(self):
        """Initialize empty lists"""
        if self.kpi_data is None:
            self.kpi_data = []
        if self.trend_data is None:
            self.trend_data = []
        if self.narrative_data is None:
            self.narrative_data = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for prompt building"""
        return {
            "entities": self.entities.to_dict(),
            "kpi_data": self.kpi_data,
            "trend_data": self.trend_data,
            "narrative_data": self.narrative_data
        }
    
    def has_content(self) -> bool:
        """Check if any context was retrieved"""
        return bool(self.kpi_data or self.trend_data or self.narrative_data)


class ResponseBuilder:
    """
    Orchestrates retrieval and response generation with unified context.
    """
    
    def __init__(self, llm_client: BedrockLLMClient):
        """
        Initialize response builder.
        
        Args:
            llm_client: Initialized LLM client
        """
        self.llm_client = llm_client
        self.prompt_templates = PromptTemplates()
    
    def generate_response(
        self,
        query: str,
        ticker: str = None,
        metrics: Optional[List[str]] = None
    ) -> tuple[str, QueryContext, LLMResponse]:
        """
        Main method to generate response with retrieval.
        All queries receive both KPI and narrative context.
        
        Args:
            query: User's question
            ticker: Optional ticker override
            metrics: Optional specific metrics to retrieve
            
        Returns:
            Tuple of (response_text, context_used, llm_response_metadata)
        """
        print(f"\n🔍 Extracting entities and retrieving context...")
        
        # Extract entities from query
        entities = entity_extractor.extract(query)
        
        # Override ticker if provided
        if ticker:
            entities.ticker = ticker
        
        # Override metrics if provided
        if metrics:
            entities.metrics = metrics
        
        print(f"   Ticker: {entities.ticker}")
        print(f"   Metrics: {entities.metrics if entities.metrics else 'Auto-detected'}")
        print(f"   Years: {entities.years if entities.years else 'All available'}")
        
        # Assemble context with both KPI and narrative data
        context = self._assemble_unified_context(query, entities)
        
        if not context.has_content():
            print("⚠️ No relevant context found")
        
        # Build prompts with unified system prompt
        system_prompt = self.prompt_templates.get_system_prompt()
        user_prompt = self._build_unified_prompt(query, context)
        
        print(f"💬 Generating response with {self.llm_client.model_id}...")
        
        # Generate response
        llm_response = self.llm_client.generate_with_prompt(
            user_message=user_prompt,
            system_prompt=system_prompt
        )
        
        print(f"✅ Response generated:")
        print(f"   Tokens: {llm_response.input_tokens} in / {llm_response.output_tokens} out")
        print(f"   Latency: {llm_response.latency_seconds}s")
        print(f"   Cost: ${llm_response.cost_usd}")
        
        return llm_response.content, context, llm_response
    
    def _assemble_unified_context(
        self,
        query: str,
        entities: ExtractedEntities
    ) -> QueryContext:
        """
        Assemble unified context with both KPI and narrative data for all queries.
        
        Args:
            query: User's question
            entities: Extracted entities
            
        Returns:
            QueryContext with all retrieved data
        """
        context = QueryContext(entities=entities)
        
        # Always retrieve KPI data
        context.kpi_data = self._retrieve_kpis(entities)
        
        # Always retrieve narrative context
        context.narrative_data = self._retrieve_narrative(query, entities.ticker)
        
        # Retrieve trends if relevant
        if entities.comparison_terms or entities.year_range or len(entities.years) > 1:
            context.trend_data = self._retrieve_trends(entities)
        
        return context
    
    def _retrieve_kpis(self, entities: ExtractedEntities) -> List[str]:
        """
        Retrieve KPI data based on extracted entities.
        
        Args:
            entities: Extracted entities
            
        Returns:
            List of formatted KPI strings
        """
        ticker = entities.ticker or "NVDA"
        metrics = entities.metrics
        
        # If no specific metrics extracted, get common financial metrics
        if not metrics:
            metrics = self._get_default_metrics(ticker)
        
        if not metrics:
            return []
        
        # Retrieve data
        year = entities.years[0] if len(entities.years) == 1 else None
        year_range = entities.year_range
        
        kpi_results = []
        for metric in metrics:
            if year_range:
                result = kpi_retriever.get_kpi(
                    ticker, metric, year_range=year_range
                )
            else:
                result = kpi_retriever.get_kpi(ticker, metric, year=year)
            
            if result.found:
                kpi_results.append(result)
        
        return kpi_retriever.format_as_context(kpi_results)
    
    def _retrieve_trends(self, entities: ExtractedEntities) -> List[str]:
        """
        Calculate trend data based on extracted entities.
        
        Args:
            entities: Extracted entities
            
        Returns:
            List of formatted trend strings
        """
        ticker = entities.ticker or "NVDA"
        metrics = entities.metrics
        
        if not metrics:
            metrics = self._get_default_metrics(ticker)
        
        if not metrics:
            return []
        
        # Calculate trends
        start_year = None
        end_year = None
        
        if entities.year_range:
            start_year, end_year = entities.year_range
        elif len(entities.years) > 1:
            start_year = min(entities.years)
            end_year = max(entities.years)
        
        trends = trend_calculator.calculate_multiple_trends(
            ticker, metrics, start_year, end_year
        )
        
        return trend_calculator.format_as_context(trends)
    
    def _retrieve_narrative(self, query: str, ticker: str) -> List[str]:
        """
        Retrieve narrative context via semantic search.
        
        Args:
            query: User's question
            ticker: Ticker symbol
            
        Returns:
            List of formatted narrative strings
        """
        return vector_search.search_with_context(
            query=query,
            top_k=5,  # Increased from 3 to get more context
            ticker=ticker or "NVDA"
        )
    
    def _get_default_metrics(self, ticker: str) -> List[str]:
        """
        Get default metrics when none are extracted.
        Returns common financial metrics.
        
        Args:
            ticker: Ticker symbol
            
        Returns:
            List of metric names
        """
        # Common metrics to retrieve by default
        common_metrics = [
            "income_stmt_Revenue",
            "income_stmt_Net Income",
            "income_stmt_Gross Profit",
            "Gross Profit Margin %",
            "balance_sheet_Total Assets",
            "balance_sheet_Stockholders Equity",
            "cash_flow_Operating Cash Flow"
        ]
        
        # Find which of these exist in the data
        available = []
        for metric in common_metrics:
            result = kpi_retriever.get_kpi(ticker, metric)
            if result.found:
                available.append(metric)
                if len(available) >= 3:  # Limit to top 3
                    break
        
        return available
    
    def _build_unified_prompt(self, query: str, context: QueryContext) -> str:
        """
        Build unified user prompt with all context.
        
        Args:
            query: User's question
            context: Retrieved context
            
        Returns:
            Formatted prompt string
        """
        prompt_parts = [f"Question: {query}\n"]
        
        # Add KPI data if available
        if context.kpi_data:
            prompt_parts.append("\n=== Available Financial Data (KPIs) ===")
            for kpi in context.kpi_data:
                prompt_parts.append(f"{kpi}")
        
        # Add trend data if available
        if context.trend_data:
            prompt_parts.append("\n=== Trend Analysis ===")
            for trend in context.trend_data:
                prompt_parts.append(f"{trend}")
        
        # Add narrative context if available
        if context.narrative_data:
            prompt_parts.append("\n=== Relevant Information from SEC Filings ===")
            for i, passage in enumerate(context.narrative_data, 1):
                prompt_parts.append(f"{i}. {passage}")
        
        prompt_parts.append("\n=== Your Response ===")
        
        return "\n".join(prompt_parts)