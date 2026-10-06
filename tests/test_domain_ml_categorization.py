"""
Unit tests for Pure ML Categorization Domain Engine.

Verifies:
1. Feature text construction invariants (no ID leakage, stable representation).
2. Merchant frequency baseline logic (majority vote, unseen merchant abstention).
3. Pipeline training, evaluation metrics, and score calibration.
4. Abstention below threshold.
5. Candidate safety gate against active model.
6. Reproducibility with fixed random seed.
"""

import pytest
from backend.domain.ml_categorization import (
    DEFAULT_SUGGESTION_THRESHOLD,
    MerchantFrequencyBaseline,
    build_feature_text,
    create_ml_pipeline,
    evaluate_classifier,
    predict_suggestion,
    should_activate_candidate,
)


def test_build_feature_text_combines_merchant_and_description():
    text = build_feature_text("Starbucks", "SQ *STARBUCKS 1842")
    assert text == "MERCHANT: Starbucks DESCRIPTION: SQ *STARBUCKS 1842"


def test_build_feature_text_handles_none_and_whitespace():
    assert build_feature_text(None, None) == "MERCHANT:  DESCRIPTION: "
    assert build_feature_text("  Target  ", "  ") == "MERCHANT: Target DESCRIPTION: "


def test_merchant_frequency_baseline_majority_vote():
    baseline = MerchantFrequencyBaseline()
    merchants = ["Starbucks", "Starbucks", "Starbucks", "Target", "Target"]
    categories = ["cat-coffee", "cat-coffee", "cat-food", "cat-shopping", "cat-shopping"]
    baseline.fit(merchants, categories)

    # Starbucks majority is cat-coffee
    assert baseline.predict_one("Starbucks") == "cat-coffee"
    assert baseline.predict_one("starbucks") == "cat-coffee"  # case-insensitive
    # Target is cat-shopping
    assert baseline.predict_one("Target") == "cat-shopping"
    # Unseen merchant returns None (abstains)
    assert baseline.predict_one("Unknown Merchant") is None
    assert baseline.predict_one(None) is None


def test_pipeline_training_and_reproducibility():
    corpus_X = [
        build_feature_text("Starbucks", "STARBUCKS #101"),
        build_feature_text("Starbucks", "STARBUCKS #102"),
        build_feature_text("Starbucks", "SQ *STARBUCKS"),
        build_feature_text("Safeway", "SAFEWAY GROCERY #44"),
        build_feature_text("Safeway", "SAFEWAY STORE 88"),
        build_feature_text("Safeway", "SAFEWAY DOWNTOWN"),
        build_feature_text("Shell", "SHELL OIL 123"),
        build_feature_text("Shell", "SHELL GAS STATION"),
        build_feature_text("Shell", "CHEVRON GAS"),
    ]
    corpus_y = [
        "cat-coffee", "cat-coffee", "cat-coffee",
        "cat-groceries", "cat-groceries", "cat-groceries",
        "cat-fuel", "cat-fuel", "cat-fuel",
    ]

    p1 = create_ml_pipeline(random_state=42)
    p1.fit(corpus_X, corpus_y)

    p2 = create_ml_pipeline(random_state=42)
    p2.fit(corpus_X, corpus_y)

    test_input = build_feature_text("Starbucks", "STARBUCKS #999")
    prob1 = p1.predict_proba([test_input])[0]
    prob2 = p2.predict_proba([test_input])[0]

    # Explicit seed produces identical weights and predictions
    assert list(p1.classes_) == list(p2.classes_)
    assert (prob1 == prob2).all()


