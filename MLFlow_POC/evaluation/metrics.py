"""
Evaluation metrics for RAG system quality assessment.
"""
import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import numpy as np


@dataclass
class EvaluationResult:
    """Container for evaluation scores"""
    query: str
    response: str
    ground_truth: Optional[str] = None
    
    # Scoring
    factual_accuracy: Optional[float] = None
    completeness: Optional[float] = None
    relevance: Optional[float] = None
    conciseness: Optional[float] = None
    
    # Meta
    passed: bool = False
    failure_reason: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "query": self.query,
            "response": self.response,
            "ground_truth": self.ground_truth,
            "scores": {
                "factual_accuracy": self.factual_accuracy,
                "completeness": self.completeness,
                "relevance": self.relevance,
                "conciseness": self.conciseness,
            },
            "passed": self.passed,
            "failure_reason": self.failure_reason
        }
    
    @property
    def overall_score(self) -> Optional[float]:
        """Calculate overall score as average of available metrics"""
        scores = [
            s for s in [
                self.factual_accuracy,
                self.completeness,
                self.relevance,
                self.conciseness
            ] if s is not None
        ]
        
        if not scores:
            return None
        
        return sum(scores) / len(scores)


class MetricsEvaluator:
    """
    Evaluate RAG system responses using multiple metrics.
    """
    
    def __init__(self):
        pass
    
    def evaluate_response(
        self,
        query: str,
        response: str,
        ground_truth: Optional[str] = None,
        expected_facts: Optional[List[str]] = None,
        context_used: Optional[List[str]] = None
    ) -> EvaluationResult:
        """
        Comprehensive evaluation of a single response.
        
        Args:
            query: Original query
            response: Generated response
            ground_truth: Optional expected response
            expected_facts: Optional list of facts that should be present
            context_used: Optional context that was retrieved
            
        Returns:
            EvaluationResult with scores
        """
        result = EvaluationResult(
            query=query,
            response=response,
            ground_truth=ground_truth
        )
        
        # Factual accuracy (if expected facts provided)
        if expected_facts:
            result.factual_accuracy = self._evaluate_factual_accuracy(
                response, expected_facts
            )
        
        # Completeness (if ground truth provided)
        if ground_truth:
            result.completeness = self._evaluate_completeness(
                response, ground_truth
            )
        
        # Relevance to query
        result.relevance = self._evaluate_relevance(query, response)
        
        # Conciseness
        result.conciseness = self._evaluate_conciseness(response)
        
        # Determine pass/fail
        result.passed = self._determine_pass_fail(result)
        
        return result
    
    def _evaluate_factual_accuracy(
        self,
        response: str,
        expected_facts: List[str]
    ) -> float:
        """
        Check if expected facts are present in response.
        
        Args:
            response: Generated response
            expected_facts: List of facts that should be included
            
        Returns:
            Score from 0.0 to 1.0
        """
        response_lower = response.lower()
        
        facts_found = 0
        for fact in expected_facts:
            fact_lower = fact.lower()
            
            # Check for exact match or close paraphrase
            if fact_lower in response_lower:
                facts_found += 1
            else:
                # Check for key terms from the fact
                key_terms = self._extract_key_terms(fact)
                terms_found = sum(1 for term in key_terms if term in response_lower)
                
                # If most terms present, consider fact partially found
                if len(key_terms) > 0 and terms_found / len(key_terms) >= 0.7:
                    facts_found += 0.7
        
        return facts_found / len(expected_facts) if expected_facts else 1.0
    
    def _evaluate_completeness(
        self,
        response: str,
        ground_truth: str
    ) -> float:
        """
        Compare response to ground truth for completeness.
        
        Args:
            response: Generated response
            ground_truth: Expected response
            
        Returns:
            Score from 0.0 to 1.0
        """
        # Extract key information from ground truth
        gt_key_terms = self._extract_key_terms(ground_truth)
        
        if not gt_key_terms:
            return 1.0
        
        response_lower = response.lower()
        
        # Count how many key terms are covered
        terms_found = sum(1 for term in gt_key_terms if term in response_lower)
        
        return terms_found / len(gt_key_terms)
    
    def _evaluate_relevance(self, query: str, response: str) -> float:
        """
        Evaluate if response is relevant to query.
        
        Args:
            query: Original query
            response: Generated response
            
        Returns:
            Score from 0.0 to 1.0
        """
        # Extract key terms from query
        query_terms = self._extract_key_terms(query)
        
        if not query_terms:
            return 1.0
        
        response_lower = response.lower()
        
        # Check for query term presence
        terms_found = sum(1 for term in query_terms if term in response_lower)
        
        relevance = terms_found / len(query_terms)
        
        # Boost score if response is not too long (staying on topic)
        if len(response) < 1000:
            relevance = min(relevance + 0.1, 1.0)
        
        return relevance
    
    def _evaluate_conciseness(self, response: str) -> float:
        """
        Evaluate if response is appropriately concise.
        
        Args:
            response: Generated response
            
        Returns:
            Score from 0.0 to 1.0
        """
        word_count = len(response.split())
        
        # Optimal range: 50-300 words
        if 50 <= word_count <= 300:
            return 1.0
        elif word_count < 50:
            # Too short - penalize linearly
            return word_count / 50
        else:
            # Too long - penalize
            penalty = min((word_count - 300) / 500, 0.5)
            return max(1.0 - penalty, 0.5)
    
    def _extract_key_terms(self, text: str) -> List[str]:
        """
        Extract key terms from text (nouns, numbers, significant words).
        
        Args:
            text: Input text
            
        Returns:
            List of key terms
        """
        text_lower = text.lower()
        
        # Remove common words
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been',
            'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
            'could', 'should', 'may', 'might', 'must', 'can', 'this', 'that',
            'these', 'those', 'what', 'which', 'who', 'when', 'where', 'why', 'how'
        }
        
        # Extract words (including numbers and financial terms)
        words = re.findall(r'\b[\w$%]+\b', text_lower)
        
        # Filter out stop words and very short words
        key_terms = [
            word for word in words
            if word not in stop_words and len(word) > 2
        ]
        
        return key_terms
    
    def _determine_pass_fail(self, result: EvaluationResult) -> bool:
        """
        Determine if response passes quality threshold.
        
        Args:
            result: EvaluationResult with scores
            
        Returns:
            True if passed, False otherwise
        """
        # Require minimum scores
        thresholds = {
            "factual_accuracy": 0.7,
            "completeness": 0.6,
            "relevance": 0.7,
            "conciseness": 0.5,
        }
        
        for metric, threshold in thresholds.items():
            score = getattr(result, metric)
            
            if score is not None and score < threshold:
                result.failure_reason = f"{metric} below threshold ({score:.2f} < {threshold})"
                return False
        
        return True
    
    def batch_evaluate(
        self,
        test_cases: List[Dict[str, Any]]
    ) -> List[EvaluationResult]:
        """
        Evaluate multiple test cases.
        
        Args:
            test_cases: List of dicts with query, response, ground_truth, etc.
            
        Returns:
            List of EvaluationResult objects
        """
        results = []
        
        for case in test_cases:
            result = self.evaluate_response(
                query=case["query"],
                response=case["response"],
                ground_truth=case.get("ground_truth"),
                expected_facts=case.get("expected_facts"),
                context_used=case.get("context_used")
            )
            results.append(result)
        
        return results
    
    def calculate_aggregate_metrics(
        self,
        results: List[EvaluationResult]
    ) -> Dict[str, float]:
        """
        Calculate aggregate statistics from evaluation results.
        
        Args:
            results: List of EvaluationResult objects
            
        Returns:
            Dictionary with aggregate metrics
        """
        metrics = {
            "total_queries": len(results),
            "pass_rate": sum(1 for r in results if r.passed) / len(results),
        }
        
        # Average scores
        score_fields = ["factual_accuracy", "completeness", "relevance", "conciseness"]
        
        for field in score_fields:
            scores = [getattr(r, field) for r in results if getattr(r, field) is not None]
            if scores:
                metrics[f"avg_{field}"] = sum(scores) / len(scores)
        
        # Overall score
        overall_scores = [r.overall_score for r in results if r.overall_score is not None]
        if overall_scores:
            metrics["avg_overall_score"] = sum(overall_scores) / len(overall_scores)
        
        return metrics


# Global evaluator instance
metrics_evaluator = MetricsEvaluator()