#!/usr/bin/env python3
"""
Скрипт для очистки недействительных медиа file_id из базы данных
"""
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from bot.database.operations import DatabaseManager

async def fix_invalid_media():
    """Очищает недействительные медиа file_id из всех профилей"""
    
    db_path = "data/bot.db"
    if not os.path.exists(db_path):
        print(f"❌ База данных не найдена: {db_path}")
        return
    
    print("🔧 Исправление недействительных медиа в профилях...")
    
    db_manager = DatabaseManager(db_path)
    await db_manager.connect()
    
    try:
        # Получаем все профили с медиа
        import aiosqlite
        async with aiosqlite.connect(db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute("""
                SELECT user_id, game_nickname, media_type 
                FROM profiles 
                WHERE media_type IS NOT NULL AND media_file_id IS NOT NULL
            """)
            profiles_with_media = await cursor.fetchall()
        
        if not profiles_with_media:
            print("📷 Профилей с медиа не найдено")
            return
        
        print(f"📷 Найдено {len(profiles_with_media)} профилей с медиа")
        
        choice = input("\nВыберите действие:\n1. Очистить ВСЕ медиа (рекомендуется)\n2. Только показать список\n3. Отменить\nВвод: ")
        
        if choice == "1":
            print(f"\n🧹 Очищаем медиа данные...")
            fixed_count = 0
            
            for profile in profiles_with_media:
                user_id = profile['user_id']
                nickname = profile['game_nickname']
                media_type = profile['media_type']
                
                # Очищаем медиа данные
                success = await db_manager.update_profile(
                    user_id,
                    media_type=None,
                    media_file_id=None
                )
                
                if success:
                    print(f"✅ Очищено медиа для {nickname} (ID: {user_id}) - тип: {media_type}")
                    fixed_count += 1
                else:
                    print(f"❌ Ошибка очистки медиа для {nickname} (ID: {user_id})")
            
            print(f"\n✅ Исправлено {fixed_count} из {len(profiles_with_media)} профилей")
            print("ℹ️  Пользователям потребуется заново добавить медиа в свои профили")
            
        elif choice == "2":
            print(f"\n📋 Список профилей с медиа:")
            for profile in profiles_with_media:
                print(f"  - {profile['game_nickname']} (ID: {profile['user_id']}) - {profile['media_type']}")
        
        else:
            print("❌ Операция отменена")
    
    finally:
        await db_manager.disconnect()

if __name__ == "__main__":
    asyncio.run(fix_invalid_media())
