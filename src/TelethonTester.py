import redis
#
# from Archive.interactive_telegram_client import InteractiveTelegramClient
# from telegram_connector.client import TelethonConnection
# from telegram_connector.telegram_registrator.registrator import TelegramRegistrator
import json

from config.redis_config import REDIS_CONF
from telegram_connector.telegram_manager import InteractiveTelegramClient

TELEGRAM_CLIENT_CONFIG = {
    'session_name': '79633479629',
    'phone_number': '+79633479629',
    'api_id': '22893',
    'api_hash': 'bfc342e48a7a0986b670777ed36fe0fb',
}

rds_client = redis.StrictRedis(
    host=REDIS_CONF['host'],
    port=REDIS_CONF['port'],
    db=REDIS_CONF['db']
)

session_file_name = TELEGRAM_CLIENT_CONFIG['session_name'] + '.session'
res_from_rds = rds_client.get(session_file_name)
ses_file = open(session_file_name, 'w')
ses_file.write(res_from_rds.decode('utf-8'))
ses_file.close()
client = InteractiveTelegramClient(
                session_user_id=TELEGRAM_CLIENT_CONFIG['session_name'],
                user_phone=TELEGRAM_CLIENT_CONFIG['phone_number'],
                api_id=int(TELEGRAM_CLIENT_CONFIG['api_id']),
                api_hash=TELEGRAM_CLIENT_CONFIG['api_hash']
            )
client.run()

# session = 'tryreg23'
# client = TelegramRegistrator(session)
# client.connect()
# phone = '+79675932422'
# result = client.check_phone(phone)
# print(result)
# client.send_code_request(phone)
#
# code = input('Введите код:')
# result = client.sign_up(phone, code, 'tst_first_name', last_name='')
# print(result)
# print()
# # client.disconnect()
