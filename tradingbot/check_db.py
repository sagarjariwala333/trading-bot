#!/usr/bin/env python3
from app.database.session import SessionLocal
from sqlalchemy import text

def check_database():
    with SessionLocal() as db:
        # Check what tables exist
        result = db.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name
        """))
        tables = result.fetchall()
        print('📊 Created tables:')
        for table in tables:
            print(f'  - {table[0]}')
            
        # Check if we have the old or new structure
        old_tables = ['bot_configs', 'bot_states', 'active_bots']
        new_tables = ['trading_pairs', 'bot_states', 'historical_data', 'trade_executions']
        
        table_names = [t[0] for t in tables]
        
        if all(t in table_names for t in old_tables):
            print('\n✅ Found OLD table structure (legacy migration)')
            
            # Check bot_configs structure
            result = db.execute(text("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'bot_configs'
                ORDER BY ordinal_position
            """))
            columns = result.fetchall()
            print('\n📋 bot_configs columns:')
            for col in columns:
                print(f'  - {col[0]}: {col[1]}')
        
        if any(t in table_names for t in new_tables):
            print('\n✅ Found NEW table structure (ORM models)')

if __name__ == '__main__':
    check_database()