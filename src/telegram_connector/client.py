# -*- coding: utf-8 -*-
import logging
import telethon

from config import APP_NAME
from config.telegram_client import TELEGRAM_CLIENT_CONFIG
from .telegram_manager import InteractiveTelegramClient

ACTUAL_CLIENT_CONFIG = TELEGRAM_CLIENT_CONFIG

logger = logging.getLogger(APP_NAME + '.' + __name__)


class TelethonConnection:
    """
    Класс подключения к telegram через библиотеку telethon
    """
    _session_user_id = None
    _user_phone = None
    _api_id = None
    _api_hash = None
    _client = None

    def __init__(self):
        self._session_user_id = ACTUAL_CLIENT_CONFIG['session_name']
        self._user_phone = ACTUAL_CLIENT_CONFIG['phone_number']
        self._api_id = int(ACTUAL_CLIENT_CONFIG['api_id'])
        self._api_hash = ACTUAL_CLIENT_CONFIG['api_hash']

    def __enter__(self):
        return self.client

    def __exit__(self, exc_type, exc_val, exc_tb):
        logger.info(
            'Закрытие клиента телеграмма %s', self.client
        )
        self.close()

    @property
    def client(self):
        """
        Создает клиента telethon
        :return:
        """
        if not self._client:
            self._client = InteractiveTelegramClient(
                session_user_id=ACTUAL_CLIENT_CONFIG['session_name'],
                user_phone=ACTUAL_CLIENT_CONFIG['phone_number'],
                api_id=int(ACTUAL_CLIENT_CONFIG['api_id']),
                api_hash=ACTUAL_CLIENT_CONFIG['api_hash']
            )
        return self._client

    def close(self):
        self.client.disconnect()
        logger.info(
            'Клиент телеграмма %s был закрыт', self._client
        )
        self._client = None