def test_predict_suggestion_above_threshold_and_abstention():
    corpus_X = [
        build_feature_text("Safeway", "SAFEWAY GROCERY"),
        build_feature_text("Safeway", "SAFEWAY SUPERMARKET"),
        build_feature_text("Chevron", "CHEVRON GAS"),
        build_feature_text("Chevron", "CHEVRON EXPRESS"),
    ]
    corpus_y = ["cat-groceries", "cat-groceries", "cat-fuel", "cat-fuel"]

    pipeline = create_ml_pipeline(random_state=42)
    pipeline.fit(corpus_X, corpus_y)

    # 1. Matching text produces suggestion
    sug = predict_suggestion(
        pipeline=pipeline,
        feature_text=build_feature_text("Safeway", "SAFEWAY STORE 500"),
        threshold=0.25,
    )
    assert sug is not None
    assert sug.category_id == "cat-groceries"
    assert sug.confidence >= 0.25
    assert "confidence" in sug.score_label

    # 2. Ambiguous / unrelated text with high threshold abstains
    sug_abstain = predict_suggestion(
        pipeline=pipeline,
        feature_text=build_feature_text("Unknown", "COMPLETELY UNRELATED TEXT"),
        threshold=0.99,
    )
    assert sug_abstain is None


def test_evaluate_classifier_computes_metrics_without_crashing():
    pipeline = create_ml_pipeline(random_state=42)
    X = [
        build_feature_text("A", "text a 1"),
        build_feature_text("A", "text a 2"),
        build_feature_text("B", "text b 1"),
        build_feature_text("B", "text b 2"),
    ]
    y = ["cat-a", "cat-a", "cat-b", "cat-b"]
    pipeline.fit(X, y)

    baseline = MerchantFrequencyBaseline().fit(["A", "A", "B", "B"], y)

    metrics = evaluate_classifier(
        pipeline=pipeline,
        X_test=X,
        y_test=y,
        baseline=baseline,
        merchants_test=["A", "A", "B", "B"],
        threshold=0.25,
        total_dataset_size=4,
    )

    assert metrics.accuracy == 1.0
    assert metrics.macro_f1 == 1.0
    assert metrics.top2_accuracy == 1.0
    assert metrics.coverage == 1.0
    assert metrics.baseline_accuracy == 1.0
    assert metrics.baseline_coverage == 1.0
    assert metrics.category_count == 2


def test_evaluate_classifier_handles_empty_test_set():
    pipeline = create_ml_pipeline(random_state=42)
    metrics = evaluate_classifier(
        pipeline=pipeline,
        X_test=[],
        y_test=[],
        total_dataset_size=10,
    )
    assert metrics.accuracy == 0.0
    assert metrics.test_examples == 0


def test_should_activate_candidate_rules():
    # 1. Candidate with too few categories rejected
    from backend.domain.ml_categorization import MLEvaluationMetrics
    m_few_cats = MLEvaluationMetrics(
        accuracy=0.9,
        macro_f1=0.9,
        top2_accuracy=0.9,
        coverage=0.9,
        total_examples=20,
        test_examples=5,
        category_count=1,
        baseline_accuracy=0.8,
        baseline_coverage=0.8,
        class_distribution={"cat-a": 20},
    )
    active, reason = should_activate_candidate(m_few_cats, active_accuracy=None)
    assert not active
    assert "minimum 2 required" in reason

    # 2. Candidate with too few examples rejected for deployability
    m_few_examples = MLEvaluationMetrics(
        accuracy=0.9,
        macro_f1=0.9,
        top2_accuracy=0.9,
        coverage=0.9,
        total_examples=3,
        test_examples=1,
        category_count=2,
        baseline_accuracy=0.8,
        baseline_coverage=0.8,
        class_distribution={"cat-a": 2, "cat-b": 1},
    )
    active, reason = should_activate_candidate(m_few_examples, active_accuracy=None)
    assert not active
    assert "minimum 10 required for deployment" in reason

    # 3. Candidate with 0 holdout accuracy rejected
    m_zero_acc = MLEvaluationMetrics(
        accuracy=0.0,
        macro_f1=0.0,
        top2_accuracy=0.0,
        coverage=0.0,
        total_examples=20,
        test_examples=5,
        category_count=2,
        baseline_accuracy=0.0,
        baseline_coverage=0.0,
        class_distribution={"cat-a": 10, "cat-b": 10},
    )
    active, reason = should_activate_candidate(m_zero_acc, active_accuracy=None)
    assert not active
    assert "0.0% holdout accuracy" in reason

    # 4. Candidate materially worse than active model rejected (evaluated on same holdout split)
    m_worse = MLEvaluationMetrics(
        accuracy=0.40,
        macro_f1=0.40,
        top2_accuracy=0.50,
        coverage=0.50,
        total_examples=50,
        test_examples=10,
        category_count=4,
        baseline_accuracy=0.40,
        baseline_coverage=0.40,
        class_distribution={"cat-a": 15, "cat-b": 15, "cat-c": 10, "cat-d": 10},
    )
    m_active = MLEvaluationMetrics(
        accuracy=0.85,
        macro_f1=0.85,
        top2_accuracy=0.90,
        coverage=0.80,
        total_examples=50,
        test_examples=10,
        category_count=4,
        baseline_accuracy=0.70,
        baseline_coverage=0.70,
        class_distribution={"cat-a": 15, "cat-b": 15, "cat-c": 10, "cat-d": 10},
    )
    active, reason = should_activate_candidate(m_worse, active_metrics=m_active)
    assert not active
    assert "15 percentage points below active model" in reason

    # 5. Candidate with low surfaced precision rejected
    m_low_prec = MLEvaluationMetrics(
        accuracy=0.60,
        macro_f1=0.60,
        top2_accuracy=0.70,
        coverage=0.50,
        total_examples=50,
        test_examples=10,
        category_count=4,
        baseline_accuracy=0.40,
        baseline_coverage=0.40,
        class_distribution={"cat-a": 15, "cat-b": 15, "cat-c": 10, "cat-d": 10},
        surfaced_count=5,
        surfaced_precision=0.40,
    )
    active, reason = should_activate_candidate(m_low_prec, active_accuracy=None)
    assert not active
    assert "below the required usefulness threshold" in reason

    # 6. Valid candidate passes
    m_valid = MLEvaluationMetrics(
        accuracy=0.80,
        macro_f1=0.80,
        top2_accuracy=0.90,
        coverage=0.85,
        total_examples=50,
        test_examples=10,
        category_count=4,
        baseline_accuracy=0.70,
        baseline_coverage=0.70,
        class_distribution={"cat-a": 15, "cat-b": 15, "cat-c": 10, "cat-d": 10},
        surfaced_count=8,
        surfaced_precision=0.875,
    )
    active, reason = should_activate_candidate(m_valid, active_accuracy=0.75)
    assert active

    # 7. Memorization fallback: active model evaluated at 100% on split, but its out-of-sample benchmark is 75%
    m_active_memorized = MLEvaluationMetrics(
        accuracy=1.0,
        macro_f1=1.0,
        top2_accuracy=1.0,
        coverage=1.0,
        total_examples=50,
        test_examples=10,
        category_count=4,
        baseline_accuracy=0.70,
        baseline_coverage=0.70,
        class_distribution={"cat-a": 15, "cat-b": 15, "cat-c": 10, "cat-d": 10},
    )
    # Candidate with 70% accuracy should pass against active_accuracy=0.75 (drop is only 5 pp, <= 15 pp)
    m_cand_70 = MLEvaluationMetrics(
        accuracy=0.70,
        macro_f1=0.70,
        top2_accuracy=0.80,
        coverage=0.80,
        total_examples=50,
        test_examples=10,
        category_count=4,
        baseline_accuracy=0.60,
        baseline_coverage=0.60,
        class_distribution={"cat-a": 15, "cat-b": 15, "cat-c": 10, "cat-d": 10},
        surfaced_count=8,
        surfaced_precision=0.75,
    )
    active, reason = should_activate_candidate(
        m_cand_70,
        active_metrics=m_active_memorized,
        active_accuracy=0.75,
    )
    assert active, f"Expected candidate to pass due to memorization fallback, got: {reason}"
