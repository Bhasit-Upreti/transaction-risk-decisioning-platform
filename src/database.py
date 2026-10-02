"""
Database Layer Module.
Manages SQLite storage for transactions, validation logs, risk decisions,
granular rule outcomes, and manual analyst reviews.
"""

from typing import List, Dict, Any, Optional, Set
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager
import sqlite3
import pandas as pd
from config import DATABASE_PATH


class DatabaseManager:
    """Manages SQLite schema creation, data insertion, and analytical queries."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DATABASE_PATH
        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        """Returns a SQLite connection with dict-like row access and foreign key enforcement."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    @contextmanager
    def transaction(self):
        """Context manager for atomic database transaction management."""
        conn = self.get_connection()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self) -> None:
        """Creates database tables and indexes if they do not exist."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 1. Transactions Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                transaction_id TEXT PRIMARY KEY,
                customer_id TEXT NOT NULL,
                amount REAL NOT NULL,
                currency TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                merchant_category TEXT NOT NULL,
                country TEXT NOT NULL,
                payment_method TEXT NOT NULL,
                customer_avg_amount REAL,
                customer_home_country TEXT,
                source TEXT DEFAULT 'unknown',
                created_at TEXT NOT NULL
            );
            """)

            # 2. Validation Results Table (Rejection and Quality log)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS validation_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_id TEXT,
                is_valid INTEGER NOT NULL,
                error_count INTEGER DEFAULT 0,
                error_reasons TEXT,
                raw_payload TEXT,
                source TEXT DEFAULT 'unknown',
                processed_at TEXT NOT NULL
            );
            """)

            # 3. Decisions Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS decisions (
                transaction_id TEXT PRIMARY KEY,
                risk_score INTEGER NOT NULL,
                decision TEXT NOT NULL,
                action_note TEXT,
                triggered_rule_ids TEXT,
                decision_explanation TEXT,
                rule_version TEXT,
                decision_timestamp TEXT NOT NULL,
                FOREIGN KEY (transaction_id) REFERENCES transactions (transaction_id)
            );
            """)

            # 4. Granular Rule Outcomes Table (For auditability)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS rule_evaluations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_id TEXT NOT NULL,
                rule_id TEXT NOT NULL,
                rule_name TEXT NOT NULL,
                triggered INTEGER NOT NULL,
                points INTEGER NOT NULL,
                reason TEXT,
                threshold_info TEXT,
                status TEXT DEFAULT 'evaluated',
                evaluated_at TEXT NOT NULL,
                FOREIGN KEY (transaction_id) REFERENCES transactions (transaction_id)
            );
            """)

            # 5. Reviews Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                transaction_id TEXT PRIMARY KEY,
                review_status TEXT DEFAULT 'Pending',
                reviewer_outcome TEXT,
                review_note TEXT,
                reviewer_name TEXT,
                reviewed_at TEXT,
                FOREIGN KEY (transaction_id) REFERENCES transactions (transaction_id)
            );
            """)

            # Create Indexes for fast querying
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_txn_cust ON transactions(customer_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_txn_ts ON transactions(timestamp);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_dec_status ON decisions(decision);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_val_valid ON validation_results(is_valid);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_rev_status ON reviews(review_status);")

            # Schema migrations — safely add columns that may be absent in older DB files
            try:
                cursor.execute(
                    "ALTER TABLE rule_evaluations ADD COLUMN status TEXT DEFAULT 'evaluated';"
                )
            except sqlite3.OperationalError:
                # Column already exists — nothing to do
                pass

            conn.commit()

    def get_existing_transaction_ids(self) -> Set[str]:
        """Returns set of all existing transaction IDs to prevent duplicate insertion."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT transaction_id FROM transactions")
            rows = cursor.fetchall()
            return {row["transaction_id"] for row in rows if row["transaction_id"]}

    def save_valid_transactions(self, valid_df: pd.DataFrame, conn: Optional[sqlite3.Connection] = None) -> int:
        """
        Saves valid transactions into the database using INSERT (immutable transactions).
        Raises sqlite3.IntegrityError on duplicate IDs to prevent silent overwriting.
        """
        if valid_df.empty:
            return 0

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        inserted = 0

        def _do_insert(c):
            nonlocal inserted
            cursor = c.cursor()
            for _, row in valid_df.iterrows():
                cust_avg = row.get("customer_avg_amount")
                cust_avg_val = float(cust_avg) if cust_avg is not None and not pd.isna(cust_avg) else None

                cursor.execute("""
                INSERT INTO transactions (
                    transaction_id, customer_id, amount, currency, timestamp,
                    merchant_category, country, payment_method, customer_avg_amount,
                    customer_home_country, source, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(row["transaction_id"]),
                    str(row["customer_id"]),
                    float(row["amount"]),
                    str(row["currency"]),
                    str(row["timestamp"]),
                    str(row["merchant_category"]),
                    str(row["country"]),
                    str(row["payment_method"]),
                    cust_avg_val,
                    str(row.get("customer_home_country", row["country"])),
                    str(row.get("source", "unknown")),
                    now_str,
                ))
                inserted += 1

        if conn is not None:
            _do_insert(conn)
        else:
            with self.transaction() as c:
                _do_insert(c)

        return inserted

    def save_validation_results(self, invalid_df: pd.DataFrame, valid_count: int = 0) -> int:
        """Saves validation failure logs and audit summaries into validation_results."""
        inserted = 0
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with self.get_connection() as conn:
            cursor = conn.cursor()
            if not invalid_df.empty:
                for _, row in invalid_df.iterrows():
                    cursor.execute("""
                    INSERT INTO validation_results (
                        transaction_id, is_valid, error_count, error_reasons, raw_payload, source, processed_at
                    ) VALUES (?, 0, ?, ?, ?, ?, ?)
                    """, (
                        str(row.get("transaction_id", "UNKNOWN")),
                        int(row.get("error_count", 1)),
                        str(row.get("error_reasons", "Validation failure")),
                        str(row.get("raw_payload", "{}")),
                        str(row.get("source", "unknown")),
                        now_str,
                    ))
                    inserted += 1
            conn.commit()
        return inserted

    def save_decisions(self, decisions_df: pd.DataFrame, conn: Optional[sqlite3.Connection] = None) -> int:
        """Saves decision records and auto-creates pending review entries for Review decisions."""
        if decisions_df.empty:
            return 0

        inserted = 0

        def _do_save(c):
            nonlocal inserted
            cursor = c.cursor()
            for _, row in decisions_df.iterrows():
                tx_id = str(row["transaction_id"])
                dec_val = str(row["decision"])
                cursor.execute("""
                INSERT OR REPLACE INTO decisions (
                    transaction_id, risk_score, decision, action_note,
                    triggered_rule_ids, decision_explanation, rule_version, decision_timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    tx_id,
                    int(row["risk_score"]),
                    dec_val,
                    str(row.get("action_note", "")),
                    str(row.get("triggered_rule_ids", "")),
                    str(row.get("decision_explanation", "")),
                    str(row.get("rule_version", "v1.0.0")),
                    str(row.get("decision_timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))),
                ))

                # Initialize review record if it does not exist
                initial_status = "Pending" if dec_val == "Review" else ("Auto-Declined" if dec_val == "Decline" else "Auto-Approved")
                cursor.execute("""
                INSERT OR IGNORE INTO reviews (
                    transaction_id, review_status, reviewer_outcome, review_note, reviewer_name, reviewed_at
                ) VALUES (?, ?, NULL, NULL, NULL, NULL)
                """, (tx_id, initial_status))

                inserted += 1

        if conn is not None:
            _do_save(conn)
        else:
            with self.transaction() as c:
                _do_save(c)

        return inserted

    def save_rule_evaluations(self, tx_id: str, rule_outcomes: List[Any], conn: Optional[sqlite3.Connection] = None) -> None:
        """Saves granular rule outcome details for audit inspection."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        def _do_save(c):
            cursor = c.cursor()
            cursor.execute("DELETE FROM rule_evaluations WHERE transaction_id = ?", (tx_id,))
            for outcome in rule_outcomes:
                cursor.execute("""
                INSERT INTO rule_evaluations (
                    transaction_id, rule_id, rule_name, triggered, points, reason, threshold_info, status, evaluated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    tx_id,
                    outcome.rule_id,
                    outcome.name,
                    1 if outcome.triggered else 0,
                    outcome.points,
                    outcome.reason,
                    outcome.threshold_info,
                    getattr(outcome, "status", "evaluated"),
                    now_str,
                ))

        if conn is not None:
            _do_save(conn)
        else:
            with self.transaction() as c:
                _do_save(c)

    def save_processed_batch(
        self,
        valid_df: pd.DataFrame,
        decisions_df: pd.DataFrame,
        batch_outcomes: List[List[Any]],
    ) -> None:
        """
        Atomically saves valid transactions, decisions, and granular rule evaluations
        in a single database transaction. If any write fails, all are rolled back.
        """
        if valid_df.empty:
            return

        with self.transaction() as conn:
            self.save_valid_transactions(valid_df, conn=conn)
            self.save_decisions(decisions_df, conn=conn)
            for idx, row in valid_df.reset_index(drop=True).iterrows():
                tx_id = str(row["transaction_id"])
                outcomes = batch_outcomes[idx]
                self.save_rule_evaluations(tx_id, outcomes, conn=conn)

    def record_review(
        self,
        transaction_id: str,
        review_status: str,
        reviewer_outcome: str,
        review_note: str,
        reviewer_name: str = "Risk Analyst"
    ) -> bool:
        """Records an analyst manual review outcome."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO reviews (
                transaction_id, review_status, reviewer_outcome, review_note, reviewer_name, reviewed_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                transaction_id,
                review_status,
                reviewer_outcome,
                review_note,
                reviewer_name,
                now_str,
            ))
            conn.commit()
            return cursor.rowcount > 0

    def get_full_transactions(self) -> pd.DataFrame:
        """Fetches joined transaction, decision, and review details."""
        query = """
        SELECT 
            t.transaction_id,
            t.customer_id,
            t.amount,
            t.currency,
            t.timestamp,
            t.merchant_category,
            t.country,
            t.payment_method,
            t.customer_avg_amount,
            t.customer_home_country,
            t.source,
            d.risk_score,
            d.decision,
            d.action_note,
            d.triggered_rule_ids,
            d.decision_explanation,
            d.rule_version,
            d.decision_timestamp,
            COALESCE(r.review_status, 'None') AS review_status,
            r.reviewer_outcome,
            r.review_note,
            r.reviewer_name,
            r.reviewed_at
        FROM transactions t
        LEFT JOIN decisions d ON t.transaction_id = d.transaction_id
        LEFT JOIN reviews r ON t.transaction_id = r.transaction_id
        ORDER BY t.timestamp DESC
        """
        with self.get_connection() as conn:
            return pd.read_sql_query(query, conn)

    def get_transaction_details(self, transaction_id: str) -> Optional[Dict[str, Any]]:
        """Returns complete inspection details for a single transaction."""
        query = """
        SELECT 
            t.*,
            d.risk_score,
            d.decision,
            d.action_note,
            d.triggered_rule_ids,
            d.decision_explanation,
            d.rule_version,
            d.decision_timestamp,
            r.review_status,
            r.reviewer_outcome,
            r.review_note,
            r.reviewer_name,
            r.reviewed_at
        FROM transactions t
        LEFT JOIN decisions d ON t.transaction_id = d.transaction_id
        LEFT JOIN reviews r ON t.transaction_id = r.transaction_id
        WHERE t.transaction_id = ?
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (transaction_id,))
            row = cursor.fetchone()
            if not row:
                return None
            result = dict(row)

            # Also fetch granular rule evaluations
            cursor.execute("""
            SELECT rule_id, rule_name, triggered, points, reason, threshold_info, status, evaluated_at
            FROM rule_evaluations
            WHERE transaction_id = ?
            ORDER BY rule_id ASC
            """, (transaction_id,))
            result["rule_evaluations"] = [dict(r) for r in cursor.fetchall()]
            return result

    def get_validation_failures(self) -> pd.DataFrame:
        """Returns all logged rejected records."""
        query = """
        SELECT id, transaction_id, error_count, error_reasons, raw_payload, source, processed_at
        FROM validation_results
        WHERE is_valid = 0
        ORDER BY processed_at DESC
        """
        with self.get_connection() as conn:
            return pd.read_sql_query(query, conn)

    def get_review_queue(self, status_filter: Optional[str] = None) -> pd.DataFrame:
        """Returns transactions queued for review."""
        base_query = """
        SELECT 
            t.transaction_id,
            t.customer_id,
            t.amount,
            t.currency,
            t.timestamp,
            t.merchant_category,
            t.country,
            t.customer_avg_amount,
            t.customer_home_country,
            d.risk_score,
            d.decision,
            d.triggered_rule_ids,
            d.decision_explanation,
            COALESCE(r.review_status, 'Pending') AS review_status,
            r.reviewer_outcome,
            r.review_note,
            r.reviewer_name,
            r.reviewed_at
        FROM transactions t
        JOIN decisions d ON t.transaction_id = d.transaction_id
        LEFT JOIN reviews r ON t.transaction_id = r.transaction_id
        WHERE d.decision = ?
        """
        params = ["Review"]
        if status_filter and status_filter != "All":
            base_query += " AND COALESCE(r.review_status, 'Pending') = ?"
            params.append(status_filter)

        base_query += " ORDER BY d.risk_score DESC, t.timestamp DESC"

        with self.get_connection() as conn:
            return pd.read_sql_query(base_query, conn, params=params)

    def clear_all_data(self) -> None:
        """Resets all database tables for a clean slate."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM rule_evaluations")
            cursor.execute("DELETE FROM reviews")
            cursor.execute("DELETE FROM decisions")
            cursor.execute("DELETE FROM validation_results")
            cursor.execute("DELETE FROM transactions")
            conn.commit()


# Singleton instance helper
_db_manager: Optional[DatabaseManager] = None

def get_db() -> DatabaseManager:
    """Returns singleton DatabaseManager instance."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager
