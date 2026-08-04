import os
from sqlalchemy import create_engine, text

PROD_DB_URL = "postgresql://tradingbot_ds2i_user:8D5Am9HRux06Kmf6r4P5d75XYaZujhV4@dpg-d9iiam7aqgkc73a5dd20-a.singapore-postgres.render.com/tradingbot_ds2i"

print("Connecting to production PostgreSQL database...")
try:
    engine = create_engine(PROD_DB_URL, connect_args={"connect_timeout": 15})
    with engine.connect() as conn:
        print("\n--- TRADING PAIRS ---")
        res = conn.execute(text("SELECT * FROM trading_pairs;"))
        for r in res:
            print(dict(r._mapping))

        print("\n--- BOT STATES ---")
        res = conn.execute(text("SELECT * FROM bot_states;"))
        for r in res:
            print(dict(r._mapping))

        print("\n--- RECENT SYSTEM LOGS ---")
        res = conn.execute(text("SELECT * FROM system_logs ORDER BY id DESC LIMIT 30;"))
        for r in res:
            d = dict(r._mapping)
            print(f"{d.get('created_at')} [{d.get('level')}] ({d.get('symbol')}) {d.get('message')}")

        print("\n--- RECENT SIGNALS HISTORY ---")
        res = conn.execute(text("SELECT * FROM signals_history ORDER BY id DESC LIMIT 20;"))
        for r in res:
            print(dict(r._mapping))

        print("\n--- RECENT TRADES ---")
        res = conn.execute(text("SELECT * FROM trades ORDER BY id DESC LIMIT 20;"))
        for r in res:
            print(dict(r._mapping))

except Exception as e:
    print("Failed to query prod DB:", e)
