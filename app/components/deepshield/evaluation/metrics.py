import reflex as rx


def metrics(
    labels: list[int],
    scores: list[float],
    threshold: float = 0.5,
    audio: bool = False,
) -> dict:
    import numpy as np
    from sklearn.metrics import (
        accuracy_score,
        balanced_accuracy_score,
        confusion_matrix,
        f1_score,
        precision_score,
        recall_score,
        roc_auc_score,
        roc_curve,
    )

    y, score = np.asarray(labels), np.asarray(scores, dtype=float)
    if (
        len(y) == 0
        or len(y) != len(score)
        or not np.isfinite(score).all()
        or not set(y).issubset({0, 1})
        or np.any((score < 0) | (score > 1))
    ):
        raise ValueError("Metrics require finite real labeled observations")
    predicted = score >= threshold
    tn, fp, fn, tp = confusion_matrix(y, predicted, labels=[0, 1]).ravel()
    both = len(set(y)) == 2
    result = {
        "samples": len(y),
        "threshold": threshold,
        "accuracy": float(accuracy_score(y, predicted)),
        "precision": float(precision_score(y, predicted, zero_division=0)),
        "recall": float(recall_score(y, predicted, zero_division=0)),
        "f1": float(f1_score(y, predicted, zero_division=0)),
        "macro_f1": float(
            f1_score(
                y, predicted, labels=[0, 1], average="macro", zero_division=0
            )
        ),
        "balanced_accuracy": float(balanced_accuracy_score(y, predicted))
        if both
        else None,
        "roc_auc": float(roc_auc_score(y, score)) if both else None,
        "confusion_matrix": [[int(tn), int(fp)], [int(fn), int(tp)]],
        "FAR": float(fn / (fn + tp)) if fn + tp else None,
        "FRR": float(fp / (fp + tn)) if fp + tn else None,
        "rate_semantics": "FAR: synthetic accepted as real; FRR: real rejected as synthetic; label 1=synthetic",
        "warnings": []
        if both
        else [
            "Single-class subset: ROC-AUC, EER, and balanced accuracy unavailable"
        ],
    }
    if audio:
        result["eer"] = None
        if both:
            fpr, tpr, _ = roc_curve(y, score)
            fnr = 1 - tpr
            difference = fpr - fnr
            right = int(np.flatnonzero(difference >= 0)[0])
            left = max(0, right - 1)
            weight = (
                0.0
                if difference[right] == difference[left]
                else -difference[left] / (difference[right] - difference[left])
            )
            result["eer"] = float(fpr[left] + weight * (fpr[right] - fpr[left]))
            result["eer_method"] = "linear_interpolation_empirical_ROC"
    return result
