from app.services.database_service import db_service
logs = db_service.get_recent_logs(symbol='BTCUSDT', limit=100)
for l in logs:
    print(f"{l['timestamp']} [{l['level']}] {l['message']}")
