"""
Workflow manager for Local ML Categorization.

Coordinates:
1. Checking model availability, metadata, and staleness.
2. Managing automatic and manual retraining cycles:
   - Extracting eligible training examples from PostgreSQL ResourceAccess.
   - Fitting TF-IDF + Logistic Regression candidate pipeline and merchant baseline via Domain Engine.
   - Evaluating candidate metrics and enforcing regression safety gates.
   - Staging temporary serialized artifact and executing atomic replacement.
   - Updating PostgreSQL metadata and committing transaction boundaries.
3. Suggestion inference for transactions:
   - Enforcing precedence: existing category > deterministic rule > ML suggestion.
   - Excluding transfers and uncategorized rows below confidence threshold.
   - Batch suggestion optimization (freshness check and model load once per batch).
4. Accepting suggestions with proper provenance tracking (category_source='ml') and revision increment.
"""

from collections import Counter
from datetime import datetime, timezone
import logging
from typing import Optional, Sequence
from uuid import UUID
from sklearn.model_selection import train_test_split
from sqlalchemy.orm import Session

from .. import models, schemas
from ..access import (
    category_access,
    categorization_rule_access,
    ml_model_access,
    transaction_access,
)
from ..domain.categorization_rules import clean_merchant_key
from ..domain.ml_categorization import (
    DEFAULT_SUGGESTION_THRESHOLD,
    DEFAULT_RANDOM_STATE,
    MIN_TRAINABLE_EXAMPLES,
    MIN_TRAINABLE_CATEGORIES,
    MIN_DEPLOYABLE_EXAMPLES,
    MIN_DEPLOYABLE_CATEGORIES,
    MerchantFrequencyBaseline,
    build_feature_text,
    create_ml_pipeline,
    evaluate_classifier,
    predict_suggestion,
    should_activate_candidate,
)

logger = logging.getLogger(__name__)

RETRAIN_THRESHOLD = 10


def get_ml_status(db: Session) -> schemas.MLModelStatusRead:
    """
    Returns current ML model status, including availability, training revisions,
    example count, and recent evaluation metrics.
    """
    meta = ml_model_access.get_model_metadata(db)
    has_artifact = ml_model_access.artifact_exists()
    is_available = meta.model_available and has_artifact

    new_labels = max(0, meta.current_training_revision - meta.trained_revision)

    if not is_available:
        status_label = "Needs more data" if meta.training_example_count < MIN_DEPLOYABLE_EXAMPLES else "Ready to train"
    elif new_labels >= RETRAIN_THRESHOLD:
        status_label = "Stale"
    else:
        status_label = "Ready"

    return schemas.MLModelStatusRead(
        model_available=is_available,
        status=status_label,
        trained_at=meta.trained_at,
        trained_revision=meta.trained_revision,
        current_training_revision=meta.current_training_revision,
        new_labels_since_training=new_labels,
        training_example_count=meta.training_example_count,
        retrain_threshold=RETRAIN_THRESHOLD,
        accuracy=float(meta.accuracy) if meta.accuracy is not None else None,
        macro_f1=float(meta.macro_f1) if meta.macro_f1 is not None else None,
        top2_accuracy=float(meta.top2_accuracy) if meta.top2_accuracy is not None else None,
        coverage=float(meta.coverage) if meta.coverage is not None else None,
        status_message=meta.status_message or status_label,
    )


