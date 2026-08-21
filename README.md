# MFP — Merchant Financial Passport

**Turn Every Transaction into Financial Opportunity**

MFP (Merchant Financial Passport) is an AI-powered financial intelligence platform designed to help small merchants transform their business transaction data into meaningful financial insights.

The platform combines business data from sources such as POS systems, bank transactions, QR payments, delivery platforms, accounting systems, or uploaded files to build a unified **Merchant Financial Passport**.

---

## Problem

Small merchants may have real revenue and continuous business activity but still face difficulties accessing financial services because their business data is fragmented across multiple platforms.

For example:

* Sales data is stored in POS systems
* Payments are recorded in bank accounts or QR payment systems
* Delivery revenue is stored on delivery platforms
* Expenses may exist in accounting systems or bank statements

As a result, the merchant's overall financial situation may not be clearly represented.

---

## Solution

MFP connects and standardizes merchant business data to create a unified financial profile.

```text
Business Data
      ↓
Data Processing
      ↓
Merchant Financial Passport
      ↓
Alternative Credit Signal
      ↓
Cash Flow Forecast
      ↓
Financial Need Detection
      ↓
Financial Opportunity
```

MFP does **not replace financial institutions' credit decision systems**. Instead, it provides additional business insights and alternative signals that may help financial providers better understand merchant activity.

---

## Core Features

### Merchant Financial Passport

Creates a financial profile based on merchant business activity, including:

* Revenue
* Revenue Stability
* Cash Flow
* Business Growth
* Transaction Activity
* Expense Behaviour
* Business Continuity
* Income Channel Diversity

### Alternative Credit Signal

Analyzes merchant business behaviour to generate an explainable alternative financial signal using information such as:

* Revenue Stability
* Cash Flow Consistency
* Revenue Volatility
* Expense Ratio
* Transaction Frequency
* Business Continuity

### Cash Flow Forecasting

Uses historical income and expense data to forecast future cash flow and identify potential liquidity problems.

Example:

```text
Available Cash:          ฿5,000
Upcoming Supplier Cost: ฿12,000
Expected Income:        ฿20,000

Predicted Cash Flow Gap: ฿7,000
```

### Financial Need Detection

Detects when a merchant may experience a short-term cash flow gap and identifies the amount and expected timing.

### AI Financial Copilot

Transforms financial analytics into simple explanations for merchants.

Example:

> Your revenue remains stable, but upcoming supplier payments may create a ฿7,000 cash flow gap within the next three days.

### Financial Opportunity Matching

Matches detected financial needs with suitable financial products such as:

* Working Capital
* Early Cash / Revenue Advance
* Equipment Financing
* Supplier Financing

Financial provider integration is simulated during the prototype phase.

---

## AI Components

MFP currently focuses on the following AI components:

1. **Alternative Credit Signal Model**
2. **Cash Flow Forecasting Model**
3. **Cash Flow Gap / Financial Need Detection**
4. **AI Financial Copilot**

The core AI models are trained and evaluated independently before being integrated into the MFP platform.

---

## Data Sources

MFP is designed to support data from multiple sources:

```text
POS
Bank Transactions
QR Payments
Delivery Platforms
Accounting Systems
CSV / Excel Upload
Manual Business Data
```

A merchant does **not need to have a POS system** to use MFP.

All incoming data is cleaned and normalized into a standard internal data format before analysis.

---

## Technology Stack

### Frontend

* React
* Vite

### Backend

* Python
* FastAPI

### AI / Data

* Python
* Pandas
* NumPy
* Scikit-learn
* TensorFlow / Keras

### Database

* PostgreSQL

### Prototype Integration

* Mock POS API
* Mock Bank API
* Mock Financial Provider API

---

## Project Structure

```text
MFP-Merchant-Financial-Passport/
│
├── frontend/
│
├── backend/
│
├── ai/
│   ├── credit_signal/
│   ├── cashflow_forecast/
│   └── copilot/
│
├── data/
│   ├── raw/
│   ├── processed/
│   └── synthetic/
│
├── models/
├── notebooks/
├── docs/
├── tests/
│
└── README.md
```

---

## Prototype Scope

### Real Implementation

* Data preprocessing
* Data normalization
* Feature engineering
* Alternative Credit Signal
* Cash Flow Forecasting
* Cash Flow Gap Detection
* AI-generated financial insights

### Mock Implementation

* POS provider integration
* Bank API integration
* Delivery platform integration
* Financial product offers
* Loan approval
* Direct financial provider integration

---

## Project Goal

The goal of MFP is to demonstrate how merchant transaction data can be transformed from simple transaction records into useful financial intelligence.

```text
Transaction
    ↓
Financial Identity
    ↓
Alternative Credit Signal
    ↓
Financial Need
    ↓
Financial Opportunity
```

## Tagline

**MFP — Turn Every Transaction into Financial Opportunity**
