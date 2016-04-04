POCKET_URL = 'https://getpocket.com/auth/authorize?request_token={token}&redirect_uri={uri}'

async def parse_creation(request_body, request_qs=None):
    return {
        'token': request_body.get('token', '')
    }

async def redirect_url(info, redirect_uri):
    return POCKET_URL.format(
        token=info.get('token'),
        uri=redirect_uri
    )
