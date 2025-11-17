"""
Gold dataset management for evaluation.
"""
import json
from typing import List, Dict, Any, Optional
from pathlib import Path
from dataclasses import dataclass, asdict

from config.settings import data_paths


@dataclass
class GoldTestCase:
    """Single test case from gold dataset"""
    query: str
    ticker: str
    ground_truth: Optional[str] = None
    expected_facts: Optional[List[str]] = None
    metrics_involved: Optional[List[str]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)


class GoldDatasetManager:
    """
    Manages gold standard test cases for evaluation.
    """
    
    def __init__(self, dataset_path: Path = None):
        """
        Initialize dataset manager.
        
        Args:
            dataset_path: Path to gold dataset JSON file
        """
        self.dataset_path = dataset_path or data_paths.GOLD_DATASET
        self.test_cases: List[GoldTestCase] = []
        
        if self.dataset_path.exists():
            self.load()
    
    def load(self) -> List[GoldTestCase]:
        """
        Load gold dataset from file.
        
        Returns:
            List of GoldTestCase objects
        """
        with open(self.dataset_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        self.test_cases = [
            GoldTestCase(**case) for case in data
        ]
        
        print(f"✅ Loaded {len(self.test_cases)} test cases from {self.dataset_path}")
        return self.test_cases
    
    def save(self):
        """Save current test cases to file"""
        # Ensure directory exists
        self.dataset_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = [case.to_dict() for case in self.test_cases]
        
        with open(self.dataset_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Saved {len(self.test_cases)} test cases to {self.dataset_path}")
    
    def add_test_case(self, test_case: GoldTestCase):
        """
        Add a new test case to the dataset.
        
        Args:
            test_case: GoldTestCase to add
        """
        self.test_cases.append(test_case)
    
    def get_by_ticker(self, ticker: str) -> List[GoldTestCase]:
        """
        Get test cases filtered by ticker.
        
        Args:
            ticker: Ticker symbol
            
        Returns:
            List of matching test cases
        """
        return [
            case for case in self.test_cases
            if case.ticker == ticker
        ]
    
    def create_sample_dataset(self):
        """
        Create a sample gold dataset for NVDA.
        Useful for initial setup.
        """
        sample_cases = [
            # Simple KPI queries
            GoldTestCase(
                query="What was NVDA's revenue in 2023?",
                ticker="NVDA",
                expected_facts=["2023", "revenue"],
                metrics_involved=["income_stmt_Revenue"]
            ),
            GoldTestCase(
                query="Show me NVDA's profit margins from 2020 to 2023",
                ticker="NVDA",
                expected_facts=["profit margin", "2020", "2023"],
                metrics_involved=["Gross Profit Margin %"]
            ),
            GoldTestCase(
                query="What was Nvidia's net income in 2022?",
                ticker="NVDA",
                expected_facts=["2022", "net income"],
                metrics_involved=["income_stmt_Net Income"]
            ),
            
            # Narrative queries
            GoldTestCase(
                query="Why did NVDA's revenue grow in recent years?",
                ticker="NVDA",
                expected_facts=["AI", "data center", "gaming", "growth drivers"],
                metrics_involved=[]
            ),
            GoldTestCase(
                query="What are the main risks mentioned in NVDA's filings?",
                ticker="NVDA",
                expected_facts=["competition", "supply chain", "regulatory"],
                metrics_involved=[]
            ),
            GoldTestCase(
                query="Explain Nvidia's business strategy",
                ticker="NVDA",
                expected_facts=["AI", "data center", "gaming", "strategy"],
                metrics_involved=[]
            ),
            
            # Hybrid queries (numbers + context)
            GoldTestCase(
                query="Analyze NVDA's revenue trends and explain the key drivers",
                ticker="NVDA",
                expected_facts=["revenue trend", "growth", "AI", "data center"],
                metrics_involved=["income_stmt_Revenue"]
            ),
            GoldTestCase(
                query="What were the main drivers of revenue growth for NVDA?",
                ticker="NVDA",
                expected_facts=["revenue", "growth", "drivers"],
                metrics_involved=["income_stmt_Revenue"]
            ),
            GoldTestCase(
                query="How did NVDA's profitability change from 2020 to 2023 and why?",
                ticker="NVDA",
                expected_facts=["profitability", "2020", "2023", "change"],
                metrics_involved=["income_stmt_Net Income", "Gross Profit Margin %"]
            ),
        ]
        
        self.test_cases = sample_cases
        self.save()
        
        print("✅ Created sample gold dataset")
        return sample_cases


# Global dataset manager
gold_dataset = GoldDatasetManager()