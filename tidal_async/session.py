import base64
import hashlib
import os
import urllib.parse

import aiohttp

from tidal_async import Track, Album, TidalObject
from tidal_async.exceptions import AuthorizationNeeded, AlreadyLoggedIn, AuthorizationError


class TidalSession(object):
    _redirect_uri = "https://tidal.com/android/login/auth"  # or tidal://login/auth
    _api_base_url = "https://api.tidal.com/"
    _oauth_authorize_url = "https://login.tidal.com/authorize"
    _oauth_token_url = "https://auth.tidal.com/v1/oauth2/token"

    def __init__(self, client_id, interactive_auth_url_getter):
        self.client_id = client_id
        self.sess = aiohttp.ClientSession()
        self._interactive_auth_getter = interactive_auth_url_getter

        self._auth_info = None
        self._refresh_token = None

    @property
    def _access_token(self):
        if self._auth_info is None:
            raise AuthorizationNeeded
        return self._auth_info['access_token']

    @property
    def _token_type(self):
        if self._auth_info is None:
            raise AuthorizationNeeded
        return self._auth_info['token_type']

    @property
    def country_code(self):
        if self._auth_info is None:
            raise AuthorizationNeeded
        return self._auth_info['user']['countryCode']

    async def login(self):
        if self._auth_info is not None:
            # TODO: refresh session
            raise AlreadyLoggedIn

        # https://tools.ietf.org/html/rfc7636#appendix-B
        code_verifier = base64.urlsafe_b64encode(os.urandom(32))[:-1]
        code_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier).digest())[:-1]

        qs = urllib.parse.urlencode({
            "response_type": "code",
            "redirect_uri": self._redirect_uri,
            "client_id": self.client_id,
            "appMode": "android",
            "code_challenge": code_challenge.decode('ascii'),
            "code_challenge_method": "S256",
            "restrict_signup": "true"
        })

        authorization_url = urllib.parse.urljoin(self._oauth_authorize_url, "?" + qs)

        auth_url = await self._interactive_auth_getter(authorization_url)

        code = urllib.parse.parse_qs(urllib.parse.urlsplit(auth_url).query)['code'][0]

        async with self.sess.post(self._oauth_token_url, data={
            "code": code,
            "client_id": self.client_id,
            "grant_type": "authorization_code",
            "redirect_uri": self._redirect_uri,
            "scope": "r_usr w_usr w_sub",
            "code_verifier": code_verifier.decode('ascii'),
        }) as resp:
            data = await resp.json()
            if resp.status != 200:
                raise AuthorizationError(data['error'], data['error_description'])
            self._auth_info = data
            self._refresh_token = data['refresh_token']

    async def request(self, method, url, auth=True, headers=None, autorefresh=True, **kwargs):
        url = urllib.parse.urljoin(self._api_base_url, url)
        headers_ = {} if headers is None else headers
        if auth:
            headers_.update({
                "X-Tidal-Token": self.client_id,
                "Authorization": f"{self._token_type} {self._access_token}"
            })

        resp = await self.sess.request(method, url, headers=headers_, **kwargs)
        if autorefresh and resp.status == 401 and (await resp.json())['subStatus'] == 11003:
            await self.refresh_session()
            return await self.request(method, url, auth, headers, False, **kwargs)
        else:
            resp.raise_for_status()

        return resp

    async def get(self, url, **kwargs):
        return await self.request("GET", url, **kwargs)

    async def post(self, url, **kwargs):
        return await self.request("POST", url, **kwargs)

    async def logout(self):
        # TODO
        # WTF, android app doesn't send any request when clicking "Log out" button
        raise NotImplemented

    async def refresh_session(self):
        if self._refresh_token is None:
            raise AuthorizationNeeded
        async with self.sess.post(self._oauth_token_url, data={
            "client_id": self.client_id,
            "grant_type": "refresh_token",
            "scope": "r_usr w_usr w_sub",
            "refresh_token": self._refresh_token,
        }) as resp:
            data = await resp.json()
            if resp.status != 200:
                raise AuthorizationError(data['error'], data['error_description'])
            self._auth_info = data

    async def close(self):
        await self.sess.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def track(self, track_id):
        return await Track.from_id(self, track_id)

    async def album(self, album_id):
        return await Album.from_id(self, album_id)

    # TODO: Move to the utils
    def _find_tidal_urls(self, str):
        words = str.split(' ')
        urls = []

        for word in words:
            if word[:8] == 'https://' or word[:7] == 'http://':
                if 'tidal.com/' in word:
                    for cls in TidalObject.__subclasses__():
                        if hasattr(cls, 'urlname') and cls.urlname + '/' in word:
                            urls.append(word)
                            break

        return urls

    async def objects_from_str(self, string):
        return [TidalObject.from_url(self, url) for url in self.find_tidal_urls(string)]


class TidalMultiSession(TidalSession):
    # It helps with downloading multiple tracks simultaneously and overriding region lock
    # TODO: run request on random session
    # TODO: retry failed (404) requests (regionlock) on next session
    # TODO: try file download request on all sessions in queue fullness order
    #  (tidal blocks downloading of files simultaneously)
    def __init__(self, client_id, interactive_auth_url_getter):
        self.sessions = []
        self.client_id = client_id
        self._interactive_auth_getter = interactive_auth_url_getter

    async def add_session(self):
        sess = TidalSession(self.client_id, self._interactive_auth_getter)
        await sess.login()
        self.sessions.append(sess)

    async def login(self):
        raise NotImplemented

    async def logout(self, sess_num=None):
        if sess_num is None:
            for s in self.sessions:
                s.logout()
        else:
            if sess_num < len(self.sessions):
                self.sessions[sess_num].logout()
                del self.sessions[sess_num]

    async def close(self):
        for s in self.sessions:
            await s.close()
