
# this wrap has a close callback.
# Which is used by ip manager.
# ip manager keep a connection number counter for every ip.

# Keep a single TLS backend on Python 3 so runtime behavior is explicit and
# does not depend on optional third-party binary modules.

implementation = "ssl"

from .ssl_wrap import SSLConnection, SSLContext, SSLCert