def retrain_model(
    db: Session,
    force: bool = False,
) -> tuple[bool, str, bool, schemas.MLModelStatusRead]:
    """
    Executes full-batch local training of a candidate TF-IDF + Logistic Regression pipeline:
    1. Loads eligible supervised training examples from Transaction ResourceAccess.
    2. Validates minimum example count and category diversity.
    3. Builds stable feature text and evaluates candidate against held-out split and merchant baseline.
    4. Enforces safety gates against existing active model.
    5. Serializes candidate to temporary file, validates deserialization, and replaces active model atomically.
    6. Updates metadata and commits.
    If training fails at any step, rolls back and preserves existing active model intact.
    Returns (success, message, model_activated, updated_status).
    """
    meta = ml_model_access.get_model_metadata(db)
    examples = ml_model_access.get_ml_training_examples(db)

    total_examples = len(examples)
    class_counts = Counter(str(ex.category_id) for ex in examples)
    distinct_categories = len(class_counts)

    if total_examples < MIN_TRAINABLE_EXAMPLES or distinct_categories < MIN_TRAINABLE_CATEGORIES:
        msg = (
            f"Insufficient training data: {total_examples} examples across {distinct_categories} categories. "
            f"Minimum {MIN_TRAINABLE_EXAMPLES} examples and {MIN_TRAINABLE_CATEGORIES} categories required."
        )
        meta.status_message = msg
        db.add(meta)
        db.commit()
        return False, msg, False, get_ml_status(db)

    X_texts = [build_feature_text(ex.merchant, ex.description) for ex in examples]
    y_labels = [str(ex.category_id) for ex in examples]
    merchants = [ex.merchant for ex in examples]

    # Split dataset for held-out evaluation
    # Use stratification only if all classes have at least 2 samples
    can_stratify = all(c >= 2 for c in class_counts.values()) and total_examples >= 8
    try:
        if can_stratify:
            X_train, X_test, y_train, y_test, m_train, m_test = train_test_split(
                X_texts,
                y_labels,
                merchants,
                test_size=0.25,
                random_state=DEFAULT_RANDOM_STATE,
                stratify=y_labels,
            )
        else:
            X_train, X_test, y_train, y_test, m_train, m_test = train_test_split(
                X_texts,
                y_labels,
                merchants,
                test_size=0.25,
                random_state=DEFAULT_RANDOM_STATE,
                stratify=None,
            )
    except Exception as exc:
        logger.warning("Train/test split fallback: %s", exc)
        X_train, X_test, y_train, y_test, m_train, m_test = (
            X_texts, X_texts, y_labels, y_labels, merchants, merchants
        )

    temp_path: Optional[str] = None
    try:
        # Fit candidate pipeline
        candidate_pipeline = create_ml_pipeline(random_state=DEFAULT_RANDOM_STATE)
        candidate_pipeline.fit(X_train, y_train)

        # Fit baseline on train split
        baseline = MerchantFrequencyBaseline()
        baseline.fit(m_train, y_train)

        # Evaluate candidate against test split
        metrics = evaluate_classifier(
            pipeline=candidate_pipeline,
            X_test=X_test,
            y_test=y_test,
            baseline=baseline,
            merchants_test=m_test,
            threshold=DEFAULT_SUGGESTION_THRESHOLD,
            total_dataset_size=total_examples,
            class_distribution=dict(class_counts),
        )

        # Evaluate active model on the exact same holdout split if active model exists
        active_pipeline = ml_model_access.load_active_model()
        active_metrics: Optional[MLEvaluationMetrics] = None
        if active_pipeline is not None:
            try:
                active_metrics = evaluate_classifier(
                    pipeline=active_pipeline,
                    X_test=X_test,
                    y_test=y_test,
                    baseline=baseline,
                    merchants_test=m_test,
                    threshold=DEFAULT_SUGGESTION_THRESHOLD,
                    total_dataset_size=total_examples,
                    class_distribution=dict(class_counts),
                )
            except Exception as exc:
                logger.warning("Active model failed holdout evaluation on candidate split: %s", exc)

        passes_criteria, reason = should_activate_candidate(
            candidate_metrics=metrics,
            active_metrics=active_metrics,
            active_accuracy=float(meta.accuracy) if meta.accuracy is not None else None,
        )

        if not passes_criteria and not force:
            meta.status_message = reason
            meta.model_available = False if not ml_model_access.artifact_exists() else meta.model_available
            db.add(meta)
            db.commit()
            return False, reason, False, get_ml_status(db)

        # Fit final pipeline on all available examples before serialization
        final_pipeline = create_ml_pipeline(random_state=DEFAULT_RANDOM_STATE)
        final_pipeline.fit(X_texts, y_labels)

        # Serialize candidate to temp file and validate load
        temp_path = ml_model_access.save_candidate_model(final_pipeline)

        # Atomically activate candidate
        ml_model_access.activate_candidate_model(temp_path)
        temp_path = None

        # Update metadata
        ml_model_access.update_model_metadata_after_training(
            db=db,
            trained_revision=meta.current_training_revision,
            training_example_count=total_examples,
            model_available=True,
            accuracy=metrics.accuracy,
            macro_f1=metrics.macro_f1,
            top2_accuracy=metrics.top2_accuracy,
            coverage=metrics.coverage,
            status_message=f"Trained on {total_examples} examples (Accuracy: {metrics.accuracy:.1%}, F1: {metrics.macro_f1:.2f})",
        )
        db.commit()

        success_msg = (
            f"Model successfully trained and activated with {total_examples} examples "
            f"across {distinct_categories} categories. Test Accuracy: {metrics.accuracy:.1%}, "
            f"Macro F1: {metrics.macro_f1:.2f}, Baseline Accuracy: {metrics.baseline_accuracy:.1%}."
        )
        return True, success_msg, True, get_ml_status(db)

    except Exception as exc:
        db.rollback()
        if temp_path:
            ml_model_access.cleanup_temp_candidate(temp_path)
        logger.exception("ML model training failed: %s", exc)
        return False, f"Training failed: {exc}", False, get_ml_status(db)


