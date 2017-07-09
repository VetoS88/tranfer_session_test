import json
import os

import requests
import time
import redis
from telegram_connector.client import TelethonConnection
from telegram_connector.telegram_manager import InteractiveTelegramClient
from telegram_connector.telegram_registrator.registrator import TelegramRegistrator

ONLINESIM_API_KEY = '58488ee65ab16eaea6bab0bebdf21942'
ONLINESIM_USER_ID = 612070

API_ID = 144783
API_HASH = 'bccb20ef33c1ccfc2ac18c9f3db7f30c'


get_number_url = 'http://onlinesim.ru/api/getNum.php?apikey={}&service=Telegram&form=1'.format(ONLINESIM_API_KEY)
services_url = 'http://onlinesim.ru/api/getServiceList.php?apikey={}'.format(ONLINESIM_API_KEY)

def get_check_url_state(api, tzid):
    check_state_url = 'http://onlinesim.ru/api/getState.php?apikey={}&tzid={}&message_to_code=1'\
        .format(api, tzid)
    return check_state_url

def make_tele_session():
    apisession = requests.Session()

    operation_resp = apisession.get(get_number_url)
    resp_param = json.loads(operation_resp.text)
    tzid = resp_param['tzid']
    check_state_url = get_check_url_state(ONLINESIM_API_KEY, tzid)
    state_response = apisession.get(check_state_url)
    state_param = json.loads(state_response.text)[0]
    phone_number = state_param['number']
    tsession = phone_number.replace('+', '')
    exp_session = os.path.join('export_sessions', tsession)
    print(phone_number)
    teleclient = TelegramRegistrator(
        session=exp_session,
        api_id=API_ID,
        api_hash=API_HASH
    )
    teleclient.connect()
    chk_phone_result = teleclient.check_phone(phone_number)
    print(chk_phone_result)
    send_code_result = teleclient.send_code_request(phone_number)
    print(send_code_result)
    code = None
    count = 0
    while True:
        print('Ждем получение ответа от onlinesim....')
        time.sleep(10)
        state_response = apisession.get(check_state_url)
        state_param = json.loads(state_response.text)[0]
        print(state_param)
        code = state_param.get('msg', None)
        if count > 10:
            code = input('Введите код (!q для выхода): ')
            if code == '!q':
                break
        if code:
            break
        print('Значение в поле код. ', code)
        count += 1
    sung_up_result = teleclient.sign_up(phone_number, code, 'tstet_name', last_name='tstet_last_name')
    print(sung_up_result)
    chk_phone_result = teleclient.check_phone(phone_number)
    print(chk_phone_result)
    is_user_authorized = teleclient.is_user_authorized()
    print('Пользователь авторизован: ', is_user_authorized)
    print()
    # teleclient.run()
    return tsession + '.session'
