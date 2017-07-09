from telethon.errors import RPCError


class UnauthorizedError(RPCError):
    """
        There was an unauthorized attempt to use functionality available only
        to authorized users.
    """
    code = 401
    message = 'UNAUTHORIZED'


class SessionPasswordNeededError(UnauthorizedError):
    def __init__(self, **kwargs):
        super(Exception, self).__init__(
            self,
            'Two-steps verification is enabled and a password is required.'
        )