def ensure_model_freshness(db: Session) -> None:
    """
    Checks if model retraining is due:
    - Model artifact missing or model not available while sufficient data exists.
    - Training revision delta >= RETRAIN_THRESHOLD.
    Executes retraining synchronously if due. Failure is non-fatal to prediction caller.
    """
    meta = ml_model_access.get_model_metadata(db)
    has_artifact = ml_model_access.artifact_exists()
    new_labels = max(0, meta.current_training_revision - meta.trained_revision)

    is_due = (not has_artifact or not meta.model_available or new_labels >= RETRAIN_THRESHOLD)
    if is_due:
        retrain_model(db)


def predict_category_for_transaction(
    db: Session,
    transaction_id: UUID,
) -> schemas.TransactionCategorySuggestionRead:
    """
    Coordinates category suggestion workflow for a single transaction.
    Enforces strict precedence:
    1. Existing category -> No suggestion (already categorized).
    2. Confirmed transfer -> Excluded from ML.
    3. Deterministic Phase 9 rule matches -> Rule takes precedence; no competing ML suggestion.
    4. Model freshness check (synchronous retrain if stale beyond threshold).
    5. Local active model inference -> suggestion if confidence >= threshold, else abstention.
    """
    tx = transaction_access.get_transaction_by_id(db, transaction_id)
    if not tx:
        return schemas.TransactionCategorySuggestionRead(
            transaction_id=transaction_id,
            reason="Transaction not found",
        )

    # 1. Existing category takes absolute precedence
    if tx.category_id is not None:
        return schemas.TransactionCategorySuggestionRead(
            transaction_id=transaction_id,
            reason="Transaction already has an explicit category assigned",
        )

    # 2. Confirmed transfers are excluded
    if getattr(tx, "is_transfer", False):
        return schemas.TransactionCategorySuggestionRead(
            transaction_id=transaction_id,
            reason="Confirmed transfers are excluded from ML categorization",
        )

    # 3. Deterministic Phase 9 rule takes precedence over ML
    if tx.merchant:
        rule = categorization_rule_access.get_rule_by_merchant(db, tx.merchant)
        if rule:
            return schemas.TransactionCategorySuggestionRead(
                transaction_id=transaction_id,
                reason=f"Matched deterministic rule for merchant '{rule.merchant}'",
            )

    # 4. Check freshness
    ensure_model_freshness(db)

    # 5. Load active model
    pipeline = ml_model_access.load_active_model()
    if pipeline is None:
        return schemas.TransactionCategorySuggestionRead(
            transaction_id=transaction_id,
            reason="No trained ML model is currently available",
        )

    # 6. Predict suggestion
    feature_text = build_feature_text(tx.merchant, tx.description)
    suggestion = predict_suggestion(
        pipeline=pipeline,
        feature_text=feature_text,
        threshold=DEFAULT_SUGGESTION_THRESHOLD,
    )

    if suggestion is None:
        return schemas.TransactionCategorySuggestionRead(
            transaction_id=transaction_id,
            reason="Model confidence is below suggestion threshold",
        )

    # Validate that suggested category currently exists
    try:
        cat_uuid = UUID(suggestion.category_id)
    except ValueError:
        return schemas.TransactionCategorySuggestionRead(
            transaction_id=transaction_id,
            reason="Invalid predicted category identifier",
        )

    cat = category_access.get_category_by_id(db, cat_uuid)
    if not cat or not cat.is_active:
        return schemas.TransactionCategorySuggestionRead(
            transaction_id=transaction_id,
            reason="Suggested category does not exist or is inactive",
        )

    return schemas.TransactionCategorySuggestionRead(
        transaction_id=transaction_id,
        suggested_category_id=cat.category_id,
        suggested_category_name=cat.name,
        confidence=suggestion.confidence,
        score_label=suggestion.score_label,
        reason="Suggested by model",
    )


