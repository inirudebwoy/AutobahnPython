###############################################################################
#
# The MIT License (MIT)
#
# Copyright (c) Tavendo GmbH
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
###############################################################################

from __future__ import absolute_import

import os
import base64
import six
import struct
import time
import binascii
import hmac
import hashlib
import random
from struct import Struct
from operator import xor
from itertools import starmap

__all__ = (
    'pbkdf2',
    'generate_totp_secret',
    'compute_totp',
    'derive_key',
    'generate_wcs',
    'compute_wcs')


def generate_totp_secret(length=10):
    """
    Generates a new Base32 encoded, random secret.

    .. seealso:: http://en.wikipedia.org/wiki/Base32

    :param length: The length of the entropy used to generate the secret.
    :type length: int

    :returns: The generated secret in Base32 (letters ``A-Z`` and digits ``2-7``).
       The length of the generated secret is ``length * 8 / 5`` octets.
    :rtype: bytes
    """
    assert(type(length) in six.integer_types)
    return base64.b32encode(os.urandom(length))


def compute_totp(secret, offset=0):
    """
    Computes the current TOTP code.

    :param secret: Base32 encoded secret.
    :type secret: bytes
    :param offset: Time offset for which to compute TOTP.
    :type offset: int

    :returns: TOTP for current time (+/- offset).
    :rtype: bytes
    """
    assert(type(secret) == bytes)
    assert(type(offset) in six.integer_types)
    try:
        key = base64.b32decode(secret)
    except TypeError:
        raise Exception('invalid secret')
    interval = offset + int(time.time()) // 30
    msg = struct.pack('>Q', interval)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    o = 15 & (digest[19] if six.PY3 else ord(digest[19]))
    token = (struct.unpack('>I', digest[o:o + 4])[0] & 0x7fffffff) % 1000000
    return '{0:06d}'.format(token).encode('ascii')


##
# The following code is adapted from the pbkdf2_bin() function
# in here https://github.com/mitsuhiko/python-pbkdf2
# Copyright 2011 by Armin Ronacher. Licensed under BSD license.
# https://github.com/mitsuhiko/python-pbkdf2/blob/master/LICENSE
##
_pack_int = Struct('>I').pack

if six.PY3:

    def _pseudorandom(x, mac):
        h = mac.copy()
        h.update(x)
        return h.digest()

    def _pbkdf2(data, salt, iterations, keylen, hashfunc):
        mac = hmac.new(data, None, hashfunc)
        buf = []
        for block in range(1, -(-keylen // mac.digest_size) + 1):
            rv = u = _pseudorandom(salt + _pack_int(block), mac)
            for i in range(iterations - 1):
                u = _pseudorandom(u, mac)
                rv = starmap(xor, zip(rv, u))
            buf.extend(rv)
        return bytes(buf)[:keylen]

else:
    from itertools import izip

    def _pseudorandom(x, mac):
        h = mac.copy()
        h.update(x)
        return map(ord, h.digest())

    def _pbkdf2(data, salt, iterations, keylen, hashfunc):
        mac = hmac.new(data, None, hashfunc)
        buf = []
        for block in xrange(1, -(-keylen // mac.digest_size) + 1):
            rv = u = _pseudorandom(salt + _pack_int(block), mac)
            for i in xrange(iterations - 1):
                u = _pseudorandom(''.join(map(chr, u)), mac)
                rv = starmap(xor, izip(rv, u))
            buf.extend(rv)
        return ''.join(map(chr, buf))[:keylen]


def pbkdf2(data, salt, iterations=1000, keylen=32, hashfunc=None):
    """
    Returns a binary digest for the PBKDF2 hash algorithm of ``data``
    with the given ``salt``. It iterates ``iterations`` time and produces a
    key of ``keylen`` bytes. By default SHA-256 is used as hash function,
    a different hashlib ``hashfunc`` can be provided.

    :param data: The data for which to compute the PBKDF2 derived key.
    :type data: bytes
    :param salt: The salt to use for deriving the key.
    :type salt: bytes
    :param iterations: The number of iterations to perform in PBKDF2.
    :type iterations: int
    :param keylen: The length of the cryptographic key to derive.
    :type keylen: int
    :param hashfunc: The hash function to use, e.g. ``hashlib.sha1``.
    :type hashfunc: callable

    :returns: The derived cryptographic key.
    :rtype: bytes
    """
    assert(type(data) == bytes)
    assert(type(salt) == bytes)
    assert(type(iterations) in six.integer_types)
    assert(type(keylen) in six.integer_types)
    return _pbkdf2(data, salt, iterations, keylen, hashfunc or hashlib.sha256)


def derive_key(secret, salt, iterations=1000, keylen=32):
    """
    Computes a derived cryptographic key from a password according to PBKDF2.

    .. seealso:: http://en.wikipedia.org/wiki/PBKDF2

    :param secret: The secret.
    :type secret: bytes
    :param salt: The salt to be used.
    :type salt: bytes
    :param iterations: Number of iterations of derivation algorithm to run.
    :type iterations: int
    :param keylen: Length of the key to derive in bits.
    :type keylen: int

    :return: The derived key in Base64 encoding.
    :rtype: bytes
    """
    assert(type(secret) == bytes)
    assert(type(salt) == bytes)
    assert(type(iterations) in six.integer_types)
    assert(type(keylen) in six.integer_types)
    key = pbkdf2(secret, salt, iterations, keylen)
    return binascii.b2a_base64(key).strip()


WCS_SECRET_CHARSET = u"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
"""
The characters from which :func:`autobahn.wamp.auth.generate_wcs` generates secrets.
"""


def generate_wcs(length=14):
    """
    Generates a new random secret for use with WAMP-CRA.

    The secret generated is a random character sequence drawn from

    - upper and lower case latin letters
    - digits
    -

    :param length: The length of the secret to generate.
    :type length: int

    :return: The generated secret. The length of the generated is ``length`` octets.
    :rtype: bytes
    """
    assert(type(length) in six.integer_types)
    return u"".join([random.choice(WCS_SECRET_CHARSET) for _ in range(length)]).encode('ascii')


def compute_wcs(key, challenge):
    """
    Compute an WAMP-CRA authentication signature from an authentication
    challenge and a (derived) key.

    :param key: The key derived (via PBKDF2) from the secret.
    :type key: bytes
    :param challenge: The authentication challenge to sign.
    :type challenge: bytes

    :return: The authentication signature.
    :rtype: bytes
    """
    assert(type(key) == bytes)
    assert(type(challenge) == bytes)
    sig = hmac.new(key, challenge, hashlib.sha256).digest()
    return binascii.b2a_base64(sig).strip()
