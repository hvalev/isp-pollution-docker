#!/usr/bin/env python3
__author__ = 'stsmith'

# isp_data_pollution: bandwidth-limited ISP data pollution

# Copyright 2017–2018 Steven T. Smith <steve dot t dot smith at gmail dot com>, GPL

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

# Vendored into this repository on 2026-11-08 from
# https://github.com/essandess/isp-data-pollution at commit
# 99862aba74ee4704c5366ac197191ed6ab5f0f13 (upstream's last commit), with this
# repository's fixes applied in place instead of as a patch series. Upstream is
# unmaintained; changes land here. See NOTICE for attribution.
__version__ = '2.0.1'      # the upstream release this file came from
__release__ = '0.5.0'      # this repository's release of it

import argparse as ap
import datetime as dt
import importlib
import importlib.util  # 'importlib' alone does not bind .util on modern Python
import os
import random
import re
import shutil
import signal
import sys
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.parse as uprs
import urllib.request
import urllib.robotparser as robotparser
import warnings as warn
from io import BytesIO

import fake_useragent as fake_ua
import numpy as np
import numpy.random as npr
import psutil
import requests
from fake_useragent.errors import FakeUserAgentError
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

# parse User-Agent for matching distribution
try:
    # pip install user-agents
    import user_agents as ua
except ImportError:
    ua = None
ua_parse_flag = ua is not None

# ensure pyopenssl exists to address SNI support
# https://stackoverflow.com/questions/18578439/using-requests-with-tls-doesnt-give-sni-support/18579484#18579484
if importlib.util.find_spec('OpenSSL') is None:
    msg = 'Use the pyopenssl package to enable SNI support for TLS-protected hosted domains.'
    print(msg)
    warn.warn(msg, stacklevel=2)

# headless Raspberry Pi: pyvirtualdisplay starts an Xvfb display when one is
# available. The container image runs Chromium truly headless and has no Xvfb,
# so this stays optional and is skipped when the binary is missing.
try:
    from pyvirtualdisplay.display import Display
except ImportError:
    Display = None

if Display is not None and shutil.which('Xvfb'):
    try:
        display = Display(visible=False, size=(1296, 1018))
        display.start()
    except Exception as e:  # an unavailable display must not stop the polluter
        warn.warn(f'Could not start a virtual display ({e}); continuing headless.', stacklevel=2)

# nice this process on UNIX
if hasattr(os, 'nice'):
    os.nice(15)

gb_per_month = 100		# How many gigabytes to pollute per month
max_links_cached = 100000  # Maximum number of links to cache for download
max_links_per_page = 200  # Maximum number of links to add per page
max_links_per_domain = 400  # Maximum number of links to add per domain
wordsite_url = 'http://svnweb.freebsd.org/csrg/share/dict/words?view=co&content-type=text/plain'
# Seeding searches are the slow part of a thin link library: the engines
# bot-wall headless traffic, and a bot-walled search costs a chromedriver hang
# plus a driver restart before pollute() ever reaches the page it already had.
# A search that overruns the budget puts further searches in cooldown so the
# pollute loop runs on the links it has. Both are overridable by environment.


def open_http(url, headers=None, timeout=None):
    """urlopen() that refuses anything but http(s).

    Scraped pages and blacklist feeds decide most of these URLs, so a
    ``file:`` or custom scheme reaching urlopen() would be a local-file read
    driven by remote content. Every remote fetch goes through here.
    """
    scheme = urllib.parse.urlparse(url).scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError(f"refusing to open a {scheme or 'schemeless'} URL: {url!r}")
    request = urllib.request.Request(url, headers=headers or {})  # noqa: S310  # scheme checked above
    if timeout is None:
        return urllib.request.urlopen(request)  # noqa: S310 nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected  # scheme checked above
    return urllib.request.urlopen(request, timeout=timeout)  # noqa: S310 nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected  # scheme checked above


def env_seconds(name, default):
    """Seconds from the environment, or the default for anything unusable."""
    raw = os.environ.get(name)
    if raw is None or raw == '':
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


seed_search_budget = env_seconds('SEED_SEARCH_BUDGET', 20)
seed_search_cooldown = env_seconds('SEED_SEARCH_COOLDOWN', 300)
# Seed words used when both the vendored list and the remote list are unusable.
# It has to hold several words: seed_links() asks random.sample() for up to
# three at a time, and a one-word list raises "Sample larger than population"
# on the first seeding call, which is outside the pollute loop's except guard --
# upstream's single-element ['FUBAR'] fallback therefore kills the process.
fallback_words = [
    'apple', 'bridge', 'cabin', 'delta', 'engine', 'forest', 'garden', 'harbor',
    'island', 'jungle', 'kernel', 'lantern', 'meadow', 'needle', 'orchard',
    'pendant', 'quarry', 'ridge', 'signal', 'temple', 'umbrella', 'vessel',
    'wharf', 'yellow', 'anchor', 'beacon', 'copper', 'downtown', 'ember',
]
timeout = 45
short_timeout = 10
browserdriver_rss_limit_mb = 1024  # Default maximum memory limit of browserdriver (chromedriver) processes (MB)
terminal_width = 80  # tty width, standard is 80 chars; add code to adapt later

# Shalla Secure Services shut down, so the upstream URL is dead (404; see
# upstream issue #35). Default to the Internet Archive copy of the last
# release; override with SHALLA_URL.
blacklist_url = os.environ.get(
    'SHALLA_URL',
    'https://web.archive.org/web/20210502020725if_/http://www.shallalist.de/Downloads/shallalist.tar.gz')
# Usage of the Shalla Blacklists:
# ===============================
#
# The Shalla Blacklists are property of Shalla Secure Services.
#
# This collection of url lists may be used for free for non
# commercial usage. This includes all kinds of private usage.
# The lists must not be given to any third party.

# property value distribution to match household
property_pvals = \
    {'DNT':  # Do Not Track HTTP header
        {True: 0.8, False: 0.2},
     'browser':
        {'Safari': 6, 'Firefox': 3, 'Chrome': 2, 'noneoftheabove': 1},
     'os':
        {r'Mac\s*OS': 3, r'iOS': 6, r'Linux': 1, r'Windows': 1, 'noneoftheabove': 1},
     'is_pc':
        {True: 4, False: 6},
     'is_touch_capable':
        {True: 6, False: 4},
     }
# project to simplex
for tlf in property_pvals:
    tot = 0.
    for f in property_pvals[tlf]:
        tot += abs(property_pvals[tlf][f])
    for f in property_pvals[tlf]:
        property_pvals[tlf][f] = abs(property_pvals[tlf][f]) / tot

# tell ISP that an iPad is being used
user_agent = 'Mozilla/5.0 (iPad; CPU OS 6_1 like Mac OS X) AppleWebKit/536.26 (KHTML, like Gecko) Version/6.0 Mobile/10B141 Safari/8536.25'

# Tor browser size on Linux
window_size = (1296, 1018)

# bias the content with non-random, diverse, link-heavy, popular content
seed_bias_links = ['http://my.xfinity.com/news',
                   'http://my.xfinity.com/entertainment',
                   'http://my.xfinity.com/shopping',
                   'http://www.cnbc.com/',
                   'https://news.google.com',
                   'https://news.yahoo.com',
                   'http://www.huffingtonpost.com',
                   'http://www.cnn.com',
                   'http://www.foxnews.com',
                   'http://www.nbcnews.com',
                   'http://www.usatoday.com',
                   'http://www.huffingtonpost.com',
                   'http://www.tmz.com',
                   'http://www.deadspin.com',
                   'http://www.dailycaller.com',
                   'http://www.sports.yahoo.com',
                   'http://www.espn.com',
                   'http://www.foxsports.com',
                   'http://www.finance.yahoo.com',
                   'http://www.money.msn.com',
                   'http://www.fool.com'
                   ]

