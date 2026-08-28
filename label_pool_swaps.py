#!/usr/bin/env python3
"""
Label COPI/RISE swap direction (buy vs sell) in transaction_labels, for any
wallet_flow_events row that shares a tx_hash with one of the 19 known core
AMM pool addresses below.

REWRITE NOTE: the original version of this script queried one transaction
at a time in a Python loop (one SQL query per tx_hash). On a multi-million-
row table that was far too slow -- ran for 8+ hours without finishing, and
worse, only committed once at the very end, so an interruption at any point
lost all progress. This version replaces that with ONE batched SQL join per
pool (19 total statements), committing after each pool individually, so
progress is saved incrementally and interrupting it only loses at most the
one pool currently in flight.

Direction is read directly off the counterparty's OWN net_quantity sign for
that tx_hash/chain/token (not derived from the pool's side), so multi-party
transactions are handled correctly:
    net_quantity > 0  -> counterparty received tokens -> event_bucket = 'pool_buy'
    net_quantity < 0  -> counterparty sent tokens     -> event_bucket = 'pool_sell'
    net_quantity == 0 -> skipped (no-op row)

The pool address's OWN row is never labeled -- only counterparty rows. If a
tx touches two of our own listed pools at once (a routed multi-hop through
two known pools), neither pool address is labeled as a counterparty of the
other -- every known pool address on that chain is excluded from the
counterparty side of the join.

Scope, deliberately excluded (see chat discussion): routers, fee-collector
contracts, LP-reward distribution contracts, "floating liquidity" treasury
wallets, and the Uniswap V4 PoolManager (over-attribution risk, already
flagged in the Bucket 3 notes). Only true Pair/Pool reserve-holding
addresses are included below.

transaction_labels is treated as append-only / skip-if-exists: if a row
already has ANY label for that (chain, token, tx_hash, address), it is left
alone, never overwritten -- enforced via NOT EXISTS in the SQL itself, not
a separate check, so it's safe to re-run (including resuming a run that was
interrupted partway through).

Run directly against your live rise_ledger.db (per your instruction --
no clone this time).

Usage:
    python label_pool_swaps.py --rise-ledger-db rise_ledger.db
"""

import argparse
import sqlite3
import sys
import time
from pathlib import Path

