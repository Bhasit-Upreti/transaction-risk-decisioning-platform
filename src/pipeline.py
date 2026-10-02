"""
Transaction Processing Pipeline.
Orchestrates the complete workflow:
Transaction input -> Data validation -> Business rules -> Risk score -> Decision -> Storage.
"""

from typing import Dict, Any, Tuple
import pandas as pd

from src.validation import TransactionValidator
from src.rules import BusinessRuleEngine
from src.scoring import RiskScoreCalculator
from src.decision import DecisionEngine
from src.database import DatabaseManager, get_db


class TransactionPipeline:
    """End-to-end orchestrator for the transaction risk decisioning workflow."""

    def __init__(self, db: DatabaseManager = None):
        self.db = db or get_db()
        self.validator = TransactionValidator()
        self.rule_engine = BusinessRuleEngine()
        self.scoring_calc = RiskScoreCalculator()
        self.decision_engine = DecisionEngine()

    def process_transactions(self, raw_df: pd.DataFrame) -> Dict[str, Any]:
        """
        Processes a DataFrame of raw transactions through the entire decisioning lifecycle.

        Returns:
            Dict containing processing metrics, valid_df, invalid_df, and decisions_df.
        """
        if raw_df is None or raw_df.empty:
            return {
                "success": False,
                "message": "Input transaction batch is empty.",
                "valid_count": 0,
                "invalid_count": 0,
                "summary": {},
            }

        # 1. Fetch existing transaction IDs for deduplication
        existing_ids = self.db.get_existing_transaction_ids()

        # 2. Validation Step
        valid_df, invalid_df, val_summary = self.validator.validate_batch(
            raw_df, existing_tx_ids=existing_ids
        )

        # 3. Persist Validation Rejections
        if not invalid_df.empty:
            self.db.save_validation_results(invalid_df, valid_count=len(valid_df))

        # 4. If no valid transactions, finish early
        if valid_df.empty:
            return {
                "success": True,
                "message": f"Processed {len(raw_df)} records: 0 valid, {len(invalid_df)} rejected.",
                "valid_count": 0,
                "invalid_count": len(invalid_df),
                "valid_df": valid_df,
                "invalid_df": invalid_df,
                "decisions_df": pd.DataFrame(),
                "summary": val_summary,
            }

        # 5. Persist Valid Transactions
        self.db.save_valid_transactions(valid_df)

        # 6. Fetch historical context for velocity rule (prior transactions from DB)
        historical_context = self.db.get_full_transactions()

        # 7. Evaluate Business Rules
        batch_outcomes = self.rule_engine.evaluate_batch(
            valid_df, historical_context=historical_context
        )

        # 8. Calculate Risk Scores
        scores_data = [self.scoring_calc.calculate_score(outcomes) for outcomes in batch_outcomes]

        # 9. Generate Decisions
        decisions_df = self.decision_engine.process_batch(valid_df, batch_outcomes, scores_data)

        # 10. Persist Decisions and Granular Rule Evaluations
        self.db.save_decisions(decisions_df)

        for idx, row in valid_df.iterrows():
            tx_id = str(row["transaction_id"])
            outcomes = batch_outcomes[idx]
            self.db.save_rule_evaluations(tx_id, outcomes)

        decision_counts = decisions_df["decision"].value_counts().to_dict()

        return {
            "success": True,
            "message": f"Successfully processed {len(raw_df)} records: {len(valid_df)} approved/reviewed/declined, {len(invalid_df)} rejected.",
            "total_records": len(raw_df),
            "valid_count": len(valid_df),
            "invalid_count": len(invalid_df),
            "valid_df": valid_df,
            "invalid_df": invalid_df,
            "decisions_df": decisions_df,
            "decision_counts": decision_counts,
            "summary": val_summary,
        }