# --- Docker runtime configuration (see README) ------------------------------
# BLACKLIST selects where the link filter comes from:
#   off    no filtering, and no network fetch at startup
#   local  read a domain list baked into the image (default)
#   remote download the Shalla and EasyList sources, like upstream does
blacklist_mode = os.environ.get('BLACKLIST', 'local').strip().lower()
blacklist_file = os.environ.get('BLACKLIST_FILE', '/etc/isp-data-pollution/blocklist-domains.txt')

# monkeypatch the read class method in RobotFileParser
# many sites will block access to robots.txt without a standard User-Agent header


class RobotFileParserUserAgent(robotparser.RobotFileParser):
    url: str  # provided by set_url() before read() is called

    timeout = short_timeout  # short-term timeout

    def read(self):
        """Reads the robots.txt URL and feeds it to the parser."""
        url = str(self.url or '')  # set by set_url(); may never have been set
        try:
            headers = {'User-Agent': user_agent, }
            f = open_http(url, headers=headers, timeout=self.timeout)
        except urllib.error.HTTPError as err:
            if err.code in (401, 403):
                self.disallow_all = True
            elif err.code >= 400 and err.code < 500:
                self.allow_all = True
        else:
            raw = f.read()
            self.parse(raw.decode("utf-8").splitlines())

# Notes for the future:
# 1. The bandwidth usage is undoubtedly (much) smaller because gzip encoding is used
# 2. A lightweight proxy could be used for accurate bandwidth, and header editing

# Safe search options


class SafeWebSearch:
    """ Safe web search class with default Google parameters.
Use unencrypted HTTP for ISP DPI.
"""

    def __init__(self,
                 search_url='http://www.google.com/search',  # search engine
                 query_parameter='q',                        # query parameter
                 safe_parameter='safe=active',               # query parameter for safe searches
                 css_selector='div.g',                       # css selector to harvest search results
                 additional_parameters='',                   # additional parameters required to get results
                 result_extraction=lambda x: x):             # function to extract the link
        self.search_url = search_url
        self.query_parameter = query_parameter
        self.safe_parameter = safe_parameter
        self.css_selector = css_selector
        self.additional_parameters = additional_parameters
        self.result_extraction = result_extraction


SafeGoogle = SafeWebSearch()
SafeBing = SafeWebSearch(search_url='http://www.bing.com/search',
                         safe_parameter='adlt=strict', css_selector='li.b_algo')
yahoo_search_reprog = re.compile(r'/RU=(.+?)/R[A-Z]=')
SafeYahoo = SafeWebSearch(search_url='http://search.yahoo.com/search', query_parameter='p',
                          safe_parameter='vm=r', css_selector='div.compTitle',
                          result_extraction=lambda x: yahoo_search_reprog.findall(uprs.parse_qs(x)['_ylu'][0])[0])
SafeDuckDuckGo = SafeWebSearch(search_url='http://www.duckduckgo.com/',
                               safe_parameter='kp=1', css_selector='div.result__body')