# ---- The 19 confirmed core swap pools (Pair/Pool contracts only) ----
# (chain, address, label) -- chain values match wallet_flow_events.chain
# (lowercase: base | bnb | eth | cardano). EVM addresses are lowercase to
# match the DB's normalized address casing.
POOLS = [
    ("eth", "0xc4cc6ce52994415709fbb11e11a6488e438eae80", "RISE pool (Aerodrome)"),
    ("eth", "0xf1e27a727ccb4c77c9de39bae9e3b8603c861b98", "RISE/WETH pool (Uniswap V2)"),
    ("cardano", "addr1z84q0denmyep98ph3tmzwsmw0j7zau9ljmsqx6a4rvaau6urzvjxmjguxys4aqhyhvjrpkees2q32p498yk284xaph7s4369mx", "Minswap V2 Pool"),
    ("cardano", "addr1z84q0denmyep98ph3tmzwsmw0j7zau9ljmsqx6a4rvaau66j2c79gy9l76sdg0xwhd7r0c0kna0tycz4y5s6mlenh8pq777e2a", "Minswap V2 Pool"),
    ("cardano", "addr1z8snz7c4974vzdpxu65ruphl3zjdvtxw8strf2c2tmqnxzvrzvjxmjguxys4aqhyhvjrpkees2q32p498yk284xaph7syflvxx", "Minswap V1 Pool"),
    ("cardano", "addr1z8snz7c4974vzdpxu65ruphl3zjdvtxw8strf2c2tmqnxz2j2c79gy9l76sdg0xwhd7r0c0kna0tycz4y5s6mlenh8pq0xmsha", "Minswap V1 Pool"),
    ("bnb", "0x73eda54a43c6a3d08ee30b089ef4c1bc3d0d4d9b", "PancakePair"),
    ("bnb", "0xfe4708dc8b7600398580979eaa813e8c83fac303", "PancakePair"),
    ("bnb", "0x48e2bcbc74ce33d2c07c1c9fe3eb23d8f5ef8518", "PancakePair"),
    ("bnb", "0x65f295490bd696d7c5bdecc8cb43962c2aa806fc", "PancakePair"),
    ("bnb", "0xb15f162cfc5b08c3917381610db845e5c3264f4a", "PancakePair"),
    ("bnb", "0xe61559fead01f32e1230278fa3266d0a33754ca7", "PancakePair"),
    ("bnb", "0x0e339af4b39b4a15b38841a0757e043aa5e5689a", "PancakeV3Pool"),
    ("base", "0x9e6a565c2322f8646f2653352e771738a0ee75a3", "UniswapV2Pair"),
    ("base", "0xbe407ecd9e7377a2da6b79b09333ec0e9d81aff2", "CLPool"),
    ("base", "0xaab8c04f37343d961c1ce75dbffefabf8476ed72", "Pool"),
    ("base", "0x91de1baa4cfe8019efc4bc8810fa2c5bd667f282", "Pool"),
    ("base", "0x598b0ba6b3c02db6a475a73e570af9368235146c", "UniswapV3Pool"),
    ("base", "0xb08ac69305ddcedad9ba3e4dabccf63f544410f0", "UniswapV3Pool"),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rise-ledger-db", required=True, help="Path to rise_ledger.db")
    args = parser.parse_args()

    db_path = Path(args.rise_ledger_db)
    if not db_path.exists():
        sys.exit(f"rise ledger db not found: {db_path}")

    conn = sqlite3.connect(str(db_path))

    # A (chain, address) index doesn't exist in the base schema -- without it,
    # the query planner sometimes picks a bad join order for this self-join
    # pattern (confirmed via EXPLAIN QUERY PLAN during testing: it used the
    # less selective index as the outer loop). This index fixes that and is
    # safe/non-destructive -- purely additive, same ALTER-style safety as the
    # stake_address work.
    conn.execute("CREATE INDEX IF NOT EXISTS idx_wfe_chain_address ON wallet_flow_events (chain, address)")
    conn.commit()

    # all pool addresses grouped by chain, for the exclusion list per query
    pools_by_chain = {}
    for chain, addr, _ in POOLS:
        pools_by_chain.setdefault(chain, []).append(addr)

    total_inserted = 0

    for idx, (chain, pool_address, pool_label) in enumerate(POOLS, 1):
        exclude_addrs = pools_by_chain[chain]
        placeholders = ",".join("?" for _ in exclude_addrs)
        notes = f"Counterparty to {pool_label} ({pool_address})"

        start = time.time()

        # Materialize this pool's own (tx_hash, token) pairs into a small temp
        # table first, so the big join below has something tiny and indexed
        # to join against, instead of relying on the planner to figure out
        # the right order on a multi-million-row self-join.
        conn.execute("DROP TABLE IF EXISTS temp.pool_txs")
        conn.execute(
            "CREATE TEMP TABLE pool_txs AS "
            "SELECT DISTINCT tx_hash, token FROM wallet_flow_events WHERE chain = ? AND address = ?",
            (chain, pool_address),
        )
        conn.execute("CREATE INDEX temp.idx_pool_txs ON pool_txs (tx_hash, token)")
        pool_tx_count = conn.execute("SELECT COUNT(*) FROM temp.pool_txs").fetchone()[0]

        sql = f"""
            INSERT INTO transaction_labels (chain, token, tx_hash, address, event_bucket, confidence, notes)
            SELECT cp.chain, cp.token, cp.tx_hash, cp.address,
                   CASE WHEN cp.net_quantity > 0 THEN 'pool_buy' ELSE 'pool_sell' END,
                   'high',
                   ?
            FROM wallet_flow_events AS cp
            JOIN temp.pool_txs AS pt
              ON pt.tx_hash = cp.tx_hash AND pt.token = cp.token
            WHERE cp.chain = ?
              AND cp.address != ?
              AND cp.net_quantity != 0
              AND cp.address NOT IN ({placeholders})
              AND NOT EXISTS (
                  SELECT 1 FROM transaction_labels tl
                  WHERE tl.chain = cp.chain AND tl.token = cp.token
                    AND tl.tx_hash = cp.tx_hash AND tl.address = cp.address
              )
        """
        params = [notes, chain, pool_address] + exclude_addrs

        cur = conn.execute(sql, params)
        conn.execute("DROP TABLE temp.pool_txs")
        conn.commit()
        elapsed = time.time() - start

        total_inserted += cur.rowcount
        print(f"[{idx}/{len(POOLS)}] {chain:8} {pool_label:30} ({pool_tx_count:>6} pool txs) inserted {cur.rowcount:>7} rows  ({elapsed:.1f}s)")

    print(f"\nDone. Total inserted: {total_inserted}")


if __name__ == "__main__":
    main()
