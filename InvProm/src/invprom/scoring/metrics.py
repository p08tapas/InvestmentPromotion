from __future__ import annotations


def net_cash_cr(
    cash_cr: float | None,
    investments_cr: float | None,
    total_debt_cr: float | None,
) -> float | None:
    if cash_cr is None:
        return None
    investments = investments_cr or 0.0
    debt = total_debt_cr or 0.0
    return cash_cr + investments - debt


def net_cash_to_market_cap(net_cash: float | None, market_cap_cr: float | None) -> float | None:
    if net_cash is None or market_cap_cr is None or market_cap_cr <= 0:
        return None
    return net_cash / market_cap_cr


def order_book_growth(order_book_cr: float | None, order_book_prev_yr_cr: float | None) -> float | None:
    if order_book_cr is None or order_book_prev_yr_cr is None or order_book_prev_yr_cr == 0:
        return None
    return (order_book_cr - order_book_prev_yr_cr) / abs(order_book_prev_yr_cr)
