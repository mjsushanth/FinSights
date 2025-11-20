"""
LLM Answer Evaluation Metrics for FinRAG Gold Test Suite.

Provides 4 core metrics:
1. ROUGE-L - Lexical overlap (baseline)
2. BERTScore F1 - Semantic similarity via contextual embeddings
3. Cosine Similarity - Fast semantic check via sentence embeddings
4. BLEURT - Learned metric trained on human judgments

Includes per-metric timing for performance analysis.
"""

import time
from pathlib import Path
from typing import Dict, Union, List
from bert_score import score as bert_score
from rouge_score import rouge_scorer
from sentence_transformers import SentenceTransformer, util

# Lazy-load BLEURT (heavy import)
_BLEURT_SCORER = None


def _get_bleurt_scorer():
    """Lazy-load BLEURT scorer (uses cached checkpoint)."""
    global _BLEURT_SCORER
    if _BLEURT_SCORER is None:
        from bleurt import score as bleurt_score
        checkpoint_path = str(Path.home() / ".cache" / "bleurt" / "BLEURT-20")
        _BLEURT_SCORER = bleurt_score.BleurtScorer(checkpoint_path)
    return _BLEURT_SCORER


# Initialize lightweight models at module load
SENTENCE_MODEL = SentenceTransformer('all-MiniLM-L6-v2')  # 80MB
ROUGE_SCORER = rouge_scorer.RougeScorer(['rougeL'], use_stemmer=True)


def evaluate_answer(
    gold_answer: Union[str, List[str]],
    synthesis_answer: str,
    include_bleurt: bool = True,
    include_timing: bool = True
) -> Dict[str, Union[float, str]]:
    """
    Evaluate synthesis answer against gold reference.
    
    Args:
        gold_answer: Curated reference answer
        synthesis_answer: LLM-generated synthesis
        include_bleurt: Whether to compute BLEURT (slower, ~5s)
        include_timing: Whether to include per-metric timing
    
    Returns:
        Dictionary with scores and optional timing:
        {
            "rouge_l": 0.682,
            "bertscore_f1": 0.874,
            "cosine_sim": 0.791,
            "bleurt": 0.756,  (if include_bleurt=True)
            "interpretation": "Excellent semantic match",
            "timing": {  (if include_timing=True)
                "rouge_l_ms": 45.2,
                "bertscore_ms": 2341.8,
                "cosine_ms": 18.3,
                "bleurt_ms": 4823.1,
                "total_ms": 7228.4
            }
        }
    """
    results = {}
    timing = {} if include_timing else None
    
    # Convert list gold answers to single string (join with newlines)
    if isinstance(gold_answer, list):
        gold_answer = "\n\n".join(gold_answer)
    
    # 1. ROUGE-L (fast, ~50ms)
    t0 = time.perf_counter()
    rouge_scores = ROUGE_SCORER.score(gold_answer, synthesis_answer)
    results['rouge_l'] = round(rouge_scores['rougeL'].fmeasure, 3)
    if include_timing:
        timing['rouge_l_ms'] = round((time.perf_counter() - t0) * 1000, 1)
    
    # 2. BERTScore F1 (accurate, ~2-3s on CPU)
    t0 = time.perf_counter()
    P, R, F1 = bert_score(
        [synthesis_answer],
        [gold_answer],
        lang='en',
        verbose=False
    )
    results['bertscore_f1'] = round(F1.item(), 3)
    if include_timing:
        timing['bertscore_ms'] = round((time.perf_counter() - t0) * 1000, 1)
    
    # 3. Cosine Similarity (fast, ~20ms)
    t0 = time.perf_counter()
    emb_gold = SENTENCE_MODEL.encode(gold_answer, convert_to_tensor=False)
    emb_synth = SENTENCE_MODEL.encode(synthesis_answer, convert_to_tensor=False)
    results['cosine_sim'] = round(util.cos_sim(emb_gold, emb_synth).item(), 3)
    if include_timing:
        timing['cosine_ms'] = round((time.perf_counter() - t0) * 1000, 1)
    
    # 4. BLEURT (optional, ~5s on CPU)
    if include_bleurt:
        t0 = time.perf_counter()
        scorer = _get_bleurt_scorer()
        bleurt_scores = scorer.score(
            references=[gold_answer],
            candidates=[synthesis_answer]
        )
        results['bleurt'] = round(bleurt_scores[0], 3)
        if include_timing:
            timing['bleurt_ms'] = round((time.perf_counter() - t0) * 1000, 1)
    
    # Interpretation based on BERTScore (most reliable)
    results['interpretation'] = _interpret_bertscore(results['bertscore_f1'])
    
    # Add timing summary
    if include_timing:
        timing['total_ms'] = round(sum(timing.values()), 1)
        results['timing'] = timing
    
    return results


def _interpret_bertscore(bertscore_f1: float) -> str:
    """Interpret BERTScore F1 into human-readable quality level."""
    if bertscore_f1 >= 0.90:
        return "Exceptional match"
    elif bertscore_f1 >= 0.85:
        return "Excellent semantic match"
    elif bertscore_f1 >= 0.75:
        return "Strong similarity"
    elif bertscore_f1 >= 0.65:
        return "Moderate alignment"
    elif bertscore_f1 >= 0.50:
        return "Weak match"
    else:
        return "Poor alignment"


def _interpret_bleurt(bleurt_score: float) -> str:
    """Interpret BLEURT score into human-readable quality level."""
    if bleurt_score >= 0.7:
        return "Excellent"
    elif bleurt_score >= 0.5:
        return "Good"
    elif bleurt_score >= 0.3:
        return "Moderate"
    elif bleurt_score >= 0.0:
        return "Weak"
    else:
        return "Poor"


def evaluate_batch(
    gold_answers: List[str],
    synthesis_answers: List[str],
    include_bleurt: bool = True,
    include_timing: bool = True
) -> List[Dict[str, Union[float, str]]]:
    """
    Evaluate multiple answer pairs in batch.
    
    Args:
        gold_answers: List of gold reference answers
        synthesis_answers: List of synthesis answers
        include_bleurt: Whether to compute BLEURT
        include_timing: Whether to include per-metric timing
    
    Returns:
        List of score dictionaries (one per answer pair)
    """
    return [
        evaluate_answer(gold, synth, include_bleurt, include_timing)
        for gold, synth in zip(gold_answers, synthesis_answers)
    ]


"""
{
    "rouge_l": 0.682,
    "bertscore_f1": 0.874,
    "cosine_sim": 0.791,
    "bleurt": 0.756,
    "interpretation": "Excellent semantic match",
    "timing": {
        "rouge_l_ms": 45.2,
        "bertscore_ms": 2341.8,
        "cosine_ms": 18.3,
        "bleurt_ms": 4823.1,
        "total_ms": 7228.4
    }
}
"""