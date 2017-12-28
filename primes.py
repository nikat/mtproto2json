#!/usr/bin/env python3.6
"""This is a prototype module for Telegram client
"""


__author__ = "Nikita Miropolskiy"
__email__ = "nikita@miropolskiy.com"
__license__ = "https://creativecommons.org/licenses/by-nc-nd/4.0/legalcode"


# TODO: implement is_safe_dh_prime as described here:
# https://core.telegram.org/mtproto/auth_key#presenting-proof-of-work-server-authentication
# TODO: tests

import random
import math

from byteutils import sha256


# Pollard-Rho-Brent integer factorization
# https://comeoncodeon.wordpress.com/2010/09/18/pollard-rho-brent-integer-factorization/
def _brent(N):
    if N % 2 == 0:
        return 2
    y, c, m = random.randint(1, N - 1), random.randint(1, N - 1), random.randint(1, N - 1)
    g, r, q = 1, 1, 1
    while g == 1:
        x = y
        for i in range(r):
            y = ((y * y) % N + c) % N
        k = 0
        while k < r and g == 1:
            ys = y
            for i in range(min(m, r - k)):
                y = ((y * y) % N + c) % N
                q = q * (abs(x - y)) % N
            g = math.gcd(q, N)
            k = k + m
        r = r * 2
    if g == N:
        while True:
            ys = ((ys * ys) % N + c) % N
            g = math.gcd(abs(x - ys), N)
            if g > 1:
                break

    return g


def factorize(pq: int):
    p = _brent(pq)
    q = pq//p
    return min(p, q), max(p, q)

_C7_prime = int('C71CAEB9C6B1C9048E6C522F70F13F73980D40238E3E21C14934D037563D930F'
                '48198A0AA7C14058229493D22530F4DBFA336F6E0AC925139543AED44CCE7C37'
                '20FD51F69458705AC68CD4FE6B6B13ABDC9746512969328454F18FAF8C595F64'
                '2477FE96BB2A941D5BCD1D4AC8CC49880708FA9B378E3C4F3A9060BEE67CF9A4'
                'A4A695811051907E162753B56B0F6B410DBA74D8A84B2A14B3144E0EF1284754'
                'FD17ED950D5965B4B9DD46582DB1178D169C6BC465B0D6FF9CA3928FEF5B9AE4'
                'E418FC15E83EBEA0F87FA9FF5EED70050DED2849F47BF959D956850CE929851F'
                '0D8115F635B105EE2E4E15D04B2454BF6F4FADF034B10403119CD8E3B92FCC5B', 16)


def is_safe_dh_prime(g, n):
    if g != 3:
        return False
    if n == _C7_prime:
        return True
    print('The server has changed the DH_prime number. This is suspicious. '
          'Lets stop now and check this manually, later. New DH_prime = %X' % n)
    return False


# tests
if __name__ == '__main__':
    pass
