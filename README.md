# Transaction Risk Decisioning & Data Quality Platform

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Framework-Streamlit-FF4B4B.svg)](https://streamlit.io/)
[![Tests](https://img.shields.io/badge/Tests-22%20Passed-brightgreen.svg)]()
[![License](https://img.shields.io/badge/License-MIT-green.svg)]()

> An educational fintech prototype simulating how real-world financial systems ingest transactions, enforce rigorous data quality checks, evaluate transparent business rules, compute explainable risk scores, persist audit trails, and manage human-in-the-loop review queues.

---

## 1. Project Overview

The **Transaction Risk Decisioning & Data Quality Platform** demonstrates the complete operational lifecycle of modern payment and risk engineering. Rather than simply fitting a black-box machine-learning classifier, this system focuses on the **governance, auditability, data quality, explainability, and analyst operations** essential for production payment platforms.

The platform processes synthetic transactions with intuitive fields (`customer_id`, `amount`, `country`, `merchant_category`, `timestamp`, `payment_method`) to illustrate rule triggers, decision bands, and operational metrics.

> **Disclaimer:** This application is strictly an educational prototype. It does not connect to real card networks or financial institutions and must not be used for real credit, payment, or fraud determinations.

---

## 2. Problem Statement

In production payment systems, labeling a transaction as fraud is only one small part of the problem. A dependable platform must:

1. **Ingest diverse data streams** (batch CSV uploads, streaming feeds).
2. **Enforce data quality & schema validation** before running expensive rule engines.
3. **Isolate malformed payloads** with explicit rejection reasons without halting good traffic.
4. **Evaluate transparent, configurable business rules** without hidden logic.
5. **Compute an explainable risk score** and assign deterministic outcomes (`Approve`, `Review`, `Decline`).
6. **Persist end-to-end audit trails** in a durable relational database.
7. **Empower fraud and risk analysts** with a specialized manual review queue.

---

## 3. Key Features

- **Automated Ingestion & Synthetic Data Engine:**
  - Configurable transaction generator producing normal patterns, velocity spikes, high-value transfers, cross-border payments, and intentional data defects.
  - CSV file ingestion with column mapping and standardization.
- **Strict Data Quality & Validation Gatekeeper:**
  - Completeness checks for required fields.
  - Value boundary checks (e.g., numeric amounts $> 0$, non-negative averages).
  - Referential and ISO format checks (currency, country, payment method, merchant category).
  - Batch-level and database-level duplicate transaction ID detection.
  - Isolated rejection logging with raw JSON payload retention and root-cause breakdowns.
- **Transparent Business Rule Engine:**
  - **R001 — High-Value Amount (+30 pts):** Triggers on transactions $\ge$ configurable threshold.
  - **R002 — Unusual Spike vs. Customer Average (+25 pts):** Triggers when amount is $\ge 3.0\times$ typical average with minimum absolute excess.
  - **R003 — Rapid Velocity (+25 pts):** Triggers when transaction count within a sliding time window (e.g. 30 mins) exceeds threshold.
  - **R004 — Country Mismatch (+20 pts):** Detects cross-border transactions differing from registered home country.
  - **R005 — High-Risk Merchant Category (+15 pts):** Flags high-risk industries (e.g., Crypto, Gambling).
- **Explainable Scoring & Decision Engine:**
  - Cumulative risk score bounded strictly between 0 and 100.
  - Decision bands:
    - **0 – 29: Approve** (Low risk, automated settlement)
    - **30 – 69: Review** (Medium risk, routed to analyst review queue)
    - **70 – 100: Decline** (High risk, automated restriction)
  - Every decision includes human-readable policy explanations linking directly to triggered rules.
- **Multi-Page Streamlit Operations Dashboard:**
  - **Executive Overview (`app.py`):** Real-time KPI metric cards, decision breakdown donuts, risk score distributions, hourly volume timeline, and rule frequency charts.
  - **Transaction Explorer (`pages/1_Transaction_Explorer.py`):** Multi-facet filtering, ID search, and granular transaction inspector with individual rule outcomes.
  - **Data Quality Observatory (`pages/2_Data_Quality.py`):** Rejection log viewer, raw JSON payload debugger, rejection root-cause charts, and CSV export.
  - **Manual Review Queue (`pages/3_Manual_Review.py`):** Dedicated analyst workbench to review flagged transactions, compare customer profile anomalies, log determinations (`Approved`, `Declined`, `Escalated`), and record audit notes.
- **Durable SQLite Storage Layer:**
  - Relational schema managing `transactions`, `validation_results`, `decisions`, `rule_evaluations`, and `reviews`.
  - Idempotent upserts and full relational integrity.

---

## 4. Technology Stack

| Technology | Purpose | Rationale |
|---|---|---|
| **Python 3.10+** | Application and engine logic | Clean, type-annotated, modular, and maintainable. |
| **Streamlit** | Interactive UI and multi-page dashboard | Rapid, modern web interfaces for operational workflows. |
| **Pandas** | Tabular data manipulation | High-performance transformation, filtering, and aggregation. |
| **SQLite** | Relational local database | Lightweight, zero-config relational persistence with full SQL capabilities. |
| **Plotly** | Dynamic data visualizations | High-fidelity interactive charts with responsive tooltips. |
| **pytest** | Automated test suite | Comprehensive unit, boundary, rule, and workflow test coverage. |

---

## 5. System Architecture

```text
                  CSV Upload / Synthetic Generator
                                |
                                v
                       Transaction Ingestion
                                |
                                v
                        Data Validation
                         /            \
                        /              \
           [Invalid Records]       [Valid Records]
                  |                       |
                  v                       v
         validation_results      Business Rule Engine
            (SQLite DB)         (R001 - R005 Evaluation)
                                          |
                                          v
                                Risk Score Calculator
                                (Capped Range: 0 - 100)
                                          |
                                          v
                                   Decision Engine
                                (Approve/Review/Decline)
                                          |
                                          v
                                    SQLite Storage
                            (transactions, decisions, reviews)
                                    /           \
                                   /             \
                                  v               v
                         Monitoring Dashboard   Analyst Review Queue
```

---

## 6. Transaction Workflow

```text
1. Ingest Raw Record  --> Clean headers, assign origin source
2. Validate Schema    --> Check types, ranges, duplicates, required columns
                          |--> FAIL: Log to rejection table with reason & raw payload
                          +--> PASS: Continue to risk engine
3. Evaluate Rules     --> Run R001 to R005; generate RuleOutcome objects
4. Compute Score      --> Sum triggered points; clamp to [0, 100]
5. Map Decision       --> Map score to Approve, Review, or Decline
6. Persist State      --> Store transaction, decision, and pending review in SQLite
7. Operations UI      --> Display live charts, inspect records, execute analyst reviews
```

---

## 7. Business Rules and Scoring Approach

| Rule ID | Name | Trigger Condition | Points |
|---|---|---|---:|
| **R001** | High-Value Amount | $\text{Amount} \ge ₹15,000.00$ | 30 |
| **R002** | Spike vs Customer Average | $\text{Amount} \ge 3.0\times \text{Avg} \text{ and } (\text{Amount} - \text{Avg}) \ge ₹2,000$ | 25 |
| **R003** | Rapid Velocity | $\ge 3\text{ transactions within 30 minutes}$ for same customer | 25 |
| **R004** | Country Mismatch | $\text{Origin Country} \ne \text{Home Country}$ | 20 |
| **R005** | High-Risk Category | Merchant category in `['Crypto', 'Gambling']` | 15 |

### Scoring Formula:
$$\text{risk\_score} = \min\left( \sum_{i \in \text{Triggered}} \text{points}_i, \; 100 \right)$$

### Decision Thresholds:
- **$0 \le \text{Score} < 30 \implies$ Approve:** Standard transaction, low risk indicator.
- **$30 \le \text{Score} < 70 \implies$ Review:** Elevated anomaly, queued for analyst review.
- **$70 \le \text{Score} \le 100 \implies$ Decline:** Extreme risk, multiple high-severity rule triggers.

---

## 8. Data Model

The SQLite database (`data/risk_platform.db`) consists of five interconnected tables:

1. **`transactions`:**
   - `transaction_id` (PK, TEXT)
   - `customer_id` (TEXT), `amount` (REAL), `currency` (TEXT), `timestamp` (TEXT)
   - `merchant_category` (TEXT), `country` (TEXT), `payment_method` (TEXT)
   - `customer_avg_amount` (REAL), `customer_home_country` (TEXT)
   - `source` (TEXT), `created_at` (TEXT)
2. **`validation_results`:**
   - `id` (PK, INTEGER AUTOINCREMENT)
   - `transaction_id` (TEXT), `is_valid` (INTEGER), `error_count` (INTEGER)
   - `error_reasons` (TEXT), `raw_payload` (TEXT), `source` (TEXT), `processed_at` (TEXT)
3. **`decisions`:**
   - `transaction_id` (PK, FK), `risk_score` (INTEGER), `decision` (TEXT)
   - `action_note` (TEXT), `triggered_rule_ids` (TEXT), `decision_explanation` (TEXT)
   - `rule_version` (TEXT), `decision_timestamp` (TEXT)
4. **`rule_evaluations`:**
   - `id` (PK, INTEGER AUTOINCREMENT), `transaction_id` (FK)
   - `rule_id` (TEXT), `rule_name` (TEXT), `triggered` (INTEGER), `points` (INTEGER)
   - `reason` (TEXT), `threshold_info` (TEXT), `evaluated_at` (TEXT)
5. **`reviews`:**
   - `transaction_id` (PK, FK), `review_status` (TEXT: Pending/Approved/Declined/Escalated)
   - `reviewer_outcome` (TEXT), `review_note` (TEXT), `reviewer_name` (TEXT), `reviewed_at` (TEXT)

---

## 9. Installation and Execution

### Prerequisites
- Python 3.10 or higher
- Git

### 1. Clone the Repository
```bash
git clone https://github.com/your-username/transaction-risk-platform.git
cd transaction-risk-platform
```

### 2. Set Up a Virtual Environment
```bash
# On Linux/macOS
python -m venv venv
source venv/bin/activate

# On Windows
python -m venv venv
.\venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the Streamlit Application
```bash
streamlit run app.py
```
Open your browser at `http://localhost:8501`.

---

## 10. Automated Testing

The project includes unit, boundary, and end-to-end integration tests using `pytest`.

To run the complete test suite:
```bash
pytest -v
```

### Test Coverage Highlights:
- **`test_validation.py`:** Valid passes, missing customer ID, negative/zero amounts, non-numeric values, malformed timestamps, batch duplicates, database duplicates, and invalid currency/country codes.
- **`test_rules.py`:** High-value thresholds, customer average multipliers, sliding-window velocity checks, cross-border mismatches, and high-risk categories.
- **`test_scoring.py`:** Zero-score conditions, additive scoring, and strict capping at 100 points.
- **`test_decision.py`:** Boundary mappings ($0, 29, 30, 69, 70, 100$) and human-readable explanation generation.
- **`test_workflow.py`:** End-to-end ingestion, defect isolation, SQLite persistence, and analyst review state transitions.

---

## 11. Limitations and Future Improvements

### Current Limitations:
- Utilizes synthetic data and simulated customer profiles.
- Single-node SQLite database intended for prototype and single-instance deployments.
- Synchronous batch processing rather than a distributed message streaming engine.

### Roadmap & Extensions:
- **FastAPI Microservice:** Expose `/api/v1/score` for real-time low-latency transaction processing.
- **Cloud Deployment:** Containerize with Docker and deploy to Google Cloud Run.
- **Message Broker Ingestion:** Integrate Apache Kafka or Google Cloud Pub/Sub for high-throughput streaming.
- **ML Shadow Scoring:** Compare rule-based decisions against a trained XGBoost/LightGBM model running in shadow mode.
- **Dynamic Rule Management UI:** Provide an administrative interface to configure thresholds and weights without code deployment.

---

## 12. Definition of Done Checklist

- [x] App starts locally with documented commands (`streamlit run app.py`).
- [x] User can generate synthetic transactions or upload CSV files.
- [x] Invalid data is rejected with explicit reasons and isolated from scoring.
- [x] Valid transactions are evaluated against transparent business rules.
- [x] Each processed transaction receives an explainable score and decision.
- [x] Application records triggered rules, explanations, and raw payloads.
- [x] Dashboard displays real-time operational and data-quality metrics.
- [x] Analysts can inspect transactions and record review outcomes.
- [x] All 22 automated tests pass with 100% success.
- [x] Clean repository free of secrets, credentials, or personal financial data.
