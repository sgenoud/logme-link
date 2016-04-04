#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''
File: server.py
Author: Steve Genoud
Date: 2016-02-29
Description:
'''

import os
import json
import urllib.parse
import random
import logging

import asyncio
from aiohttp import web
import aioredis

from services import pocket

def _parse_qs(string, *args, **kwargs):
    return dict(urllib.parse.parse_qsl(string, *args, **kwargs))


# Configuration of the logger
std_handler = logging.StreamHandler()
std_handler.setLevel(logging.INFO)
access_logger = logging.getLogger('aiohttp.access')
access_logger.setLevel(logging.INFO)
access_logger.addHandler(std_handler)

# Environment Variables
REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')
REDIS_PORT = os.environ.get('REDIS_PORT', 6379)
REDIS = (REDIS_HOST, REDIS_PORT)

HOST = os.environ.get('SERVE_ON', '0.0.0.0')
PORT = os.environ.get('SERVE_ON_PORT', 8080)

MY_URL = os.environ.get('SERVER_URL', 'http://localhost:8080')
KEY_TTL = int(os.environ.get('KEY_TTL', 300))

FINAL_REDIRECT_URL = os.environ.get('FINAL_REDIRECT_URL')

SERVICES = {
    'pocket': pocket,
}


def error(text, status=400):
    return web.json_response({
        "status": "error",
        "error": text
    }, status=status)


CHARS = 'abcdefghijklmnopqrstuvwxyz23456789'.upper()
def _code(size):
    return ''.join(random.choice(CHARS) for _ in range(size))

def _normalise(text):
    text = text.upper()
    text.replace('0', 'O')
    text.replace('1', 'I')
    return text

async def _info(redis, secret, updated_with=None):
    info = await redis.get(secret, encoding='utf-8')
    if not info:
        raise web.HTTPNotFound()

    parsed_info = json.loads(info)

    if updated_with:
        parsed_info.update(updated_with)

        tr = redis.multi_exec()
        tr.set(secret, json.dumps(parsed_info))
        tr.expire(secret, KEY_TTL)
        await tr.execute()

    return parsed_info

async def create(request):
    redis_pool = request.app['redis_pool']
    try:
        body = await request.json()
    except json.decoder.JSONDecodeError:
        return error('could not decode the body')

    qs = request.query_string
    if qs:
        qs = _parse_qs(qs)

    service_name = body.get('service')
    service = SERVICES.get(service_name)
    if not service:
        return error('service {} not available'.format(service_name))

    key, secret = _code(6), _code(60)
    if 'key' in body:
        key = body['key'].upper()

    base_info = {
        'service': service_name,
        'registered': False,
        'redirected': False,
    }
    if 'final_redirect_url' in body:
        base_info['final_redirect_url'] = body['final_redirect_url']
    info = (await service.parse_creation(body, qs)).copy()
    info.update(base_info)

    async with redis_pool.get() as redis:
        tr = redis.multi_exec()
        tr.set(key, secret)
        tr.set(secret, json.dumps(info))
        tr.expire(key, KEY_TTL)
        tr.expire(secret, KEY_TTL)
        await tr.execute()

    return web.json_response({
        'status': 'ok',
        'key': key,
        'url': MY_URL + '/' + key.lower(),
        'secret': secret,
    })

async def redirect(request):
    key = request.match_info.get('key')

    async with request.app['redis_pool'].get() as redis:
        secret = await redis.get(_normalise(key), encoding='utf-8')

        if not secret:
            return error('Not Found', status=404)

        info = await _info(redis, secret, updated_with={'redirected': True})
        redis.publish(secret, 'redirected')

    if not info:
        return error('Not Found', status=404)

    service_name = info['service']
    service = SERVICES.get(service_name)
    if not service:
        return error('service {} not available'.format(service_name))

    redirect_uri = urllib.parse.quote(MY_URL + '/register/{}'.format(key))
    url = await service.redirect_url(info, redirect_uri=redirect_uri)
    return web.HTTPFound(url)


async def fetch_info(request):
    secret = request.match_info.get('secret')
    redis_pool = request.app['redis_pool']
    redis_sub_pool = request.app['redis_subscribe_pool']

    # We get the status from he query string
    qs = urllib.parse.parse_qs(request.query_string)
    statuses = qs.get('wait', [])
    statuses = [s for s in statuses if s in ['registered', 'redirected']]

    async with redis_pool.get() as redis:
        parsed_info = await _info(redis, secret)

    # cases where we do not want to wait: no status or any of the status returned
    if not statuses or any(parsed_info.get(status) for status in statuses):
        return web.json_response(parsed_info)

    async with redis_sub_pool.get() as redis_sub:
        channel, = await redis_sub.subscribe(secret)

        for _ in range(10):
            done, not_done = await asyncio.wait([channel.get(encoding='utf-8')], timeout=30)

            if not_done or (done and done.pop().result() in statuses):
                break

        await redis_sub.unsubscribe(secret)

    async with redis_pool.get() as redis:
        info = await _info(redis, secret)

    return web.json_response(info)


async def register(request):
    key = request.match_info.get('key')
    async with request.app['redis_pool'].get() as redis:
        secret = await redis.get(_normalise(key), encoding='utf-8')
        if not secret:
            return error('Not Found', status=404)

        info = await _info(redis, secret, updated_with={'registered': True})
        redis.publish(secret, 'registered')

    if info.get('final_redirect_url', FINAL_REDIRECT_URL):
        return web.HTTPFound(info.get('final_redirect_url', FINAL_REDIRECT_URL))

    return web.Response(
        text='<!DOCTYPE html> <html> <body><h1>Ok</h1></body> </html>',
        content_type='text/html'
    )

async def isup(request):
    async with request.app['redis_pool'].get() as redis:
        await redis.set('test', 'test')
        out = await redis.get('test', encoding='utf-8')

    return web.json_response({
        'status': 'ok',
        'redis': out == 'test',
        'base_url': MY_URL,
    })

def add_routes(app):
    app.router.add_route('GET', '/_isup', isup)

    app.router.add_route('POST', '/_create', create)

    app.router.add_route('GET', '/_info/{secret}', fetch_info)

    app.router.add_route('GET', '/{key}', redirect)
    app.router.add_route('GET', '/register/{key}', register)


def init():
    app = web.Application()

    loop = asyncio.get_event_loop()
    handler = app.make_handler()
    f = loop.create_server(handler, SERVE_ON, SERVE_ON_PORT)

    srv = loop.run_until_complete(f)

    add_routes(app)
    app['redis_pool'] = loop.run_until_complete(aioredis.create_pool(REDIS))
    app['redis_subscribe_pool'] = loop.run_until_complete(aioredis.create_pool(REDIS))

    print('serving on', srv.sockets[0].getsockname())

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.close()
        loop.run_until_complete(app['redis_pool'].clear())
        loop.run_until_complete(app['redis_subscribe_pool'].clear())
        loop.run_until_complete(srv.wait_closed())
        loop.run_until_complete(app.shutdown())
        loop.run_until_complete(handler.finish_connections(60.0))
        loop.run_until_complete(app.cleanup())
    loop.close()

if __name__ == '__main__':
    init()
