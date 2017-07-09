import platform
from datetime import timedelta
from threading import Event, RLock, Thread
from time import sleep

# Import some externalized utilities to work with the Telegram types and more
from telethon import TelegramClient
from telethon.errors import (RPCError, InvalidDCError, FloodWaitError,
                             ReadCancelledError)
from telethon.network import authenticator, MtProtoSender, TcpTransport
# For sending and receiving requests
from telethon.tl import MTProtoRequest, Session, JsonSession
from telethon.tl.all_tlobjects import layer
from telethon.tl.functions import (InitConnectionRequest, InvokeWithLayerRequest)
# Required to work with different data centers
from telethon.tl.functions.auth import (CheckPhoneRequest)
# Logging in and out
from telethon.tl.functions.auth import (SendCodeRequest, SignUpRequest)
# Initial request
from telethon.tl.functions.help import GetConfigRequest
from telethon.tl.types import UpdateShortMessage, UpdateShortChatMessage
from telethon.utils import get_display_name

# from config.logging_config import app_logger


# Required to get the password salt
# Easier access to common methods
# For .get_me() and ensuring we're authorized
# Easier access for working with media, too
# All the types we need to work with
from Archive.loging_config_local import app_logger


def sprint(string, *args, **kwargs):
    """Safe Print (handle UnicodeEncodeErrors on some terminals)"""
    try:
        print(string, *args, **kwargs)
    except UnicodeEncodeError:
        string = string.encode('utf-8', errors='ignore') \
            .decode('ascii', errors='ignore')
        print(string, *args, **kwargs)


def print_title(title):
    # Clear previous window
    print('\n')
    print('=={}=='.format('=' * len(title)))
    sprint('= {} ='.format(title))
    print('=={}=='.format('=' * len(title)))


def bytes_to_string(byte_count):
    """Converts a byte count to a string (in KB, MB...)"""
    suffix_index = 0
    while byte_count >= 1024:
        byte_count /= 1024
        suffix_index += 1

    return '{:.2f}{}'.format(byte_count,
                             [' bytes', 'KB', 'MB', 'GB', 'TB'][suffix_index])


class TelegramRegistrator(TelegramClient):
    # Current TelegramClient version
    __version__ = '0.10.1'

    # region Initialization

    def __init__(self, session, api_id=None, api_hash=None, proxy=None):
        """Initializes the Telegram client with the specified API ID and Hash.

           Session can either be a `str` object (the filename for the loaded/saved .session)
           or it can be a `Session` instance (in which case list_sessions() would probably not work).
           If you don't want any file to be saved, pass `None`

           In the later case, you are free to override the `Session` class to provide different
           .save() and .load() implementations to suit your needs."""

        # if api_id is None or api_hash is None:
        #     raise PermissionError(
        #         'Your API ID or Hash are invalid. Please read "Requirements" on README.rst')

        super().__init__(session, api_id, api_hash, proxy)
        self.api_id = api_id
        self.api_hash = api_hash

        # Determine what session object we have
        # TODO JsonSession until migration is complete (by v1.0)
        if isinstance(session, str) or session is None:
            self.session = JsonSession.try_load_or_create_new(session)
        elif isinstance(session, Session):
            self.session = session
        else:
            raise ValueError(
                'The given session must either be a string or a Session instance.')

        self.transport = None
        self.proxy = proxy  # Will be used when a TcpTransport is created

        self.login_success = False

        # Safety across multiple threads (for the updates thread)
        self._lock = RLock()
        self._logger = app_logger

        # Methods to be called when an update is received
        self._update_handlers = []
        self._updates_thread_running = Event()
        self._updates_thread_receiving = Event()

        # Cache "exported" senders 'dc_id: MtProtoSender' and
        # their corresponding sessions not to recreate them all
        # the time since it's a (somewhat expensive) process.
        self._cached_senders = {}
        self._cached_sessions = {}

        # These will be set later
        self._updates_thread = None
        self.dc_options = None
        self.sender = None
        self.phone_code_hashes = {}

    def connect(self, reconnect=False,
                device_model=None, system_version=None,
                app_version=None, lang_code=None):
        """Connects to the Telegram servers, executing authentication if
           required. Note that authenticating to the Telegram servers is
           not the same as authenticating the desired user itself, which
           may require a call (or several) to 'sign_in' for the first time.

           Default values for the optional parameters if left as None are:
             device_model   = platform.node()
             system_version = platform.system()
             app_version    = TelegramClient.__version__
             lang_code      = 'en'
        """
        if self.transport is None:
            self.transport = TcpTransport(self.session.server_address,
                                          self.session.port, proxy=self.proxy)

        try:
            if not self.session.auth_key or (reconnect and self.sender is not None):
                self.session.auth_key, self.session.time_offset = \
                    authenticator.do_authentication(self.transport)

                self.session.save()

            self.sender = MtProtoSender(self.transport, self.session)
            self.sender.connect()

            # Set the default parameters if left unspecified
            if not device_model:
                device_model = platform.node()
            if not system_version:
                system_version = platform.system()
            if not app_version:
                app_version = self.__version__
            if not lang_code:
                lang_code = 'en'

            # Now it's time to send an InitConnectionRequest
            # This must always be invoked with the layer we'll be using
            query = InitConnectionRequest(
                api_id=self.api_id,
                device_model=device_model,
                system_version=system_version,
                app_version=app_version,
                lang_code=lang_code,
                query=GetConfigRequest())

            result = self.invoke(
                InvokeWithLayerRequest(
                    layer=layer, query=query))

            # We're only interested in the DC options,
            # although many other options are available!
            self.dc_options = result.dc_options

            self.login_success = True
            return True
        except (RPCError, ConnectionError) as error:
            # Probably errors from the previous session, ignore them
            self._logger.warning('Could not stabilise initial connection: {}'
                                 .format(error))
            return False

    def check_phone(self, phone_number):
        result = self.invoke(
                CheckPhoneRequest(phone_number=phone_number))
        return result

    def sign_up(self, phone_number, code, first_name, last_name=''):
        """Signs up to Telegram. Make sure you sent a code request first!"""
        result = self.invoke(
            SignUpRequest(
                phone_number=phone_number,
                phone_code_hash=self.phone_code_hashes[phone_number],
                phone_code=code,
                first_name=first_name,
                last_name=last_name))

        self.session.user = result.user
        self.session.save()
        return result

    def invoke(self, request, timeout=timedelta(seconds=5), throw_invalid_dc=False):
        """Invokes a MTProtoRequest (sends and receives it) and returns its result.
           An optional timeout can be given to cancel the operation after the time delta.
           Timeout can be set to None for no timeout.

           If throw_invalid_dc is True, these errors won't be caught (useful to
           avoid infinite recursion). This should not be set to True manually."""
        if not issubclass(type(request), MTProtoRequest):
            raise ValueError('You can only invoke MtProtoRequests')

        if not self.sender:
            raise ValueError('You must be connected to invoke requests!')

        if self._updates_thread_receiving.is_set():
            self.sender.cancel_receive()

        try:
            self._lock.acquire()
            updates = []
            self.sender.send(request)
            self.sender.receive(request, timeout, updates=updates)
            for update in updates:
                for handler in self._update_handlers:
                    handler(update)

            return request.result

        except InvalidDCError as error:
            if throw_invalid_dc:
                raise
            self._reconnect_to_dc(error.new_dc)
            return self.invoke(request,
                               timeout=timeout, throw_invalid_dc=True)

        except ConnectionResetError:
            self._logger.info('Server disconnected us. Reconnecting and '
                              'resending request...')
            self.reconnect()
            self.invoke(request, timeout=timeout,
                        throw_invalid_dc=throw_invalid_dc)

        except FloodWaitError:
            self.disconnect()
            raise

        finally:
            self._lock.release()

    def reconnect(self):
        """Disconnects and connects again (effectively reconnecting)"""
        self.disconnect()
        self.connect()

    def disconnect(self):
        """Disconnects from the Telegram server and stops all the spawned threads"""
        self._set_updates_thread(running=False)
        if self.sender:
            self.sender.disconnect()
            self.sender = None
        if self.transport:
            self.transport.close()
            self.transport = None

        # Also disconnect all the cached senders
        for sender in self._cached_senders.values():
            sender.disconnect()

        self._cached_senders.clear()
        self._cached_sessions.clear()

    def _set_updates_thread(self, running):
        """Sets the updates thread status (running or not)"""
        if running == self._updates_thread_running.is_set():
            return

        # Different state, update the saved value and behave as required
        self._logger.info('Changing updates thread running status to %s', running)
        if running:
            self._updates_thread_running.set()
            if not self._updates_thread:
                self._updates_thread = Thread(
                    name='UpdatesThread', daemon=True,
                    target=self._updates_thread_method)

            self._updates_thread.start()
        else:
            self._updates_thread_running.clear()
            if self._updates_thread_receiving.is_set():
                self.sender.cancel_receive()

    def _updates_thread_method(self):
        """This method will run until specified and listen for incoming updates"""

        # Set a reasonable timeout when checking for updates
        timeout = timedelta(minutes=1)

        while self._updates_thread_running.is_set():
            # Always sleep a bit before each iteration to relax the CPU,
            # since it's possible to early 'continue' the loop to reach
            # the next iteration, but we still should to sleep.
            sleep(0.1)

            with self._lock:
                self._logger.debug('Updates thread acquired the lock')
                try:
                    self._updates_thread_receiving.set()
                    self._logger.debug('Trying to receive updates from the updates thread')
                    result = self.sender.receive_update(timeout=timeout)
                    self._logger.info('Received update from the updates thread')
                    for handler in self._update_handlers:
                        handler(result)

                except ConnectionResetError:
                    self._logger.info('Server disconnected us. Reconnecting...')
                    self.reconnect()

                except TimeoutError:
                    self._logger.debug('Receiving updates timed out')

                except ReadCancelledError:
                    self._logger.info('Receiving updates cancelled')

                except OSError:
                    self._logger.warning('OSError on updates thread, %s logging out',
                                         'was' if self.sender.logging_out else 'was not')

                    if self.sender.logging_out:
                        # This error is okay when logging out, means we got disconnected
                        # TODO Not sure why this happens because we call disconnect()…
                        self._set_updates_thread(running=False)
                    else:
                        raise

            self._logger.debug('Updates thread released the lock')
            self._updates_thread_receiving.clear()

        # Thread is over, so clean unset its variable
        self._updates_thread = None

    def _reconnect_to_dc(self, dc_id):
        """Reconnects to the specified DC ID. This is automatically
           called after an InvalidDCError is raised"""
        dc = self._get_dc(dc_id)

        self.transport.close()
        self.transport = None
        self.session.server_address = dc.ip_address
        self.session.port = dc.port
        self.session.save()

        self.connect(reconnect=True)

    def _get_dc(self, dc_id):
        """Gets the Data Center (DC) associated to 'dc_id'"""
        if not self.dc_options:
            raise ConnectionError(
                'Cannot determine the required data center IP address. '
                'Stabilise a successful initial connection first.')

        return next(dc for dc in self.dc_options if dc.id == dc_id)

    def send_code_request(self, phone_number):
        """Sends a code request to the specified phone number"""
        result = self.invoke(SendCodeRequest(phone_number, self.api_id, self.api_hash))
        self.phone_code_hashes[phone_number] = result.phone_code_hash
        return result

    def run(self):
        # Listen for updates
        self.add_update_handler(self.update_handler)

        # Enter a while loop to chat as long as the user wants
        while True:
            # Retrieve the top dialogs
            dialog_count = 10

            # Entities represent the user, chat or channel
            # corresponding to the dialog on the same index
            dialogs, entities = self.get_dialogs(dialog_count)

            i = None
            while i is None:
                print_title('Dialogs window')

                # Display them so the user can choose
                for i, entity in enumerate(entities, start=1):
                    sprint('{}. {}'.format(i, get_display_name(entity)))

                # Let the user decide who they want to talk to
                print()
                print('> Who do you want to send messages to?')
                print('> Available commands:')
                print('  !q: Quits the dialogs window and exits.')
                print('  !l: Logs out, terminating this session.')
                print()
                i = input('Enter dialog ID or a command: ')
                if i == '!q':
                    return
                if i == '!l':
                    self.log_out()
                    return

                try:
                    i = int(i if i else 0) - 1
                    # Ensure it is inside the bounds, otherwise retry
                    if not 0 <= i < dialog_count:
                        i = None
                except ValueError:
                    i = None

            # Retrieve the selected user (or chat, or channel)
            entity = entities[i]

            # Show some information
            print_title('Chat with "{}"'.format(get_display_name(entity)))
            print('Available commands:')
            print('  !q: Quits the current chat.')
            print('  !Q: Quits the current chat and exits.')
            print('  !h: prints the latest messages (message History).')
            print('  !up <path>: Uploads and sends the Photo from path.')
            print('  !uf <path>: Uploads and sends the File from path.')
            print('  !dm <msg-id>: Downloads the given message Media (if any).')
            print('  !dp: Downloads the current dialog Profile picture.')
            print()

            # And start a while loop to chat
            while True:
                msg = input('Enter a message: ')
                # Quit
                if msg == '!q':
                    break
                elif msg == '!Q':
                    return

                # History
                elif msg == '!h':
                    # First retrieve the messages and some information
                    total_count, messages, senders = self.get_message_history(
                        entity, limit=10)

                    # Iterate over all (in reverse order so the latest appear
                    # the last in the console) and print them with format:
                    # "[hh:mm] Sender: Message"
                    for msg, sender in zip(
                            reversed(messages), reversed(senders)):
                        # Get the name of the sender if any
                        if sender:
                            name = getattr(sender, 'first_name', None)
                            if not name:
                                name = getattr(sender, 'title')
                                if not name:
                                    name = '???'
                        else:
                            name = '???'

                        # Format the message content
                        if getattr(msg, 'media', None):
                            self.found_media.add(msg)
                            # The media may or may not have a caption
                            caption = getattr(msg.media, 'caption', '')
                            content = '<{}> {}'.format(
                                type(msg.media).__name__, caption)

                        elif hasattr(msg, 'message'):
                            content = msg.message
                        elif hasattr(msg, 'action'):
                            content = str(msg.action)
                        else:
                            # Unknown message, simply print its class name
                            content = type(msg).__name__

                        # And print it to the user
                        sprint('[{}:{}] (ID={}) {}: {}'.format(
                            msg.date.hour, msg.date.minute, msg.id, name,
                            content))

                # Send photo
                elif msg.startswith('!up '):
                    # Slice the message to get the path
                    self.send_photo(path=msg[len('!up '):], entity=entity)

                # Send file (document)
                elif msg.startswith('!uf '):
                    # Slice the message to get the path
                    self.send_document(path=msg[len('!uf '):], entity=entity)

                # Download media
                elif msg.startswith('!dm '):
                    # Slice the message to get message ID
                    self.download_media(msg[len('!dm '):])

                # Download profile photo
                elif msg == '!dp':
                    output = str('usermedia/propic_{}'.format(entity.id))
                    print('Downloading profile picture...')
                    success = self.download_profile_photo(entity.photo, output)
                    if success:
                        print('Profile picture downloaded to {}'.format(
                            output))
                    else:
                        print('No profile picture found for this user.')

                # Send chat message (if any)
                elif msg:
                    self.send_message(
                        entity, msg, no_web_page=True)

    @staticmethod
    def update_handler(update_object):
        if type(update_object) is UpdateShortMessage:
            if update_object.out:
                sprint('You sent {} to user #{}'.format(
                    update_object.message, update_object.user_id))
            else:
                sprint('[User #{} sent {}]'.format(
                    update_object.user_id, update_object.message))

        elif type(update_object) is UpdateShortChatMessage:
            if update_object.out:
                sprint('You sent {} to chat #{}'.format(
                    update_object.message, update_object.chat_id))
            else:
                sprint('[Chat #{}, user #{} sent {}]'.format(
                    update_object.chat_id, update_object.from_id,
                    update_object.message))

    def is_user_authorized(self):
        """Has the user been authorized yet
           (code request sent and confirmed)?"""
        return self.session and self.get_me() is not None