def batch_predict_suggestions(
    db: Session,
    transaction_ids: Sequence[UUID],
) -> dict[UUID, schemas.TransactionCategorySuggestionRead]:
    """
    Batch suggestion workflow for multiple transactions:
    - Retrains at most once if stale.
    - Loads active model, rules lookup, and category names once into memory.
    - Returns mapping of transaction_id -> TransactionCategorySuggestionRead.
    """
    if not transaction_ids:
        return {}

    # Check model freshness once before batch loop
    ensure_model_freshness(db)

    pipeline = ml_model_access.load_active_model()
    rules_lookup = categorization_rule_access.get_rules_lookup_dict(db)
    all_categories = {c.category_id: c for c in category_access.list_categories(db)}

    results: dict[UUID, schemas.TransactionCategorySuggestionRead] = {}

    for tx_id in transaction_ids:
        tx = transaction_access.get_transaction_by_id(db, tx_id)
        if not tx:
            results[tx_id] = schemas.TransactionCategorySuggestionRead(
                transaction_id=tx_id,
                reason="Transaction not found",
            )
            continue

        if tx.category_id is not None:
            results[tx_id] = schemas.TransactionCategorySuggestionRead(
                transaction_id=tx_id,
                reason="Transaction already has an explicit category assigned",
            )
            continue

        if getattr(tx, "is_transfer", False):
            results[tx_id] = schemas.TransactionCategorySuggestionRead(
                transaction_id=tx_id,
                reason="Confirmed transfers are excluded from ML categorization",
            )
            continue

        if tx.merchant:
            clean_key = clean_merchant_key(tx.merchant)
            if clean_key and clean_key in rules_lookup:
                results[tx_id] = schemas.TransactionCategorySuggestionRead(
                    transaction_id=tx_id,
                    reason=f"Matched deterministic rule for merchant '{tx.merchant}'",
                )
                continue

        if pipeline is None:
            results[tx_id] = schemas.TransactionCategorySuggestionRead(
                transaction_id=tx_id,
                reason="No trained ML model is currently available",
            )
            continue

        feature_text = build_feature_text(tx.merchant, tx.description)
        suggestion = predict_suggestion(
            pipeline=pipeline,
            feature_text=feature_text,
            threshold=DEFAULT_SUGGESTION_THRESHOLD,
        )

        if suggestion is None:
            results[tx_id] = schemas.TransactionCategorySuggestionRead(
                transaction_id=tx_id,
                reason="Model confidence is below suggestion threshold",
            )
            continue

        try:
            cat_uuid = UUID(suggestion.category_id)
        except ValueError:
            results[tx_id] = schemas.TransactionCategorySuggestionRead(
                transaction_id=tx_id,
                reason="Invalid predicted category identifier",
            )
            continue

        cat = all_categories.get(cat_uuid)
        if not cat or not cat.is_active:
            results[tx_id] = schemas.TransactionCategorySuggestionRead(
                transaction_id=tx_id,
                reason="Suggested category does not exist or is inactive",
            )
            continue

        results[tx_id] = schemas.TransactionCategorySuggestionRead(
            transaction_id=tx_id,
            suggested_category_id=cat.category_id,
            suggested_category_name=cat.name,
            confidence=suggestion.confidence,
            score_label=suggestion.score_label,
            reason="Suggested by model",
        )

    return results


def accept_suggestion(
    db: Session,
    transaction_id: UUID,
    category_id: UUID,
) -> models.Transaction:
    """
    Accepts an ML category suggestion for a transaction:
    - Sets Transaction.category_id to the accepted category.
    - Sets Transaction.category_source to 'ml' for human-confirmed label provenance.
    - Increments current_training_revision.
    - Commits the transaction atomically.
    - Preserves review status, merchant, and financial fields.
    """
    tx = transaction_access.get_transaction_by_id(db, transaction_id)
    if not tx:
        raise ValueError(f"Transaction {transaction_id} not found.")

    cat = category_access.get_category_by_id(db, category_id)
    if not cat:
        raise ValueError(f"Category {category_id} not found.")

    tx.category_id = category_id
    tx.category_source = "ml"
    ml_model_access.increment_training_revision(db)

    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx
