import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from quant_ko.broker.kis import KisClient  # noqa: E402

client = KisClient()
for d_str in ["20261029", "20261030", "20261031"]:
    orders = client.fetch_orders(date=d_str)
    print(f"Date {d_str} orders count: {len(orders)}")
    tot_buy = 0.0
    for o in orders:
        qty = int(o.get("order_qty") or 0)
        p = float(o.get("order_price") or 0.0)
        filled = int(o.get("filled_qty") or 0)
        tot_buy += filled * p
        print(f"  {o.get('name')}({o.get('ticker')}): {o.get('side')} qty={qty}, filled={filled}, price={p}")
    print(f"Date {d_str} total filled buy: {tot_buy:,.0f}원\n")