class ISPDataPollution:
    # Set by init_random_time(), which runs from inside a callback rather than
    # from __init__, so nothing else shows they exist.
    random_start_time: float
    random_interval: float

    """
    Re: https://www.eff.org/deeplinks/2017/03/senate-puts-isp-profits-over-your-privacy

I pay my ISP a lot for data usage every month. I typically don't use
all the bandwidth that I pay for.  If my ISP is going to sell my
private browsing habits, then I'm going to pollute my browsing with
noise and use all the bandwidth that I pay for. This method
accomplishes this.

If everyone uses all the data they've paid for to pollute their
browsing history, then perhaps ISPs will reconsider the business model
of selling customer's private browsing history.

The alternative of using a VPN or Tor merely pushes the issue onto to
the choice of VPN provider, complicates networking, and adds the
real issue of navigating captchas when appearing as a Tor exit node.

The crawler uses the Python requests and lxml.html libraries, is hardcoded
to download html without javascript processing, will not download
images, and respects robots.txt, which all provide good security.
    """

    def __init__(self, gb_per_month=gb_per_month,
                 max_links_cached=max_links_cached,
                 max_links_per_page=max_links_per_page,
                 max_links_per_domain=max_links_per_domain,
                 property_pvals=property_pvals,
                 user_agent=user_agent,
                 blacklist_url=blacklist_url,
                 wordsite_url=wordsite_url,
                 seed_bias_links=seed_bias_links,
                 timeout=timeout, diurnal_flag=True,
                 quit_driver_every_call=False,
                 blacklist=True, verbose=True):
        print(f'This is ISP Data Pollution 🐙💨, version {__release__} (upstream {__version__})')
        self.max_links_cached = max_links_cached
        self.max_links_per_page = max_links_per_page
        self.max_links_per_domain = max_links_per_domain
        self.property_pvals = property_pvals
        self.user_agent = user_agent
        self.blacklist_url = blacklist_url
        self.wordsite_url = wordsite_url
        self.seed_bias_links = seed_bias_links
        self.blacklist_mode = blacklist_mode
        self.blacklist_file = blacklist_file
        self.blacklist = self.blacklist_mode != 'off'
        self.verbose = verbose
        self.timeout = timeout
        self.diurnal_flag = diurnal_flag
        self.quit_driver_every_call = quit_driver_every_call
        # self.gb_per_month = gb_per_month  # set in parseArgs
        # self.debug = debug  # set in parseArgs
        self.args = self.args = self.parseArgs()
        # timeout configurable decorators
        self.chromedriver_timeout = self.block_timeout(self.chromedriver_hang_handler, \
                                                       alarm_time=self.timeout + 2, errors=(self.TimeoutError,), debug=self.debug)
        self.chromedriver_short_timeout = self.block_timeout(self.chromedriver_hang_handler, \
                                                             alarm_time=short_timeout + 2, errors=(self.TimeoutError, Exception), debug=self.debug)
        self.chromedriver_quit_timeout = self.block_timeout(self.chromedriver_quit_hang_handler, \
                                                            alarm_time=short_timeout + 2, errors=(self.TimeoutError, Exception), debug=self.debug)
        self.robots_timeout = self.block_timeout(self.robots_hang_handler, \
                                                 alarm_time=short_timeout + 2, errors=(self.TimeoutError,), debug=self.debug)
        self.check_chromedriver_version()
        self.get_useragents()
        self.hour_trigger = True
        self.twentyfour_hour_trigger = True
        self.domain_links = {}
        self.start_time = time.time()
        self.data_usage = 0
        self.get_blacklist()
        self.get_random_words()
        self.pollute_forever()

    def parseArgs(self):
        parser = ap.ArgumentParser()
        parser.add_argument('-bw', '--gb_per_month', help="GB per month", type=int, default=gb_per_month)
        parser.add_argument('-mm', '--maxmemory',
                            help="Maximum memory of chromedriver (MB); 0=>restart every link",
                            type=int, default=1024)
        parser.add_argument('-P', '--chromedriver-binary-path', help="Path to chromedriver binary", type=str, default=None)
        parser.add_argument('-p', '--proxy', help="Proxy for chromedriver", type=str, default=None)
        parser.add_argument('-g', '--debug', help="Debug flag", action='store_true')
        args = parser.parse_args()
        # Each option becomes an instance attribute; named here rather than
        # copied blindly out of the namespace, so both readers and the type
        # checker can see what the command line provides.
        self.gb_per_month = args.gb_per_month
        self.maxmemory = args.maxmemory
        self.chromedriver_binary_path = args.chromedriver_binary_path
        self.proxy = args.proxy
        self.debug = args.debug
        self.sanity_check_arguments()
        return args

    def sanity_check_arguments(self):
        self.gb_per_month = min(2048, max(1, self.gb_per_month))  # min-max bandwidth limits
        if self.maxmemory == 0:
            self.quit_driver_every_call = True
        self.chromedriver_rss_limit_mb = min(4096, max(256, self.maxmemory))  # min-max bandwidth limits

    def check_chromedriver_version(self, recommended_version=(2, 41)):
        self.open_driver()
        if self.debug:
            print("{} version is {}, chromedriver version is {}".format(self.driver.capabilities["browserName"],
                                                                        self.driver.capabilities.get("browserVersion", self.driver.capabilities.get("version", "")),
                                                                        self.driver.capabilities["chrome"]["chromedriverVersion"]))
        try:
            chromedriver_version = tuple(int(i) for i in
                                         re.sub(r'([\d.]+?) .*', '\\1', self.driver.capabilities["chrome"]["chromedriverVersion"]).split('.'))
        except (ValueError, KeyError):
            # This check only ever prints advice, so a version string we cannot
            # parse must not be able to stop the program from starting.
            warn.warn('Could not parse the chromedriver version string; skipping the version check.', stacklevel=2)
            self.quit_driver()
            return
        if chromedriver_version < recommended_version:
            warn.warn("""{} version is {};
please upgrade to at least version {} from http://chromedriver.chromium.org/downloads.
""".format(self.driver.capabilities["browserName"], self.driver.capabilities.get("browserVersion", self.driver.capabilities.get("version", "")),
                '.'.join(str(i) for i in recommended_version)), stacklevel=2)
        self.quit_driver()

    def open_driver(self):
        self.quit_driver()
        if not hasattr(self, 'driver') or not isinstance(self.driver, webdriver.chrome.webdriver.WebDriver):
            # chromedriver
            chrome_options = webdriver.ChromeOptions()
            chrome_options.add_argument('headless')
            # Docker: the container runs as root without a user-namespace
            # sandbox, and /dev/shm is small by default. Without these two
            # flags Chromium crashes on startup inside a container.
            chrome_options.add_argument('no-sandbox')
            chrome_options.add_argument('disable-dev-shm-usage')
            chrome_options.add_argument(f'user-agent={self.user_agent}')
            chrome_options.add_argument(f'window-size={window_size[0]:d},{window_size[1]:d}')
            # Disable image downloads; see https://stackoverflow.com/questions/18657976/disable-images-in-selenium-google-chromedriver
            chrome_options.add_argument('blink-settings=imagesEnabled=false')
            chrome_options.add_argument('mute-audio')
            if self.proxy is not None:
                chrome_options.add_argument(f'proxy-server={self.proxy}')
            if self.chromedriver_binary_path is None:
                driver = webdriver.Chrome(options=chrome_options)
            else:
                # Selenium 4 moved the driver binary into a Service object. The
                # old code also assigned it to chrome_options.binary_location,
                # which is the *browser* binary and could never work.
                driver = webdriver.Chrome(
                    service=ChromeService(executable_path=self.chromedriver_binary_path),
                    options=chrome_options)
            driver.set_window_size(window_size[0], window_size[1])
            driver.implicitly_wait(self.timeout)
            driver.set_page_load_timeout(self.timeout)
            driver.set_script_timeout(self.timeout)
            self.driver = driver

    def quit_driver(self, hard_quit=False, pid=None, chromedriver_short_timeout_decorator=None):
        """
        close, kill -9, quit, del
        :param hard_quit:
        :param pid:
        :return:
         """
        # Use original phantomjs code for chromedriver, even though chromedriver is likely far more robust
        # http://stackoverflow.com/questions/25110624/how-to-properly-stop-phantomjs-execution
        if chromedriver_short_timeout_decorator is None:
            chromedriver_short_timeout_decorator = self.chromedriver_short_timeout
        if hasattr(self, 'driver'):
            if not hard_quit:
                @chromedriver_short_timeout_decorator
                def chromedriver_close(): self.driver.close()
                chromedriver_close()
            try:
                if pid is None:
                    @chromedriver_short_timeout_decorator
                    def chromedriver_process_pid(): return self.driver.service.process.pid
                    pid = chromedriver_process_pid()

                @chromedriver_short_timeout_decorator
                def chromedriver_send_signal():
                    # Google Chrome is a child process of chromedriver
                    for c in psutil.Process(pid).children():
                        c.send_signal(signal.SIGTERM)
                    self.driver.service.process.send_signal(signal.SIGTERM)
                chromedriver_send_signal()
            except Exception as e:
                if self.debug:
                    print(f'.send_signal() exception:\n{e}')
                if isinstance(pid, int):
                    try:
                        # Google Chrome is a child process of chromedriver
                        for c in psutil.Process(pid).children():
                            os.kill(c.pid, signal.SIGTERM)
                        os.kill(pid, signal.SIGTERM)  # overkill (pun intended)
                    except Exception as e:
                        if self.debug:
                            print(f'.kill() exception:\n{e}')
            try:
                @chromedriver_short_timeout_decorator
                def chromedriver_quit(): self.driver.quit()
                chromedriver_quit()
            except Exception as e:
                if self.debug:
                    print(f'.quit() exception:\n{e}')
            del self.driver

    def clear_driver(self):
        # https://sqa.stackexchange.com/questions/10466/how-to-clear-localstorage-using-selenium-and-webdriver
        if hasattr(self, 'driver'):
            try:
                @self.chromedriver_short_timeout
                def chromedriver_delete_all_cookies(): self.driver.delete_all_cookies()
                chromedriver_delete_all_cookies()
            except Exception as e:
                if self.debug:
                    print(f'.delete_all_cookies() exception:\n{e}')
            try:
                @self.chromedriver_short_timeout
                def chromedriver_clear():
                    self.driver.execute_script('window.localStorage.clear();')
                    self.driver.execute_script('window.sessionStorage.clear();')
                chromedriver_clear()
            except Exception as e:
                if self.debug:
                    print(f'.execute_script() exception:\n{e}')

    def get_useragents(self):
        for attempt in range(5):
            try:
                self.fake_ua = fake_ua.UserAgent()
            except (FakeUserAgentError, urllib.error.URLError) as e:
                if self.debug:
                    print(f'.UserAgent exception #{attempt}:\n{e}')
            else:
                break
        else:
            print('Too many .UserAgent failures. Exiting.')
            sys.exit(1)

    def get_blacklist(self, update_flag=False):
        blacklist_domains = getattr(self, 'blacklist_domains', set())
        blacklist_urls = getattr(self, 'blacklist_urls', set())
        self.blacklist_domains = set()
        self.blacklist_urls = set()
        try:
            if not self.blacklist:
                raise Exception('BLACKLIST=off: no link filter will be applied.')
            elif self.blacklist_mode == 'local':
                if self.verbose:
                    print('Reading the local blacklist… ', end='', flush=True)
                self.get_local_blacklist()
                if self.verbose:
                    print('Local blacklist done.', flush=True)
            elif self.blacklist_mode == 'remote':
                if self.verbose:
                    print('Downloading the blacklists… ', end='', flush=True)
                self.get_shalla_blacklist()
                if self.verbose:
                    print('Shallalist done… ', end='', flush=True)
                self.get_easylist_blacklist()
                if self.verbose:
                    print('EasyList done.', flush=True)
            else:
                raise Exception(f'BLACKLIST must be off, local or remote (got {self.blacklist_mode!r}).')
        except Exception as e:
            if self.verbose:
                print(e)
        # Make sure blacklists are not empty. Only a failed remote download is
        # fatal: with BLACKLIST=local an unreadable BLACKLIST_FILE means "no
        # filter", and the polluter keeps working.
        if self.blacklist and self.blacklist_mode == 'remote':
            try:  # no fully empty collection of blacklists
                assert (self.blacklist_domains != set() or self.blacklist_urls != set()) \
                    and (not update_flag or (blacklist_domains != set() or blacklist_urls != set()))
            except AssertionError as e:
                print(e)
                if update_flag:
                    self.blacklist_domains = blacklist_domains
                    self.blacklist_urls = blacklist_urls
                    warn.warn('Blacklists not updated; falling back on previous blacklist download.', stacklevel=2)
                else:
                    print('Empty blacklists! Exiting.')
                    sys.exit(1)
        # ignore problem urls
        self.blacklist_urls |= {'about:blank'}

    def get_local_blacklist(self):
        """Fill the filter from a plain newline-separated domain list (patched)."""
        try:
            with open(self.blacklist_file, encoding='utf-8', errors='ignore') as fh:
                for line in fh:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        self.blacklist_domains.add(line)
        except OSError as e:
            warn.warn(f'Local blacklist {self.blacklist_file} is unreadable ({e}); running without a filter.', stacklevel=2)
            return
        if not self.blacklist_domains:
            warn.warn(f'Local blacklist {self.blacklist_file} is empty; running without a filter.', stacklevel=2)

    def get_shalla_blacklist(self):
        # http://stackoverflow.com/questions/18623842/read-contents-tarfile-into-python-seeking-backwards-is-not-allowed
        tgzstream = open_http(self.blacklist_url, headers={'User-Agent': self.user_agent})
        tmpfile = BytesIO()
        while True:
            s = tgzstream.read(16384)
            if not s:
                break
            tmpfile.write(s)
        tgzstream.close()
        tmpfile.seek(0)
        # bash$ ls BL
        # COPYRIGHT	education	isp		recreation	updatesites
        # adv		finance		jobsearch	redirector	urlshortener
        # aggressive	fortunetelling	library		religion	violence
        # alcohol		forum		military	remotecontrol	warez
        # anonvpn		gamble		models		ringtones	weapons
        # automobile	global_usage	movies		science		webmail
        # chat		government	music		searchengines	webphone
        # costtraps	hacking		news		sex		webradio
        # dating		hobby		podcasts	shopping	webtv
        # downloads	homestyle	politics	socialnet
        # drugs		hospitals	porn		spyware
        # dynamic		imagehosting	radiotv		tracker
        members = ('downloads', 'drugs', 'hacking', 'gamble', 'porn', 'spyware',
                   'updatesites', 'urlshortener', 'violence', 'warez', 'weapons')
        with tarfile.open(fileobj=tmpfile, mode='r:gz') as tgz:
            for member in members:
                for part, target in (('domains', self.blacklist_domains), ('urls', self.blacklist_urls)):
                    path = f'BL/{member}/{part}'
                    entry = tgz.extractfile(path)
                    if entry is None:  # a tarball that changed shape must not abort the whole filter
                        warn.warn(f'Blacklist member {path} is missing from the tarball; skipping it.', stacklevel=2)
                        continue
                    with entry:
                        target.update(entry.read().decode('utf-8').splitlines())
        tmpfile.close()

    def get_easylist_blacklist(self):
        # Malware lists from open source AdBlock and spam404.com lists
        spam404_com_adblock_list = 'https://raw.githubusercontent.com/Dawsey21/Lists/master/adblock-list.txt'
        spam404_com_main_blacklist = 'https://raw.githubusercontent.com/Dawsey21/Lists/master/main-blacklist.txt'  # not EasyList format
        # easylist-downloads.adblockplus.org/malwaredomains_full.txt is gone (404)
        download_list = list({spam404_com_adblock_list, spam404_com_main_blacklist})
        download_parse = {spam404_com_adblock_list: True, spam404_com_main_blacklist: False}

        for url in download_list:
            # a single dead source must not discard the ones that still work
            try:
                resp = open_http(url, headers={'User-Agent': self.user_agent})
            except Exception as e:
                warn.warn(f'Skipping unreachable blacklist source {url} ({e})', stacklevel=2)
                continue
            for line in resp:
                line = line.decode('utf-8').rstrip()
                if download_parse[url]:
                    self.parse_and_filter_rule_urls(line)
                else:
                    self.blacklist_domains |= {line}

    @staticmethod
    def word_list_from_text(text):
        """Word-shaped lines only, or [] when the text is not a word list (patched).

        A dictionary endpoint that answers with a bot challenge or an error page
        would otherwise hand HTML and minified JavaScript to the search seeder.
        """
        words = [line.strip() for line in text.splitlines()]
        words = [w for w in words if 2 < len(w) < 25 and w.isalpha()]
        return words if len(words) >= 100 else []

    def read_word_list(self, path):
        """Seed words from a vendored file, or [] if it is missing or unusable."""
        try:
            with open(path, encoding='utf-8', errors='replace') as fh:
                text = fh.read()
        except OSError:
            return []
        return self.word_list_from_text(text)

    def get_random_words(self):
        """Seed words for the search queries, vendored list first (patched).

        The dictionary URL now answers a plain HTTP client with 404 and a
        browser-user-agent client with a bot-challenge page, and every line of
        whatever came back became a search term, so the vendored list inside the
        image is tried first and the remote list is only a fallback.
        """
        path = os.environ.get('SEED_WORDS_FILE', '/etc/isp-data-pollution/seed-words.txt')
        self.words = self.read_word_list(path)
        if self.words:
            # if self.debug: print('There are {:d} words.'.format(len(self.words)))
            return
        if self.debug:
            print(f'Seed words at {path} unusable; falling back to {self.wordsite_url}...')
        try:
            reqsession = requests.Session()
            reqsession.headers.update({'User-Agent': self.user_agent})
            response = reqsession.get(self.wordsite_url, timeout=10)
            words = self.word_list_from_text(response.content.decode('utf-8', 'replace'))
            reqsession.close()
        except Exception as e:
            if self.debug:
                print(f'requests exception:\n{e}')
            words = []
        self.words = words if words else fallback_words
        # if self.debug: print('There are {:d} words.'.format(len(self.words)))

    def heartbeat(self) -> None:
        """Touch a liveness file so a container HEALTHCHECK can watch us (patched)."""
        try:
            health_file = os.environ.get('HEALTH_FILE', '/tmp/isp-data-pollution.health')  # noqa: S108  # container-private default
            with open(health_file, 'w') as fh:
                fh.write(f'{time.time():.1f} {self.data_usage:.0f}\n')
        except OSError:
            pass

    def pollute_forever(self):
        if self.verbose:
            print("""Display format:
Downloading: website.com; NNNNN links [in library], H(domain)= B bits [entropy]
Downloaded:  website.com: +LLL/NNNNN links [added], H(domain)= B bits [entropy]
""")
        self.open_driver()
        self.seed_links()
        self.clear_driver()
        if self.quit_driver_every_call:
            self.quit_driver()
        while True:  # pollute forever, pausing only to meet the bandwidth requirement
            try:
                # Tick first: exceeded_bandwidth_tasks() below can sleep for
                # minutes, and the liveness file must not look stale because we
                # are correctly throttling bandwidth.
                self.heartbeat()
                if (not self.diurnal_flag) or self.diurnal_cycle_test():
                    self.pollute()
                else:
                    time.sleep(self.chi2_mean_std(3., 1.))
                if npr.uniform() < 0.005:
                    self.set_user_agent()  # reset the user agent occasionally
                self.elapsed_time = time.time() - self.start_time
                self.exceeded_bandwidth_tasks()
                self.random_interval_tasks()
                self.every_hour_tasks()
                time.sleep(self.chi2_mean_std(0.5, 0.2))
            except Exception as e:
                if self.debug:
                    print(f'.pollute() exception:\n{e}')

    def pollute(self):
        if not self.quit_driver_every_call:
            self.check_chromedriver_process()
        if self.link_count() < 2000:
            if self.quit_driver_every_call:
                self.open_driver()
            self.seed_links()
            self.clear_driver()
            if self.quit_driver_every_call:
                self.quit_driver()
        url = self.pop_link()
        if self.verbose:
            self.print_url(url)
        if self.quit_driver_every_call:
            self.open_driver()
        self.get_url(url)
        self.clear_driver()
        if self.quit_driver_every_call:
            self.quit_driver()

    def link_count(self):
        return int(np.array([len(self.domain_links[dmn]) for dmn in self.domain_links]).sum())

    def domain_entropy(self):
        result = 0.
        domain_count = np.array([(dmn, len(self.domain_links[dmn])) for dmn in self.domain_links])
        p = np.array([float(c) for d, c in domain_count])
        count_total = p.sum()
        if count_total > 0:
            p = p / p.sum()
            result = self.entropy(p)
        return result

    def entropy(self, p):
        return -np.fromiter((self.xlgx(x) for x in p.flatten()), dtype=p.dtype).sum()

    def xlgx(self, x):
        x = np.abs(x)
        y = 0.
        if not (x == 0. or x == 1.):
            y = x * np.log2(x)
        return y

    def seed_links(self):
        # bias with non-random seed links
        self.bias_links()
        if time.time() < getattr(self, 'seed_search_cooldown_until', 0.):
            if self.debug:
                print('Seeding search on cooldown; polluting from the link library.')
            return
        if self.link_count() < self.max_links_cached:
            num_words = max(1, npr.poisson(1.33) + 1)  # mean of 1.33 words per search
            if num_words == 1:
                word = ' '.join(random.sample(self.words, num_words))
            else:
                if npr.uniform() < 0.5:
                    word = ' '.join(random.sample(self.words, num_words))
                else:      # quote the first two words together
                    word = ' '.join(['"{}"'.format(' '.join(random.sample(self.words, 2))),
                                     ' '.join(random.sample(self.words, num_words - 2))])
            if self.debug:
                print(f'Seeding with search for \'{word}\'…')
            elapsed = time.time()
            self.get_websearch(word)
            elapsed = time.time() - elapsed
            if elapsed > seed_search_budget:
                self.seed_search_cooldown_until = time.time() + seed_search_cooldown
                if self.debug:
                    msg = f'seed search {elapsed:.0f}s > {seed_search_budget:.0f}s budget'
                    print(msg + f'; not searching again for {seed_search_cooldown:.0f}s.')

    def bias_links(self):
        for url in self.seed_bias_links:
            self.add_link(url)

    def diurnal_cycle_test(self):
        now = dt.datetime.now()
        tmhr = now.hour + now.minute / 60.
        phase = npr.normal(14., 1.)
        exponent = min(0.667, self.chi2_mean_std(0.333, 0.1))

        def cospow(x, e):  # flattened cosine with e < 1
            c = np.cos(x)
            return np.sign(c) * np.power(np.abs(c), e)
        diurn = max(0., 0.5 * (1. + cospow((tmhr - phase) * (2. * np.pi / 24.), exponent)))
        flr = min(0.1, self.chi2_mean_std(0.02, 0.002))
        val = flr + (1. - flr) * diurn
        return npr.uniform() < val

    def chi2_mean_std(self, mean=1., std=0.1):
        """
        Chi-squared random variable with given mean and standard deviation.
        :param mean:
        :param std:
        :return:
        """
        scale = 2. * mean / std
        nu = mean * scale
        return npr.chisquare(nu) / scale

    def exceeded_bandwidth_tasks(self):
        if self.bandwidth_test():
            self.decimate_links(total_frac=0.81, decimate_frac=0.1)
            time.sleep(120)

    def random_interval_tasks(self, random_interval=None):
        if random_interval is None:
            random_interval = self.chi2_mean_std(2 * 3600., 3600.)

        def init_random_time():
            self.random_start_time = time.time()
            self.random_interval = self.random_start_time + random_interval
        if not hasattr(self, 'random_interval'):
            init_random_time()
        if time.time() > self.random_interval:
            init_random_time()  # reinitialize random interval
            self.current_preferred_domain = self.draw_domain()

    def every_hour_tasks(self):
        if int(self.elapsed_time / 60. % 60.) == 59:
            # reset user agent, clear out cookies, seed more links
            if self.hour_trigger:
                if hasattr(self, 'driver'):
                    self.set_user_agent()
                    if True:
                        pass
                    elif False:
                        # `set_user_agent` reopens chromedriver now
                        self.quit_driver()
                        self.open_driver()
                    else:
                        try:
                            @self.chromedriver_short_timeout
                            def chromedriver_delete_all_cookies(): self.driver.delete_all_cookies()
                            chromedriver_delete_all_cookies()
                        except Exception as e:
                            if self.debug:
                                print(f'.delete_all_cookies() exception:\n{e}')
                    self.seed_links()
                else:
                    self.open_driver()
                self.hour_trigger = False
        else:
            self.hour_trigger = True
        self.every_day_tasks()
        self.every_two_weeks_tasks()

    def every_day_tasks(self):
        if int(self.elapsed_time / 3600. % 24.) == 23:
            # clear out cookies every day, decimate, and seed more links
            if self.twentyfour_hour_trigger:
                if hasattr(self, 'driver'):
                    self.seed_links()
                    # restart the driver
                    self.quit_driver()
                    self.open_driver()
                else:
                    self.open_driver()
                    self.decimate_links(total_frac=0.667, decimate_frac=0.1)
                    self.seed_links()
                    if self.quit_driver_every_call:
                        self.quit_driver()
                self.twentyfour_hour_trigger = False
        else:
            self.twentyfour_hour_trigger = True

    def every_two_weeks_tasks(self):
        if self.elapsed_time > 3600. * 24 * 14:
            # reset bw stats and (really) decimate the stack every couple of weeks
            self.start_time = time.time()
            self.data_usage = 0
            self.decimate_links(total_frac=0.49, decimate_frac=0.333)
            self.get_blacklist(update_flag=True)  # reload the latest blacklists

    def decimate_links(self, total_frac=0.81, decimate_frac=0.1, log_sampling=False):
        """ Delete `decimate_frac` of links if the total exceeds `total_frac` of the maximum allowed. """
        if self.link_count() > int(np.ceil(total_frac * self.max_links_cached)):
            for url in self.draw_links(n=int(np.ceil(self.link_count() * decimate_frac)), log_sampling=log_sampling):
                self.remove_link(url)

    def set_user_agent(self):
        self.draw_user_agent()
        # chromedriver cannot reset the User-Agent in runtime, so it must be restarted with a new UA
        # https://stackoverflow.com/questions/50375628/how-to-change-useragent-string-in-runtime-chromedriver-selenium/50375914#50375914
        self.open_driver()

    def draw_user_agent(self, max_draws=10000):
        """Draw a random User-Agent either uniformly (mildly susceptible to ML), or from a matched distribution."""
        global user_agent
        if ua is None:  # the user-agents package is optional
            self.user_agent = self.fake_ua.random if npr.random() < 0.95 else user_agent
            return
        # Draw User-Agent from pre-defined property distribution
        property_pvals = self.property_pvals
        uap = None
        k = 0
        while k < max_draws:
            uap = ua.parse(self.fake_ua.random)
            # print(uap.ua_string)
            p_browser = property_pvals['browser']['noneoftheabove']
            for ky in property_pvals['browser']:
                if bool(re.findall(ky, uap.browser.family, flags=re.IGNORECASE)):
                    p_browser = property_pvals['browser'][ky]
                    break
            p_os = property_pvals['os']['noneoftheabove']
            for ky in property_pvals['os']:
                if bool(re.findall(ky, uap.os.family, flags=re.IGNORECASE)):
                    p_os = property_pvals['os'][ky]
                    break
            p_pc = property_pvals['is_pc'][uap.is_pc]
            p_touch_capable = property_pvals['is_touch_capable'][uap.is_touch_capable]
            if npr.uniform() <= p_browser \
                and npr.uniform() <= p_os \
                and npr.uniform() <= p_pc \
                    and npr.uniform() <= p_touch_capable:
                break
            k += 1
        self.user_agent = uap.ua_string if uap is not None else self.fake_ua.random

    def draw_link(self, log_sampling=True):
        """ Draw a single, random link. """
        return self.draw_links(n=1, log_sampling=log_sampling)[0]

    def draw_links(self, n=1, log_sampling=False):
        """ Draw multiple random links. """
        urls = []
        domain_array = np.array(list(self.domain_links))
        domain_count = np.array([len(self.domain_links[domain_array[k]]) for k in range(domain_array.shape[0])])
        p = np.array([float(c) for c in domain_count])
        count_total = p.sum()
        if log_sampling:  # log-sampling [log(x+1)] to bias lower count domains
            p = np.fromiter((np.log1p(x) for x in p), dtype=p.dtype)
        if count_total > 0:
            p = p / p.sum()
            cnts = npr.multinomial(n, pvals=p)
            if n > 1:
                for k in range(cnts.shape[0]):
                    domain = domain_array[k]
                    cnt = min(cnts[k], domain_count[k])
                    # Python 3.11 requires a sequence here; the library stores sets.
                    for url in random.sample(sorted(self.domain_links[domain]), cnt):
                        urls.append(url)
            else:
                # numpy 2 dropped the implicit size-1 array -> scalar conversion
                # this line used to rely on.
                hits = np.nonzero(cnts)[0]
                if hits.shape[0] == 0:
                    return urls
                domain = domain_array[int(hits[0])]
                url = random.sample(sorted(self.domain_links[domain]), 1)[0]
                urls.append(url)
        return urls

    def draw_domain(self, log_sampling=False):
        """ Draw a single, random domain. """
        domain = None
        domain_array = np.array(list(self.domain_links))
        domain_count = np.array([len(self.domain_links[domain_array[k]]) for k in range(domain_array.shape[0])])
        p = np.array([float(c) for c in domain_count])
        count_total = p.sum()
        if log_sampling:  # log-sampling [log(x+1)] to bias lower count domains
            p = np.fromiter((np.log1p(x) for x in p), dtype=p.dtype)
        if count_total > 0:
            p = p / p.sum()
            cnts = npr.multinomial(1, pvals=p)
            hits = np.nonzero(cnts)[0]  # numpy 2: no implicit array -> scalar
            if hits.shape[0] > 0:
                domain = domain_array[int(hits[0])]
        return domain

    def draw_link_from_domain(self, domain):
        """ Draw a single, random link from a specific domain. """
        domain_count = len(self.domain_links.get(domain, set()))
        url = random.sample(sorted(self.domain_links[domain]), 1)[0] if domain_count > 0 else None
        return url

    def pop_link(self, remove_link_fraction=0.95, current_preferred_domain_fraction=0.1):
        """ Pop a link from the collected list.
If `self.current_preferred_domain` is defined, then a link from this domain is drawn
a fraction of the time. """
        url = None
        if hasattr(self, 'current_preferred_domain') and npr.uniform() < current_preferred_domain_fraction:
            while url is not None and len(self.domain_links) > 0:  # loop until `self.current_preferred_domain` has a url
                url = self.draw_link_from_domain(self.current_preferred_domain)
                if url is None:
                    self.current_preferred_domain = self.draw_domain()
        if url is None:
            url = self.draw_link()
        if npr.uniform() < remove_link_fraction:  # 95% 1 GET, ~5% 2 GETs, .2% three GETs
            self.remove_link(url)  # pop a random item from the stack
        return url

    def add_link(self, url):
        result = False
        # Modern pages inline data:, blob: and javascript: targets in CSS and
        # JS, and the link harvesters pick them up. chromedriver cannot navigate
        # to them reliably (and clearing storage on a data: URL errors out), so
        # only http(s) is worth keeping in the link library.
        if uprs.urlparse(url).scheme.lower() not in ('http', 'https'):
            return result
        domain = self.domain_name(url)
        if self.link_count() < self.max_links_cached \
                and len(self.domain_links.get(domain, [])) < self.max_links_per_domain \
                and url not in self.domain_links.get(domain, set()):
            self.domain_links.setdefault(domain, set())
            self.domain_links[domain].add(url)
            result = True
            # if self.debug: print(f'\tAdded link \'{url}\'…')
        return result

    def remove_link(self, url):
        result = False
        domain = self.domain_name(url)
        if url in self.domain_links.get(domain, set()):
            self.domain_links[domain].remove(url)
            if len(self.domain_links[domain]) == 0:
                del self.domain_links[domain]
            result = True
        return result

    def domain_name(self, url):
        return '.'.join(uprs.urlparse(url).netloc.split('.')[-2:])

    def get_websearch(self, query):
        """
        HTTP GET of a websearch, then add any embedded links.
        :param query:
        :return:
        """
        self.select_random_search_engine()
        url = uprs.urlunparse(uprs.urlparse(self.SafeSearch.search_url)._replace(query=f'{self.SafeSearch.query_parameter}={uprs.quote_plus(query)}{self.SafeSearch.additional_parameters}&{self.SafeSearch.safe_parameter}'))
        if self.verbose:
            self.print_url(url)

        @self.chromedriver_timeout
        def chromedriver_get(): self.driver.get(url)  # selenium driver
        chromedriver_get()
        @self.chromedriver_short_timeout
        def chromedriver_page_source(): self.data_usage += len(self.driver.page_source)
        chromedriver_page_source()
        new_links = self.websearch_links()
        if self.link_count() < self.max_links_cached:
            self.add_url_links(new_links, url)

    def select_random_search_engine(self):
        self.SafeSearch = random.choice([SafeGoogle, SafeBing, SafeYahoo, SafeDuckDuckGo])
        return self.SafeSearch

    def websearch_links(self):
        """
        Webpage format for a popular search engine, <div class="g">.
        :return:
        """
        # https://github.com/detro/ghostdriver/issues/169
        @self.chromedriver_short_timeout
        def chromedriver_find_elements_by_css_selector():
            return WebDriverWait(self.driver, short_timeout).until(lambda x: x.find_elements(By.CSS_SELECTOR, self.SafeSearch.css_selector))
        elements = chromedriver_find_elements_by_css_selector()
        # get links in random order until max. per page
        k = 0
        links = []
        try:
            for elt in sorted(elements, key=lambda k: random.random()):
                @self.chromedriver_short_timeout
                def chromedriver_find_element_by_tag_name(elt=elt): return elt.find_element(By.TAG_NAME, 'a')
                a_tag = chromedriver_find_element_by_tag_name()
                @self.chromedriver_short_timeout
                def chromedriver_get_attribute(a_tag=a_tag): return a_tag.get_attribute('href')
                href = chromedriver_get_attribute()
                if href is not None:
                    href = self.SafeSearch.result_extraction(href)
                    links.append(href)
                k += 1
                if k > self.max_links_per_page or self.link_count() == self.max_links_cached:
                    break
        except Exception as e:
            if self.debug:
                print(f'.find_element_by_tag_name.get_attribute() exception:\n{e}')
        return links

    def get_url(self, url):
        """
        HTTP GET of the url, and add any embedded links.
        :param url:
        :return:
        """
        if not self.check_robots(url):
            return  # bail out if robots.txt says to

        @self.chromedriver_timeout
        def chromedriver_get(): self.driver.get(url)  # selenium driver
        chromedriver_get()
        @self.chromedriver_short_timeout
        def chromedriver_page_source(): self.data_usage += len(self.driver.page_source)
        chromedriver_page_source()
        new_links = self.url_links()
        if self.link_count() < self.max_links_cached:
            self.add_url_links(new_links, url)

    def url_links(self):
        """Generic webpage link finder format."""
        # https://github.com/detro/ghostdriver/issues/169
        @self.chromedriver_short_timeout
        def chromedriver_find_elements_by_tag_name():
            return WebDriverWait(self.driver, short_timeout).until(lambda x: x.find_elements(By.TAG_NAME, 'a'))
        elements = chromedriver_find_elements_by_tag_name()

        # get links in random order until max. per page
        k = 0
        links = []
        try:
            for a in sorted(elements, key=lambda k: random.random()):
                @self.chromedriver_short_timeout
                def chromedriver_get_attribute(a=a): return a.get_attribute('href')
                href = chromedriver_get_attribute()
                if href is not None:
                    links.append(href)
                k += 1
                if k > self.max_links_per_page or self.link_count() == self.max_links_cached:
                    break
        except Exception as e:
            if self.debug:
                print(f'.get_attribute() exception:\n{e}')
        return links

    def check_robots(self, url):
        result = True
        url_robots = f'https://{uprs.urlparse(url).netloc}/robots.txt'

        @self.robots_timeout
        def robots_read():
            rp = RobotFileParserUserAgent()
            rp.set_url(url_robots)
            rp.read()
            result = rp.can_fetch(self.user_agent, url)
            del rp      # ensure self.close() in urllib
            return result
        result = robots_read()
        return result

    def add_url_links(self, links, url=''):
        k = 0
        for link in sorted(links, key=lambda k: random.random()):
            lp = uprs.urlparse(link)
            if (lp.scheme == 'http' or lp.scheme == 'https') and not self.blacklisted(link):
                if self.add_link(link):
                    k += 1
                if k > self.max_links_per_page:
                    break
        current_url = url  # default, unless the driver can tell us better
        if self.verbose or self.debug:
            try:
                @self.chromedriver_short_timeout
                def chromedriver_current_url(): return self.driver.current_url
                current_url = chromedriver_current_url()
                # the current_url method breaks on a lot of sites, e.g.
                # python3 -c 'from selenium import webdriver; driver = webdriver.PhantomJS(); driver.get("https://github.com"); print(driver.title); print(driver.current_url); driver.quit()'
            except Exception as e:
                if self.debug:
                    print(f'.current_url exception:\n{e}')
        if self.debug:
            print(f"{current_url}: {k:d} links added, {self.link_count():d} total, {self.domain_entropy():.1f} bits domain entropy")
        elif self.verbose:
            self.print_progress(current_url, num_links=k)

    def print_url(self, url):
        if self.debug:
            print(url + ' …')
        else:
            self.print_progress(url)

    def print_progress(self, url, num_links=None):
        if num_links is not None:
            text_suffix = f': +{num_links:d}/{self.link_count():d} links, H(domain)={self.domain_entropy():.1f} b'
        else:
            text_suffix = f'; {self.link_count():d} links, H(domain)={self.domain_entropy():.1f} b …'
        self.print_truncated_line(url, text_suffix)

    def print_truncated_line(self, url, text_suffix='', terminal_width=terminal_width):
        """
        Print truncated `url` + `text_suffix` to fill `terminal_width`
        :param url:
        :param text_suffix:
        :param terminal_width:
        :return:
        """
        chars_used = len(text_suffix)
        if text_suffix == '…':
            if len(url) >= terminal_width:
                url = url[:terminal_width - 1]  # add '…' below
            elif len(url) < terminal_width - 1:
                url += ' '  # add an extra space before the ellipsis
        else:
            if len(url) + chars_used > terminal_width:
                url = url[:terminal_width - chars_used - 1] + '…'
        text = f"{url}{text_suffix}"  # added white space necessary
        text = text[:min(terminal_width, len(text))] + ' ' * max(0, terminal_width - len(text))
        print(text, end='', flush=True)
        time.sleep(0.01)
        print('\r', end='', flush=True)

    def blacklisted(self, link):
        return link in self.blacklist_urls or self.domain_name(link) in self.blacklist_domains

    def bandwidth_test(self):
        running_bandwidth = self.data_usage / (self.elapsed_time + 900.)
        running_bandwidth = running_bandwidth / 407.  # Convert to GB/month, 2**30/(3600*24*30.5)
        # if self.debug: print(f'Using {running_bandwidth} GB/month')
        return running_bandwidth > self.gb_per_month

    # handle chromedriver timeouts
    # configurable decorator to timeout chromedriver and robotparser calls
    # http://stackoverflow.com/questions/15572288/general-decorator-to-wrap-try-except-in-python
    # Syntax:
    # chromedriver_timeout = block_timeout(chromedriver_hang_handler)
    # @chromedriver_timeout
    # def chromedriver_block():
    #     # chromedriver stuff
    #     pass
    # chromedriver_block()

    def block_timeout(self, hang_handler, alarm_time=timeout, errors=(Exception,), debug=False):
        def decorator(func):
            def call_func(*args, **kwargs):
                signal.signal(signal.SIGALRM, hang_handler)  # register hang handler
                signal.alarm(alarm_time)  # set an alarm
                result = None
                try:
                    result = func(*args, **kwargs)
                except errors as e:
                    if debug:
                        print(f'{func.__name__} exception:\n{e}')
                finally:
                    signal.alarm(0)  # cancel the alarm
                return result
            return call_func
        return decorator

    class TimeoutError(Exception):
        pass

    def chromedriver_hang_handler(self, signum, frame):
        # https://github.com/detro/ghostdriver/issues/334
        # http://stackoverflow.com/questions/492519/timeout-on-a-function-call
        if self.debug:
            print('Looks like chromedriver has hung.')
        try:
            self.quit_driver(chromedriver_short_timeout_decorator=self.chromedriver_quit_timeout)
        except Exception as e:
            if self.debug:
                print(e)
        self.open_driver()

    def chromedriver_quit_hang_handler(self, signum, frame):
        raise self.TimeoutError('chromedriver .quit method is taking too long')

    def robots_hang_handler(self, signum, frame):
        if self.debug:
            print('Looks like robotparser has hung.')
        raise self.TimeoutError('robotparser is taking too long')

    def check_chromedriver_process(self) -> bool:
        """
        Check if chromedriver is running.
        :return:
        """
        # Check rss and restart if too large, then check existence
        # http://stackoverflow.com/questions/568271/how-to-check-if-there-exists-a-process-with-a-given-pid-in-python
        try:
            if not hasattr(self, 'driver'):
                self.open_driver()
            pid, rss_mb = self.chromedriver_pid_and_memory()
            if rss_mb > self.chromedriver_rss_limit_mb:  # memory limit
                self.quit_driver(pid=pid)
                self.open_driver()
                pid, _ = self.chromedriver_pid_and_memory()
            # check existence
            os.kill(pid, 0)
        except (OSError, psutil.NoSuchProcess, Exception) as e:
            if self.debug:
                print(f'.chromedriver_pid_and_memory() exception:\n{e}')
            if issubclass(type(e), psutil.NoSuchProcess):
                raise Exception("There's a chromedriver zombie, and the thread shouldn't have reached this statement.") from e
            return False
        else:
            return True

    def chromedriver_pid_and_memory(self) -> tuple[int, float]:
        """ Return the pid and memory (MB) of the chromedriver process,
        restart if it's a zombie, and exit if a restart isn't working
        after three attempts. """
        pid = None
        rss_mb = 0.0
        for _k in range(3):    # three strikes
            try:
                @self.chromedriver_short_timeout
                def chromedriver_process_pid(): return self.driver.service.process.pid
                pid = chromedriver_process_pid()
                rss_mb = psutil.Process(pid).memory_info().rss / float(2 ** 20)
                return (pid, rss_mb)
            except (psutil.NoSuchProcess, Exception) as e:
                if self.debug:
                    print(f'.service.process.pid exception:\n{e}')
                if pid is not None:
                    self.quit_driver(pid=pid)
                self.open_driver()
        else:  # throw in the towel and exit if no viable chromedriver process after multiple attempts
            print('No viable chromedriver process after multiple attempts!')
            sys.exit(1)

    def parse_and_filter_rule_urls(self, line):
        """Convert EasyList domain anchor rule to domain or url."""
        line = line.rstrip()
        # filter out configuration, comment, exception lines, domain-specific, and selector rules
        if re_test(configuration_re, line) or re_test(comment_re, line) or re_test(exception_re, line) or re_test(
                domain_option_re, line) or re_test(selector_re, line):
            return
        if re_test(option_re, line):
            line = option_re.sub('\\1', line)  # delete all the options and continue
        # ignore these cases
        # blank url case: ignore
        if re_test(httpempty_re, line):
            return
        # blank line case: ignore
        if not bool(line):
            return
        # parse all remaining rules
        # treat each of the these cases separately
        # regex case: ignore
        if re_test(regex_re, line):
            return
        # now that regex's are handled, delete unnecessary wildcards, e.g. /.../*
        line = wildcard_begend_re.sub('\\1', line)
        # domain anchors, || or '|http://a.b' -> domain anchor 'a.b' for regex efficiency in JS
        if re_test(domain_anch_re, line) or re_test(scheme_anchor_re, line):
            # strip off initial || or |scheme://
            if re_test(domain_anch_re, line):
                line = domain_anch_re.sub('\\1', line)
            elif re_test(scheme_anchor_re, line):
                line = scheme_anchor_re.sub("", line)
            # host subcase
            if re_test(da_hostonly_re, line):
                line = da_hostonly_re.sub('\\1', line)
                if not re_test(wild_anch_sep_exc_re, line):  # exact subsubcase
                    if wildcard_ignore_test(line):
                        return
                    self.blacklist_domains |= {line}
                    return line
                else:
                    return  # regex subsubcase
            # hostpath subcase
            if re_test(da_hostpath_re, line):
                line = da_hostpath_re.sub('\\1', line)
                if not re_test(wild_sep_exc_noanch_re, line) and re_test(pathend_re, line):  # exact subsubcase
                    line = re.sub(r'[/|]$', '', line)  # strip EOL slashes and anchors
                    if wildcard_ignore_test(line):
                        return
                    self.blacklist_urls |= {line}
                    return line
                else:
                    return  # regex subsubcase
            # hostpathquery default case
            if wildcard_ignore_test(line):
                return
            self.blacklist_urls |= {line}
            return line
        # all other non-regex patterns in for the path parts: ignore
        return


