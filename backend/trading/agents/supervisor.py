"""Training Supervisor agent — post-retraining analysis of WF results + drift."""

from __future__ import annotations

from trading.agents.base import BaseAgent, Insight


class TrainingSupervisor(BaseAgent):
    name = "supervisor"
    priority = "low"  # post-retrain review; not in the trade path
    system = (
        "You are ScalpFX Alpha, ML supervisor of ScalpFX. You receive walk-forward "
        "training results and drift metrics. Judge whether the new model is safe "
        "to gate live signals: watch for fold variance, precision collapse, PSI>0.25. "
        'Reply ONLY as JSON: {"title": str, "body": str (<=80 words), '
        '"severity": "info"|"warn"|"alert", "tags": [str]}'
    )

    def build_prompt(self, context: dict) -> str:
        return (
            f"Walk-forward folds:\n{context.get('folds_table')}\n\n"
            f"mean accuracy: {context.get('mean_accuracy')}\n"
            f"mean precision(long): {context.get('mean_precision')}\n"
            f"feature drift PSI: {context.get('psi')}\n"
            f"promoted: {context.get('promoted')}\n"
            f"champion history: {context.get('champions')}\n\n"
            "Produce assessment JSON."
        )

    def fallback(self, context: dict) -> Insight:
        acc = float(context.get("mean_accuracy") or 0)
        prec = float(context.get("mean_precision") or 0)
        psi = float(context.get("psi") or 0)
        promoted = bool(context.get("promoted"))

        issues = []
        if acc < 0.53:
            issues.append("accuracy barely above coin flip")
        if prec < 0.30:
            issues.append("long-precision weak")
        if psi > 0.25:
            issues.append(f"drift PSI={psi:.2f} > 0.25")
        severity = "alert" if len(issues) >= 2 else ("warn" if issues else "info")

        body = "[heuristic] " + (
            f"gate {'PROMOTED' if promoted else 'rejected'}; acc {acc:.3f}, prec {prec:.3f}, PSI {psi:.2f}. "
            + (f"Concerns: {'; '.join(issues)}." if issues else "No stability concerns.")
        )
        title = "Model gate: OK" if not issues else f"Model gate: {len(issues)} concern(s)"
        return Insight(
            agent=self.name,
            title=title,
            body=body,
            severity=severity,
            tags=["training", "promoted" if promoted else "rejected"],
            meta={"source": "fallback"},
        )
