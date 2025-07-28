import tweepy
import asyncio
import logging
from telegram import Bot
from telegram.constants import ParseMode
import json
import os
from datetime import datetime
import re

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
BEARER_TOKEN = os.getenv('BEARER_TOKEN', "AAAAAAAAAAAAAAAAAAAAAF0U3QEAAAAAZ1mMW0tIY3J2WYlyLrK6KEg2UDM%3DCQ1BUccUEoPm56Osb4LaFIrQarMphlEKK7Klx0mUVvCARC4wQi")
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', "6020853840:AAG6XrAbh05rCUt9zPO-nq8F6pLkI40PZEo")
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', "587512070")

# Список аккаунтов для мониторинга
TWITTER_ACCOUNTS = ["Xenea_io", "pharos_network", "opnetbtc", "owb_studio"]

# Инициализация Twitter API
twitter_client = tweepy.Client(
    bearer_token=BEARER_TOKEN, 
    wait_on_rate_limit=True
)

# Инициализация Telegram бота
telegram_bot = Bot(token=TELEGRAM_BOT_TOKEN)

class TwitterMonitor:
    def __init__(self):
        self.last_tweet_ids = self.load_last_tweet_ids()
    
    def load_last_tweet_ids(self):
        """Загрузка последних ID твитов из файла"""
        try:
            with open('last_tweets.json', 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {account: None for account in TWITTER_ACCOUNTS}
        except Exception as e:
            logger.error(f"Ошибка загрузки last_tweets.json: {e}")
            return {account: None for account in TWITTER_ACCOUNTS}
    
    def save_last_tweet_ids(self):
        """Сохранение последних ID твитов в файл"""
        try:
            with open('last_tweets.json', 'w') as f:
                json.dump(self.last_tweet_ids, f)
        except Exception as e:
            logger.error(f"Ошибка сохранения last_tweets.json: {e}")
    
    async def get_user_info(self, username):
        """Получение информации о пользователе"""
        try:
            user = twitter_client.get_user(
                username=username,
                user_fields=['name', 'username', 'profile_image_url']
            )
            return user.data if user.data else None
        except Exception as e:
            logger.error(f"Ошибка при получении информации о пользователе {username}: {e}")
            return None
    
    async def get_user_tweets(self, username):
        """Получение последних твитов пользователя"""
        try:
            user = await self.get_user_info(username)
            if not user:
                return []
            
            # Получаем последние твиты
            tweets = twitter_client.get_users_tweets(
                id=user.id,
                max_results=20,
                tweet_fields=['created_at', 'author_id', 'public_metrics', 'attachments', 'text'],
                exclude=['retweets', 'replies']
            )
            
            return tweets.data if tweets.data else []
        except Exception as e:
            logger.error(f"Ошибка при получении твитов пользователя {username}: {e}")
            return []
    
    def format_tweet_text(self, text):
        """Форматирование текста твита для Telegram"""
        # Обработка хэштегов
        text = re.sub(r'#(\w+)', r'<b>#\1</b>', text)
        # Обработка упоминаний
        text = re.sub(r'@(\w+)', r'@<a href="https://twitter.com/\1">\1</a>', text)
        return text
    
    async def send_telegram_message(self, message_text, tweet_url):
        """Отправка сообщения в Telegram"""
        try:
            full_message = f"{message_text}\n\n🔗 <a href='{tweet_url}'>Перейти к твиту</a>"
            
            await telegram_bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=full_message,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения в Telegram: {e}")
    
    async def process_account_tweets(self, account):
        """Обработка твитов одного аккаунта"""
        try:
            logger.info(f"Проверка твитов для @{account}")
            tweets = await self.get_user_tweets(account)
            
            if not tweets:
                return
            
            # Сортируем по дате (новые первыми)
            tweets = sorted(tweets, key=lambda x: x.created_at, reverse=True)
            
            new_tweets_count = 0
            for tweet in reversed(tweets):  # Обрабатываем в хронологическом порядке
                tweet_id = str(tweet.id)
                last_id = self.last_tweet_ids.get(account)
                
                # Пропускаем уже отправленные твиты
                if last_id and tweet_id <= last_id:
                    continue
                
                # Формируем сообщение
                user_info = await self.get_user_info(account)
                user_name = user_info.name if user_info else account
                
                message_text = f"<b>{user_name} (@{account})</b>\n\n"
                message_text += self.format_tweet_text(tweet.text)
                message_text += f"\n\n<i>📅 {tweet.created_at.strftime('%d.%m.%Y %H:%M')}</i>"
                
                tweet_url = f"https://twitter.com/{account}/status/{tweet_id}"
                
                await self.send_telegram_message(message_text, tweet_url)
                
                # Обновляем последний ID
                self.last_tweet_ids[account] = tweet_id
                new_tweets_count += 1
                
                # Небольшая задержка между сообщениями
                await asyncio.sleep(2)
            
            if new_tweets_count > 0:
                self.save_last_tweet_ids()
                logger.info(f"Отправлено {new_tweets_count} новых твитов от @{account}")
                
        except Exception as e:
            logger.error(f"Ошибка при обработке аккаунта @{account}: {e}")
    
    async def process_all_accounts(self):
        """Обработка твитов всех аккаунтов"""
        for account in TWITTER_ACCOUNTS:
            await self.process_account_tweets(account)
            # Задержка между аккаунтами
            await asyncio.sleep(5)
    
    async def run_monitoring(self):
        """Основной цикл мониторинга"""
        logger.info("Начало мониторинга Twitter аккаунтов...")
        
        while True:
            try:
                await self.process_all_accounts()
                # Ждем 10 минут перед следующей проверкой
                await asyncio.sleep(600)
            except Exception as e:
                logger.error(f"Ошибка в основном цикле: {e}")
                # Ждем 1 минуту перед повторной попыткой
                await asyncio.sleep(60)

async def main():
    """Главная функция"""
    monitor = TwitterMonitor()
    await monitor.run_monitoring()

if __name__ == "__main__":
    asyncio.run(main())