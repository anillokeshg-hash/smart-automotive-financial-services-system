# Smart Automotive Financial Services System

A simple base project for a vehicle-finance company: loans, EMIs, repayments, insurance and reporting.

## Features
- Vehicle catalog and customer records (income, credit score, existing EMIs)
- EMI calculator and credit-score based interest rates
- Automated loan decision with clear rejection reasons (credit score, down payment, debt-to-income)
- Full amortization (repayment) schedule
- Installment payments with outstanding-balance tracking and automatic loan closure
- Insurance premium quotes (depreciated insured value, no-claim bonus, GST)
- Portfolio report: approval rate, disbursed, collected and outstanding amounts

## Requirements
- Python 3.8 or newer (standard library only, uses SQLite)

## How to run

    python smart_auto_finance.py          # interactive menu (creates auto_finance.db)
    python smart_auto_finance.py --demo   # full sample walkthrough, nothing saved

## Business rules (edit at the top of the file)
- Minimum credit score 600; rate from 8.5% (score 750+) to 13.5% (600-649)
- Minimum down payment 10%; tenure 12-84 months
- (Existing EMIs + new EMI) must not exceed 50% of monthly income
- Insurance GST 18%

## Ideas to extend
Add a web or mobile front end, document upload and KYC checks, late-payment penalties,
loan foreclosure, or a real credit-bureau API.
