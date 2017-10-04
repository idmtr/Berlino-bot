#!/usr/bin/env python
# -*- coding: utf-8 -*-
import json
import logging
import os
import re
import ssl
import threading
import urlparse
from collections import namedtuple

import requests
import websocket

log = logging.getLogger(__name__)

###VARIABLES THAT YOU NEED TO SET MANUALLY IF NOT ON HEROKU#####
try:
	WELCOME_MESSAGE = os.environ['WELCOME-MESSAGE']
	TOKEN = os.environ['SLACK-TOKEN']
except:
	WELCOME_MESSAGE = 'Manually set the Message if youre not running through heroku or have not set vars in ENV'
	TOKEN = 'Manually set the API Token if youre not running through heroku or have not set vars in ENV'
###############################################################

SNEAKY_USER_AGENT = headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/55.0.2883.75 Safari/537.36'}

_self_uid = None

SlackURL = namedtuple('SlackURL', ['text', 'url'])


def extract_root_domain(url):
    """
    >>> extract_root_domain("http://www.google.com")
    'google.com'
    >>> extract_root_domain("http://GOOGLE.com")
    'google.com'
    >>> extract_root_domain("http://foo")
    'foo'
    """
    parsed_url = urlparse.urlparse(url)
    root_domain = parsed_url.netloc.rsplit('.', 2)[-2:]
    return '.'.join(root_domain).lower()


def same_root_domains(url1, url2):
    return extract_root_domain(url1) == extract_root_domain(url2)


def extract_slack_urls(message):
    """
    >>> extract_slack_urls("derp <http://google.com|google.com> herp")
    [SlackURL(text='google.com', url='http://google.com')]
    >>> extract_slack_urls("derp <http://google.com|google.com> <http://bing.com|bing.com> herp")
    [SlackURL(text='google.com', url='http://google.com'), SlackURL(text='bing.com', url='http://bing.com')]
    >>> extract_slack_urls("derp <http://bit.ly/installfreemyapps> herp")
    [SlackURL(text='http://bit.ly/installfreemyapps', url='http://bit.ly/installfreemyapps')]
    >>> extract_slack_urls("derp google.com herp")
    []
    """

    def slack_url(wrapped_url):
        if '|' in wrapped_url:
            url, text = wrapped_url.split('|', 1)
        else:
            url = text = wrapped_url

        return SlackURL(text, url)

    wrapped_urls = re.findall(r'<(http[^>]+)>', message)

    return [slack_url(wrapped_url) for wrapped_url in wrapped_urls]


def send_message(cid, text, **kwargs):
    log.debug('Sending to CID %s: %r', cid, text)
    return requests.post('https://slack.com/api/chat.postMessage',
            params=dict(
                token=TOKEN,
                channel=cid,
                text=text,
                parse='full',
                as_user='true',
                **kwargs))


def handle_join(event):
    uid = event['user']['id']
    resp = requests.post('https://slack.com/api/im.open',
            params=dict(
                token=TOKEN,
                user=uid)).json()
    cid = resp['channel']['id']
    send_message(cid, WELCOME_MESSAGE)


def handle_message(event):
    def should_parse_urls(event):
        global _self_uid
        return (
            event.get('user') not in (None, _self_uid) and
            event.get('subtype') in (None, 'me_message')
        )

    if should_parse_urls(event):
        threading.Thread(target=parse_urls, args=(event,)).run()


def parse_urls(event):
    slack_urls = extract_slack_urls(event['text'])

    redirects = []

    for slack_url in slack_urls:
        log.debug('URL-Fetcher: Checking %s', slack_url)
        orig_url = slack_url.url
        try:
            req = requests.head(orig_url,
                    headers={'User-Agent': SNEAKY_USER_AGENT},
                    allow_redirects=True)
        except requests.RequestException:
            log.debug('Error fetching URL: %s', orig_url)
        else:
            final_url = req.url
            log.debug('Redirected URL was: %s', final_url)
            if not same_root_domains(orig_url, final_url):
                redirects.append(":mag_right: {orig_url} redirects to {final_url}".format(
                    orig_url=orig_url,
                    final_url=final_url))

    if redirects:
        send_message(event['channel'], "\n".join(redirects), unfurl_links='false')


def start_rtm():
    """Connect to slack and initiate socket handshake; returns JSON response"""
    resp = requests.post("https://slack.com/api/rtm.start",
            params=dict(
                token=TOKEN),
            verify=False)
    return resp.json()


EVENT_HANDLERS = {
    'team_join': handle_join,
    'message': handle_message,
}

def on_ws_message(ws, message):
    event = json.loads(message)
    handler = EVENT_HANDLERS.get(event['type'])
    if handler:
        handler(event)


def on_ws_error(ws, error):
    log.error('Websocket error: %r', error)


def on_ws_close(ws):
    log.warning('Websocket connection closed')


def on_ws_open(ws):
    log.info('Websocket connected')


def main():
    global _self_uid

    log.info("🤖 Berlino-Bot Boot Sequence Initiated 🤖")

    rtm_resp = start_rtm()
    _self_uid = rtm_resp['self']['id']
    log.info('Berlino-Bot UID: %s', _self_uid)
    ws_url = rtm_resp['url']
    ws = websocket.WebSocketApp(ws_url,
                                on_message=on_ws_message,
                                on_error=on_ws_error,
                                on_close=on_ws_close,
                                on_open=on_ws_open)
    #ssl_defaults = ssl.get_default_verify_paths()
    log.info('Creating websocket to %s', ws_url)
    ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})


def setup_logging():
    log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
    if log_level in ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'):
        log_level = getattr(logging, log_level)
    else:
        log_level = logging.INFO

    log.setLevel(log_level)
    fmt = logging.Formatter('[Berlino-Bot] %(levelname)s - %(name)s - %(message)s')
    h = logging.StreamHandler()
    h.setFormatter(fmt)
    logging.getLogger().addHandler(h)

if __name__ == "__main__":
    setup_logging()
    main()
