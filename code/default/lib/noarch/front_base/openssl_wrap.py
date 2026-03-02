
# this wrap has a close callback.
# Which is used by ip manager.
# ip manager keep a connection number counter for every ip.

# Keep a single TLS backend on Python 3 so runtime behavior is explicit and
# does not depend on optional third-party binary modules.

import sys

implementation = None

def init():
    global implementation
    if sys.version_info[0] == 3:
        from .ssl_wrap import SSLConnection, SSLContext, SSLCert

        implementation = "ssl"
    else:
        from .pyopenssl_wrap import SSLConnection, SSLContext, SSLCert
        implementation = "OpenSSL"

    return SSLConnection, SSLContext, SSLCert


SSLConnection, SSLContext, SSLCert = init()
