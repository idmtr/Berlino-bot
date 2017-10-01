#!/usr/bin/env python
# -*- coding: utf-8 -*-
import logging
import websocket
import json
import requests
import os
import ssl
import re
import urlparse
from collections import namedtuple

log = logging.getLogger(__name__)

###VARIABLES THAT YOU NEED TO SET MANUALLY IF NOT ON HEROKU#####
try:
	WELCOME_MESSAGE = os.environ['WELCOME-MESSAGE']
	TOKEN = os.environ['SLACK-TOKEN']
except:
	WELCOME_MESSAGE = 'Manually set the Message if youre not running through heroku or have not set vars in ENV'
	TOKEN = 'Manually set the API Token if youre not running through heroku or have not set vars in ENV'
###############################################################

_self_uid = None

SlackURL = namedtuple('SlackURL', ['original', 'transformed'])


def normalize_url_human(url):
    """
    >>> normalize_url_human("http://www.google.com").geturl()
    '//google.com'
    >>> normalize_url_human("https://google.com").geturl()
    '//google.com'
    >>> normalize_url_human("https://google.com/").geturl()
    '//google.com'
    >>> normalize_url_human("https://google.com/derp").geturl()
    '//google.com/derp'
    """

    parsed_url = urlparse.urlparse(url)
    dict_ = parsed_url._asdict()
    dict_['scheme'] = ""
    dict_['netloc'] = dict_['netloc'][4:] if dict_['netloc'].startswith("www.") else dict_['netloc']
    dict_['path'] = "" if dict_['path'] == "/" else dict_['path']

    return urlparse.ParseResult(**dict_)


def is_human_equal(url1, url2):
    """
    >>> is_human_equal("http://google.com/", "http://google.com/")
    True
    >>> is_human_equal("http://google.com/", "https://google.com/")
    True
    >>> is_human_equal("http://google.com/", "http://bing.com/")
    False
    >>> is_human_equal("http://google.com/", "http://www.google.com/")
    True
    >>> is_human_equal("http://google.com", "http://google.com/")
    True
    """

    return normalize_url_human(url1) == normalize_url_human(url2)


def extract_slack_urls(message):
    """
    >>> extract_slack_urls("derp <http://google.com|google.com> herp")
    [SlackURL(original='google.com', transformed='http://google.com')]
    >>> extract_slack_urls("derp <http://google.com|google.com> <http://bing.com|bing.com> herp")
    [SlackURL(original='google.com', transformed='http://google.com'), SlackURL(original='bing.com', transformed='http://bing.com')]
    >>> extract_slack_urls("derp <http://bit.ly/installfreemyapps> herp")
    [SlackURL(original='http://bit.ly/installfreemyapps', transformed='http://bit.ly/installfreemyapps')]
    >>> extract_slack_urls("derp google.com herp")
    []
    """

    def slack_url(wrapped_url):
        if '|' in wrapped_url:
            transformed_url, original_url = wrapped_url.split('|', 1)
        else:
            transformed_url = original_url = wrapped_url

        return SlackURL(original_url, transformed_url)

    wrapped_urls = re.findall(r'<(http[^>]+)>', message)

    return [slack_url(wrapped_url) for wrapped_url in wrapped_urls]


def send_message(cid, text):
    log.debug('Sending to CID %s: %r', cid, text)
    return requests.post('https://slack.com/api/chat.postMessage',
            params=dict(
                token=TOKEN,
                channel=cid,
                text=text,
                parse='full',
                as_user='true'))


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
            event['user'] != _self_uid and
            event.get('subtype', None) in
                (None, 'me_message')
        )

    if should_parse_urls(event):
        cid = event['channel']
        slack_urls = extract_slack_urls(event['text'])

        redirects = []

        for slack_url in slack_urls:
            log.debug('URL-Fetcher: Checking %s', slack_url)
            req = requests.head(slack_url.transformed, allows_redirects=True)
            final_url = req.url
            log.debug('Redirected URL was: %s', final_url)
            if not is_human_equal(slack_url.transformed, final_url):
                redirects.append("{url} redirects to {final_url}".format(
                    url=slack_url.original, final_url=final_url))

        if redirects:
            notice = "Redirection notice: {}".format(", ".join(redirects))
            send_message(cid, notice)


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
