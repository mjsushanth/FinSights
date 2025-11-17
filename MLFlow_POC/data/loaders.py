"""
Data loading utilities with caching support.
"""
import pandas as pd
import faiss
from sentence_transformers import SentenceTransformer
from dataclasses import dataclass
from typing import Optional
from pathlib import Path

from config.settings import data_paths


@dataclass
class DataContext:
    """Container for all loaded data"""
    metrics: pd.DataFrame
    sentences: pd.DataFrame
    faiss_index: faiss.Index
    embedder: SentenceTransformer
    
    def __post_init__(self):
        """Validate data after initialization"""
        assert len(self.metrics) > 0, "Metrics dataframe is empty"
        assert len(self.sentences) > 0, "Sentences dataframe is empty"
        assert self.faiss_index.ntotal > 0, "FAISS index is empty"


class DataLoader:
    """Centralized data loading with caching"""
    
    _instance: Optional['DataLoader'] = None
    _data_context: Optional[DataContext] = None
    
    def __new__(cls):
        """Singleton pattern for data loader"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def load_all(self, force_reload: bool = False) -> DataContext:
        """
        Load all required data sources.
        
        Args:
            force_reload: If True, reload even if cached
            
        Returns:
            DataContext with all loaded data
        """
        if self._data_context is not None and not force_reload:
            print("✅ Using cached data")
            return self._data_context
        
        print("📂 Loading data from disk...")
        
        # Load structured metrics
        metrics = self._load_metrics()
        
        # Load sentences for semantic search
        sentences = self._load_sentences()
        
        # Load FAISS index
        index = self._load_faiss_index()
        
        # Load embedder model
        embedder = self._load_embedder()
        
        self._data_context = DataContext(
            metrics=metrics,
            sentences=sentences,
            faiss_index=index,
            embedder=embedder
        )
        
        print(f"✅ Data loaded: {len(metrics)} metrics, "
              f"{len(sentences)} sentences, {index.ntotal} vectors")
        
        return self._data_context
    
    def _load_metrics(self) -> pd.DataFrame:
        """Load structured KPI metrics"""
        path = data_paths.METRICS_FILE
        if not path.exists():
            raise FileNotFoundError(f"Metrics file not found: {path}")
        
        df = pd.read_parquet(path)
        
        # Validate required columns
        required_cols = ["ticker", "metric", "year", "value"]
        missing = set(required_cols) - set(df.columns)
        if missing:
            raise ValueError(f"Missing required columns: {missing}")
        
        return df
    
    def _load_sentences(self) -> pd.DataFrame:
        """Load windowed sentences for semantic search"""
        path = data_paths.SENTENCES_FILE
        if not path.exists():
            raise FileNotFoundError(f"Sentences file not found: {path}")
        
        df = pd.read_parquet(path)
        
        # Validate required columns
        required_cols = ["ticker", "primary_sentence"]
        missing = set(required_cols) - set(df.columns)
        if missing:
            raise ValueError(f"Missing required columns: {missing}")
        
        return df
    
    def _load_faiss_index(self) -> faiss.Index:
        """Load FAISS vector index"""
        path = data_paths.FAISS_INDEX
        if not path.exists():
            raise FileNotFoundError(f"FAISS index not found: {path}")
        
        return faiss.read_index(str(path))
    
    def _load_embedder(self) -> SentenceTransformer:
        """Load sentence transformer model"""
        model_name = data_paths.EMBEDDER_MODEL
        print(f"🔧 Loading embedder: {model_name}")
        return SentenceTransformer(model_name)
    
    def get_metrics_for_ticker(self, ticker: str) -> pd.DataFrame:
        """Get all metrics for a specific ticker"""
        if self._data_context is None:
            self.load_all()
        
        return self._data_context.metrics[
            self._data_context.metrics.ticker == ticker
        ].copy()
    
    def get_available_tickers(self) -> list:
        """Get list of available tickers"""
        if self._data_context is None:
            self.load_all()
        
        return sorted(self._data_context.metrics.ticker.unique())
    
    def get_available_metrics(self, ticker: str = None) -> list:
        """Get list of available metrics, optionally filtered by ticker"""
        if self._data_context is None:
            self.load_all()
        
        df = self._data_context.metrics
        if ticker:
            df = df[df.ticker == ticker]
        
        return sorted(df.metric.unique())


# Global data loader instance
data_loader = DataLoader()