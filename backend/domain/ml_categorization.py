"""
Pure domain functions and classes for local ML transaction categorization.

Rules & Invariants:
1. Pure: No ORM, no Session, no HTTP, no filesystem paths, no environment variables.
2. Deterministic: Fixed random seeds ensure reproducible model fitting and evaluation.
3. Feature Stability: Structured merchant and raw description representation without leaking IDs.
4. Abstention: The model abstains (returns None) when confidence is below the prediction threshold.
5. Baseline Comparison: Simple merchant-frequency baseline is evaluated alongside Logistic Regression.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.metrics import accuracy_score, f1_score


DEFAULT_SUGGESTION_THRESHOLD = 0.30
DEFAULT_RANDOM_STATE = 42
MIN_TRAINABLE_EXAMPLES = 5
MIN_TRAINABLE_CATEGORIES = 2
MIN_DEPLOYABLE_EXAMPLES = 10
MIN_DEPLOYABLE_CATEGORIES = 2

# Backward-compatibility aliases
MIN_EXAMPLES_FOR_TRAINING = MIN_TRAINABLE_EXAMPLES
MIN_CATEGORIES_FOR_TRAINING = MIN_TRAINABLE_CATEGORIES


@dataclass(frozen=True)
class MLEvaluationMetrics:
    accuracy: float
    macro_f1: float
    top2_accuracy: float
    coverage: float
    total_examples: int
    test_examples: int
    category_count: int
    baseline_accuracy: float
    baseline_coverage: float
    class_distribution: dict[str, int]
    surfaced_count: int = 0
    surfaced_precision: float = 0.0


@dataclass(frozen=True)
class MLSuggestion:
    category_id: str
    confidence: float
    score_label: str


def build_feature_text(
    merchant: Optional[str],
    description: Optional[str],
) -> str:
    """
    Constructs a stable textual representation of a transaction for TF-IDF feature extraction.
    Combines normalized merchant identity and raw description text.
    Database IDs and category identities must never be included.
    """
    m = (merchant or "").strip()
    d = (description or "").strip()
    return f"MERCHANT: {m} DESCRIPTION: {d}"


class MerchantFrequencyBaseline:
    """
    Simple baseline classifier:
    For a given merchant, predicts the category most commonly assigned to that merchant
    in historical training examples.
    Abstains (returns None) for previously unseen merchants or empty merchants.
    """

    def __init__(self):
        self.merchant_to_top_category: dict[str, str] = {}
        self.category_counts: dict[str, int] = {}

    def fit(self, merchants: Sequence[Optional[str]], categories: Sequence[str]) -> "MerchantFrequencyBaseline":
        counts_by_merchant: dict[str, Counter[str]] = defaultdict(Counter)
        overall_counts: Counter[str] = Counter()

        for m, cat in zip(merchants, categories):
            clean_m = (m or "").strip().lower()
            if clean_m:
                counts_by_merchant[clean_m][str(cat)] += 1
            overall_counts[str(cat)] += 1

        self.merchant_to_top_category = {
            m: counter.most_common(1)[0][0]
            for m, counter in counts_by_merchant.items()
            if counter
        }
        self.category_counts = dict(overall_counts)
        return self

    def predict_one(self, merchant: Optional[str]) -> Optional[str]:
        clean_m = (merchant or "").strip().lower()
        if not clean_m:
            return None
        return self.merchant_to_top_category.get(clean_m)

    def predict(self, merchants: Sequence[Optional[str]]) -> list[Optional[str]]:
        return [self.predict_one(m) for m in merchants]


def create_ml_pipeline(
    random_state: int = DEFAULT_RANDOM_STATE,
) -> Pipeline:
    """
    Instantiates the preferred TF-IDF + Logistic Regression pipeline:
    - Character n-grams (3 to 5 chars) with word-boundary analyzer to handle typos,
      store numbers, and processor prefixes robustly.
    - Balanced class weighting to handle sparse personal finance categories fairly.
    """
    return Pipeline([
        (
            "tfidf",
            TfidfVectorizer(
                analyzer="char_wb",
                ngram_range=(3, 5),
                min_df=1,
                lowercase=True,
            ),
        ),
        (
            "clf",
            LogisticRegression(
                C=2.0,
                max_iter=1000,
                class_weight="balanced",
                random_state=random_state,
            ),
        ),
    ])


def evaluate_classifier(
    pipeline: Pipeline,
    X_test: Sequence[str],
    y_test: Sequence[str],
    baseline: Optional[MerchantFrequencyBaseline] = None,
    merchants_test: Optional[Sequence[Optional[str]]] = None,
    threshold: float = DEFAULT_SUGGESTION_THRESHOLD,
    total_dataset_size: int = 0,
    class_distribution: Optional[dict[str, int]] = None,
) -> MLEvaluationMetrics:
    """
    Evaluates classifier predictions against test labels:
    - Accuracy
    - Macro F1 (with zero_division=0)
    - Top-2 accuracy
    - Coverage (proportion with max probability >= threshold)
    - Merchant frequency baseline accuracy and coverage on identical test set
    """
    if len(X_test) == 0:
        return MLEvaluationMetrics(
            accuracy=0.0,
            macro_f1=0.0,
            top2_accuracy=0.0,
            coverage=0.0,
            total_examples=total_dataset_size,
            test_examples=0,
            category_count=len(class_distribution or {}),
            baseline_accuracy=0.0,
            baseline_coverage=0.0,
            class_distribution=class_distribution or {},
        )

    y_test_arr = np.array([str(y) for y in y_test])
    preds = pipeline.predict(X_test)
    probs = pipeline.predict_proba(X_test)
    classes = pipeline.classes_

    acc = float(accuracy_score(y_test_arr, preds))
    macro_f1 = float(f1_score(y_test_arr, preds, average="macro", zero_division=0))

    # Top-2 accuracy
    top2_correct = 0
    for prob_row, true_label in zip(probs, y_test_arr):
        top_indices = np.argsort(prob_row)[::-1][:2]
        top_classes = classes[top_indices]
        if true_label in top_classes:
            top2_correct += 1
    top2_acc = float(top2_correct / len(y_test_arr))

    # Coverage and precision at suggestion threshold
    max_probs = probs.max(axis=1)
    surfaced_mask = max_probs >= threshold
    surfaced_count = int(np.sum(surfaced_mask))
    coverage = float(surfaced_count / len(y_test_arr)) if len(y_test_arr) > 0 else 0.0
    if surfaced_count > 0:
        surfaced_correct = int(np.sum(preds[surfaced_mask] == y_test_arr[surfaced_mask]))
        surfaced_precision = float(surfaced_correct / surfaced_count)
    else:
        surfaced_precision = 0.0

    # Baseline evaluation
    base_acc = 0.0
    base_cov = 0.0
    if baseline is not None and merchants_test is not None:
        base_preds = baseline.predict(merchants_test)
        covered_count = sum(1 for p in base_preds if p is not None)
        base_cov = float(covered_count / len(y_test_arr)) if len(y_test_arr) > 0 else 0.0
        correct_count = sum(
            1 for p, true_l in zip(base_preds, y_test_arr)
            if p is not None and p == true_l
        )
        base_acc = float(correct_count / len(y_test_arr)) if len(y_test_arr) > 0 else 0.0

    return MLEvaluationMetrics(
        accuracy=round(acc, 4),
        macro_f1=round(macro_f1, 4),
        top2_accuracy=round(top2_acc, 4),
        coverage=round(coverage, 4),
        total_examples=total_dataset_size,
        test_examples=len(y_test_arr),
        category_count=len(classes),
        baseline_accuracy=round(base_acc, 4),
        baseline_coverage=round(base_cov, 4),
        class_distribution=class_distribution or {},
        surfaced_count=surfaced_count,
        surfaced_precision=round(surfaced_precision, 4),
    )


MAX_ACCURACY_DROP_PERCENTAGE_POINTS = 0.15
MIN_SURFACED_PRECISION = 0.50


def should_activate_candidate(
    candidate_metrics: MLEvaluationMetrics,
    active_metrics: Optional[MLEvaluationMetrics] = None,
    active_accuracy: Optional[float] = None,
) -> tuple[bool, str]:
    """
    Decides whether a newly trained candidate model qualifies for production activation:
    1. Dataset Sufficiency: Must have at least MIN_DEPLOYABLE_EXAMPLES (10) and MIN_DEPLOYABLE_CATEGORIES (2).
       If fewer, returns (False, 'Needs more training data: ...').
    2. Measurable Performance:
       - Held-out accuracy must be strictly > 0.0.
       - Operating threshold coverage must be > 0.0 (model must not abstain on 100% of cases).
       - If suggestions are surfaced at threshold, surfaced precision must be >= 50.0% (empirically useful operating point).
    3. Active Model Comparison: When evaluated on the exact same holdout split (or historical benchmark),
       candidate accuracy must not be more than 15 percentage points below the active model.
    """
    if candidate_metrics.total_examples < MIN_DEPLOYABLE_EXAMPLES:
        return (
            False,
            f"Needs more training data: {candidate_metrics.total_examples} examples available (minimum {MIN_DEPLOYABLE_EXAMPLES} required for deployment).",
        )

    if candidate_metrics.category_count < MIN_DEPLOYABLE_CATEGORIES:
        return (
            False,
            f"Needs more training data: {candidate_metrics.category_count} categories available (minimum {MIN_DEPLOYABLE_CATEGORIES} required for deployment).",
        )

    if candidate_metrics.accuracy <= 0.0:
        return (
            False,
            "Needs more training data: Candidate model achieved 0.0% holdout accuracy.",
        )

    if candidate_metrics.coverage <= 0.0:
        return (
            False,
            "Needs more training data: Model confidence is too low to produce suggestions at the operating threshold.",
        )

    if candidate_metrics.surfaced_count > 0 and candidate_metrics.surfaced_precision < MIN_SURFACED_PRECISION:
        return (
            False,
            f"Needs more training data: Surfaced suggestion precision ({candidate_metrics.surfaced_precision:.1%}) is below the required usefulness threshold (50.0%).",
        )

    # Determine reference active accuracy:
    # active_accuracy represents the active model's recorded holdout benchmark.
    # When available, it is preferred because evaluating the active model on the candidate's
    # holdout split suffers from in-sample memorization (as the active model was already fitted
    # on prior examples contained in the dataset).
    ref_active_acc: Optional[float] = None
    if active_accuracy is not None and active_accuracy > 0.0:
        ref_active_acc = active_accuracy
    elif active_metrics is not None and active_metrics.accuracy is not None and active_metrics.accuracy > 0.0:
        ref_active_acc = active_metrics.accuracy

    if ref_active_acc is not None and ref_active_acc > 0.0:
        if candidate_metrics.accuracy < (ref_active_acc - MAX_ACCURACY_DROP_PERCENTAGE_POINTS):
            source_desc = "compared to active baseline" if active_accuracy is not None else "on the same test set"
            return (
                False,
                f"Candidate accuracy ({candidate_metrics.accuracy:.1%}) is more than 15 percentage points below active model ({ref_active_acc:.1%}) {source_desc}.",
            )

    return True, "Candidate passed deployability criteria."


def predict_suggestion(
    pipeline: Pipeline,
    feature_text: str,
    threshold: float = DEFAULT_SUGGESTION_THRESHOLD,
) -> Optional[MLSuggestion]:
    """
    Generates a category suggestion for an input transaction feature string.
    Returns MLSuggestion if confidence >= threshold, or None if the model abstains.
    """
    probs = pipeline.predict_proba([feature_text])[0]
    classes = pipeline.classes_

    best_idx = int(np.argmax(probs))
    best_score = float(probs[best_idx])
    best_category_id = str(classes[best_idx])

    if best_score < threshold:
        return None

    score_pct = int(round(best_score * 100))
    return MLSuggestion(
        category_id=best_category_id,
        confidence=round(best_score, 4),
        score_label=f"{score_pct}% confidence",
    )