# EasyList regular expressions
# See https://github.com/essandess/easylist-pac-privoxy
comment_re = re.compile(r'^\s*?!')   # ! comment
configuration_re = re.compile(r'^\s*?\[[^]]*?\]')  # [Adblock Plus 2.0]
easylist_opts = r'~?\b(?:third\-party|domain|script|image|stylesheet|object(?!-subrequest)|object\-subrequest|xmlhttprequest|subdocument|ping|websocket|webrtc|document|elemhide|generichide|genericblock|other|sitekey|match-case|collapse|donottrack|popup|media|font)\b'
option_re = re.compile(r'^(.*?)\$(' + easylist_opts + r'.*?)$')
# regex's used to exclude options for specific cases
domain_option_re = re.compile(r'\$.*?(?:domain=)')  # discards rules specific to links from specific domains
selector_re = re.compile(r'^(.*?)#\@?#*?.*?$')  # @##div [should be #+?, but old style still used]
regex_re = re.compile(r'^\@{0,2}\/(.*?)\/$')
wildcard_begend_re = re.compile(r'^(?:\**?([^*]*?)\*+?|\*+?([^*]*?)\**?)$')
wild_anch_sep_exc_re = re.compile(r'[*|^@]')
wild_sep_exc_noanch_re = re.compile(r'(?:[*^@]|\|[\s\S])')
exception_re = re.compile(r'^@@(.*?)$')
httpempty_re = re.compile(r'^\|?https?://$')
pathend_re = re.compile(r'(?i)(?:[/|]$|\.(?:jsp?|php|xml|jpe?g|png|p?gif|img|swf|flv|[sp]?html?|f?cgi|pl?|aspx|ashx|css|jsonp?|asp|search|cfm|ico|act|act(?:ion)?|spy|do|stm|cms|txt|imu|dll|io|smjs|xhr|ount|bin|py|dyn|gne|mvc|lv|nap|jam|nhn))', re.IGNORECASE)

domain_anch_re = re.compile(r'^\|\|(.+?)$')
# omit scheme from start of rule -- this will also be done in JS for efficiency
scheme_anchor_re = re.compile(r'^(\|?(?:[\w*+-]{1,15})?://)')  # e.g. '|http://' at start

# (Almost) fully-qualified domain name extraction (with EasyList wildcards)
# Example case: banner.3ddownloads.com^
da_hostonly_re = re.compile(r'^((?:[\w*-]+\.)+[a-zA-Z0-9*-]{1,24}\.?)(?:$|[/^?])$')
da_hostpath_re = re.compile(r'^((?:[\w*-]+\.)+[a-zA-Z0-9*-]{1,24}\.?[\w~%./^*-]+?)\??$')


def re_test(regex, string):
    if isinstance(regex, str):
        regex = re.compile(regex)
    return bool(regex.search(string))


def wildcard_ignore_test(rule):
    return bool(wild_anch_sep_exc_re.search(rule))


if __name__ == "__main__":
    ISPDataPollution()
