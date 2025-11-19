"""
Metadata filter construction for S3 Vectors queries.

Converts EntityExtractionResult (from entity_adapter) into S3 Vectors filter JSON
according to the filtered/global retrieval strategy.

Strategy:
- Filtered call: Strong constraints (company, year, section)
- Global call: Relaxed time constraints, keep company if available

-------------------------------------------------------------------------------------
!! -- READ: Output Schema
# Filtered call result:
{
    "cik_int": {"$eq": 1045810}  or  {"$in": [1045810, 320193, 789019]},
    "report_year": {"$eq": 2021}  or  {"$in": [2020, 2021, 2022]},
    "section_name": {"$eq": "ITEM_7"}  or  {"$in": ["ITEM_7", "ITEM_1A"]}
}

# Global call result:
{
    "cik_int": {"$eq": 1045810}  or  {"$in": [1045810, 320193]},
    "report_year": {"$gte": 2015}
}

# Edge case - no entities:
None

-------------------------------------------------------------------------------------
Single value: {"$eq": value}
Multiple values: {"$in": [val1, val2, ...]}
Range: {"$gte": threshold}
Missing filters: Key omitted entirely
No filters at all: Returns None
-------------------------------------------------------------------------------------
"""

from typing import Dict, Any, Optional, List

from finrag_ml_tg1.loaders.ml_config_loader import MLConfig
from finrag_ml_tg1.rag_modules_src.entity_adapter.entity_adapter import EntityExtractionResult


