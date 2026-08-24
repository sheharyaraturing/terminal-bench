-- General ledger extract: month-end trading-fee expense postings, USD.
-- One journal line per active month, mapped from the exchange export by the
-- automated month-end feed. This is the book of record the desk notes say the
-- fee line has never been agreed to.
CREATE TABLE IF NOT EXISTS general_ledger_fee_postings (
    period      TEXT,
    journal_ref TEXT,
    account     TEXT,
    memo        TEXT,
    amount_usd  TEXT
);
INSERT INTO general_ledger_fee_postings (period, journal_ref, account, memo, amount_usd) VALUES
 ('2022-12','JE-2212-07','6200 Trading fees','Month-end trading fee accrual','4.77'),
 ('2023-01','JE-2301-07','6200 Trading fees','Month-end trading fee accrual','7.40'),
 ('2023-02','JE-2302-07','6200 Trading fees','Month-end trading fee accrual','7.91'),
 ('2023-03','JE-2303-07','6200 Trading fees','Month-end trading fee accrual','10.72'),
 ('2023-04','JE-2304-07','6200 Trading fees','Month-end trading fee accrual','11.44'),
 ('2023-05','JE-2305-07','6200 Trading fees','Month-end trading fee accrual','4.59'),
 ('2023-06','JE-2306-07','6200 Trading fees','Month-end trading fee accrual','5.24'),
 ('2023-07','JE-2307-07','6200 Trading fees','Month-end trading fee accrual','10.98'),
 ('2023-08','JE-2308-07','6200 Trading fees','Month-end trading fee accrual','4.25'),
 ('2023-09','JE-2309-07','6200 Trading fees','Month-end trading fee accrual','94.57'),
 ('2023-10','JE-2310-07','6200 Trading fees','Month-end trading fee accrual','15.87'),
 ('2023-11','JE-2311-07','6200 Trading fees','Month-end trading fee accrual','10.00'),
 ('2023-12','JE-2312-07','6200 Trading fees','Month-end trading fee accrual','15.87'),
 ('2024-01','JE-2401-07','6200 Trading fees','Month-end trading fee accrual','22.40');
