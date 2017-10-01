import websocket
import json
import requests
import urllib
import os
import ssl
from collections import namedtuple
import re
import urlparse

###VARIABLES THAT YOU NEED TO SET MANUALLY IF NOT ON HEROKU#####
try:
	MESSAGE = os.environ['WELCOME-MESSAGE'] 
	TOKEN = os.environ['SLACK-TOKEN']
except:
	MESSAGE = 'Manually set the Message if youre not running through heroku or have not set vars in ENV'
	TOKEN = 'Manually set the API Token if youre not running through heroku or have not set vars in ENV'
###############################################################

redirection_prefix = "Redirect alert:"

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


def is_regular_message(message):
    return (
        message['user'] != "USLACKBOT" and
        message['type'] == "message" and
        'subtype' not in message and
        not message["text"].startswith(redirection_prefix)
    )


def send_message(cid, message):
    return requests.post("https://slack.com/api/chat.postMessage?token="+TOKEN+"&channel="+cid+"&text="+urllib.quote(message)+"&parse=full&as_user=true")


def parse_join(message):
    m = json.loads(message)

    if m['type'] == "team_join":
        x = requests.get("https://slack.com/api/im.open?token="+TOKEN+"&user="+m["user"]["id"])
        x = x.json()
        x = x["channel"]["id"]
        send_message(x, MESSAGE)

        #DEBUG
        #print '\033[91m' + "HELLO SENT" + m["user"]["id"] + '\033[0m'
        #
    elif is_regular_message(m):
        cid = m["channel"]
        slack_urls = extract_slack_urls(m["text"])

        for slack_url in slack_urls:
            req = requests.get(slack_url.transformed)
            if not is_human_equal(slack_url.transformed, req.url):
                message = " ".join([redirection_prefix, slack_url.original, "redirects to", req.url])
                send_message(cid, message)


def start_rtm():
    """Connect to slack and initiate socket handshake; returns JSON response"""
    r = requests.get("https://slack.com/api/rtm.start?token="+TOKEN, verify=False)
    r = r.json()
    r = r["url"]
    return r


def on_message(ws, message):
    parse_join(message)


def on_error(ws, error):
    print "SOME ERROR HAS HAPPENED", error


def on_close(ws):
    print '\033[91m'+"Connection Closed"+'\033[0m'


def on_open(ws):
    print "Connection Started - Auto Greeting new joiners to the network"


if __name__ == "__main__":
    r = start_rtm()
    ws = websocket.WebSocketApp(r, on_message = on_message, on_error = on_error, on_close = on_close)
    #ws.on_open
    ssl_defaults = ssl.get_default_verify_paths()
    ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})
