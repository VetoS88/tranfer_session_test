import redis
import json
import os
from Archive.session_registrator.src.telegram_connector.telegram_registrator.onlinesim_manager import make_tele_session
# from .config.redis_config import REDIS_CONF
from Archive.session_registrator.src.config.redis_config import REDIS_CONF

rds_client = redis.StrictRedis(
    host=REDIS_CONF['host'],
    port=REDIS_CONF['port'],
    db=REDIS_CONF['db']
)

session_name = make_tele_session()
# session_name = '80992546590.session'
session_string = open(os.path.join(os.getcwd(), 'export_sessions', session_name)).read()
res = rds_client.set(session_name, session_string)
print(res)
# json_session = json.load(session_file)