class MetadataFilterBuilder:
    """
    Builds S3 Vectors metadata filter JSONs from extracted entities.
    
    Implements the filtered vs global retrieval strategy:
    - If companies exist: filtered uses all constraints, global relaxes years
    - If no companies: filtered uses year/section, global uses recent years only
    
    Usage:
        builder = MetadataFilterBuilder(config)
        
        filtered_filters = builder.build_filters(entities)
        global_filters = builder.build_global_filters(entities)
    """
    
    def __init__(self, config: MLConfig):
        """
        Initialize filter builder from MLConfig.
        
        Args:
            config: MLConfig instance (extracts recent_year_threshold from retrieval config)
        """
        retrieval_cfg = config.get_retrieval_config()
        self.recent_year_threshold = retrieval_cfg.get('recent_year_threshold', 2015)
    
    def build_filters(
        self, 
        entities: EntityExtractionResult,
        force_no_filters: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Build FILTERED retrieval filters (strong constraints).
        
        Returns S3 Vectors filter dict with proper $and wrapping when multiple conditions exist.
        
        Args:
            entities: Extracted entities from EntityAdapter
            force_no_filters: If True, return None (open retrieval)
        
        Returns:
            S3 Vectors filter dict or None
        """
        if force_no_filters:
            return None
        
        conditions = []  # Build list of conditions, then wrap in $and if needed
        
        # ─────────────────────────────────────────────────────────────────────
        # COMPANY FILTER
        # ─────────────────────────────────────────────────────────────────────
        if entities.companies and entities.companies.ciks_int:
            ciks = list(entities.companies.ciks_int)
            if len(ciks) == 1:
                conditions.append({"cik_int": {"$eq": ciks[0]}})
            else:
                conditions.append({"cik_int": {"$in": ciks}})
        
        # ─────────────────────────────────────────────────────────────────────
        # YEAR FILTER
        # ─────────────────────────────────────────────────────────────────────
        if entities.years and entities.years.past_years:
            years = sorted(entities.years.past_years)
            if len(years) == 1:
                conditions.append({"report_year": {"$eq": years[0]}})
            else:
                conditions.append({"report_year": {"$in": years}})
        elif entities.years and entities.years.years:
            years = sorted(entities.years.years)
            if len(years) == 1:
                conditions.append({"report_year": {"$eq": years[0]}})
            else:
                conditions.append({"report_year": {"$in": years}})
        
        # ─────────────────────────────────────────────────────────────────────
        # SECTION FILTER - Use $or for multiple sections
        # ─────────────────────────────────────────────────────────────────────
        if entities.sections:
            sections = self._extract_section_list(entities)
            if sections:
                if len(sections) == 1:
                    # Single section - simple equality
                    conditions.append({"section_name": {"$eq": sections[0]}})
                else:
                    # Multiple sections - use $or (proven to work in Notebook 5)
                    section_conditions = [
                        {"section_name": {"$eq": sec}} for sec in sections
                    ]
                    conditions.append({"$or": section_conditions})
        
        # ─────────────────────────────────────────────────────────────────────
        # WRAP IN $and IF MULTIPLE CONDITIONS
        # ─────────────────────────────────────────────────────────────────────
        if not conditions:
            return None
        elif len(conditions) == 1:
            # Single condition - no wrapper needed
            return conditions[0]
        else:
            # Multiple conditions - wrap in $and
            return {"$and": conditions}
    
    def build_global_filters(
        self, 
        entities: EntityExtractionResult
    ) -> Optional[Dict[str, Any]]:
        """
        Build GLOBAL retrieval filters (relaxed time constraints).
        
        Returns S3 Vectors filter dict with proper $and wrapping.
        
        Args:
            entities: Extracted entities from EntityAdapter
        
        Returns:
            S3 Vectors filter dict or None
        """
        conditions = []
        
        # ─────────────────────────────────────────────────────────────────────
        # COMPANY FILTER (keep if available)
        # ─────────────────────────────────────────────────────────────────────
        if entities.companies and entities.companies.ciks_int:
            ciks = list(entities.companies.ciks_int)
            if len(ciks) == 1:
                conditions.append({"cik_int": {"$eq": ciks[0]}})
            else:
                conditions.append({"cik_int": {"$in": ciks}})
        
        # ─────────────────────────────────────────────────────────────────────
        # YEAR FILTER (always add - use threshold for "recent")
        # ─────────────────────────────────────────────────────────────────────
        # CRITICAL FIX: Ensure recent_year_threshold is an int, not MLConfig object
        conditions.append({"report_year": {"$gte": self.recent_year_threshold}})
        
        # ─────────────────────────────────────────────────────────────────────
        # WRAP IN $and IF MULTIPLE CONDITIONS
        # ─────────────────────────────────────────────────────────────────────
        if not conditions:
            return None
        elif len(conditions) == 1:
            return conditions[0]
        else:
            return {"$and": conditions}
    
    def _extract_section_list(self, entities: EntityExtractionResult) -> List[str]:
        """
        Extract clean section list from entities.
        
        Handles both old dict format and new dataclass format from entity_adapter.
        
        Args:
            entities: Extracted entities from EntityAdapter
        
        Returns:
            List of SEC section strings (e.g., ["ITEM_7", "ITEM_1A"])
        """
        sections = []
        
        # Handle sections object (could be dict or dataclass)
        if hasattr(entities.sections, 'items'):
            # Dataclass with .items attribute
            sections = list(entities.sections.items) if entities.sections.items else []
        elif isinstance(entities.sections, dict):
            # Dict format
            sections = entities.sections.get('items', [])
        elif isinstance(entities.sections, list):
            # Already a list
            sections = entities.sections
        
        # Add primary section if specified
        if hasattr(entities.sections, 'primary') and entities.sections.primary:
            primary = entities.sections.primary
            if primary and primary not in sections:
                sections.append(primary)
        elif isinstance(entities.sections, dict) and entities.sections.get('primary'):
            primary = entities.sections['primary']
            if primary not in sections:
                sections.append(primary)
        
        return sections
    
    def explain_filters(
        self, 
        filtered: Optional[Dict], 
        global_: Optional[Dict]
    ) -> str:
        """
        Generate human-readable explanation of filter strategy.
        
        Useful for debugging and validation.
        
        Args:
            filtered: Filtered call filters
            global_: Global call filters
        
        Returns:
            Multi-line string explaining filter behavior
        """
        lines = ["Filter Strategy:"]
        lines.append(f"  Recent year threshold: {self.recent_year_threshold}")
        lines.append("")
        
        lines.append("Filtered Call:")
        if filtered:
            for key, val in filtered.items():
                lines.append(f"  {key}: {val}")
        else:
            lines.append("  (no filters - open retrieval)")
        lines.append("")
        
        lines.append("Global Call:")
        if global_:
            for key, val in global_.items():
                lines.append(f"  {key}: {val}")
        else:
            lines.append("  (no filters - truly global)")
        
        return "\n".join(lines)