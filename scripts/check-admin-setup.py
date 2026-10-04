"""Offline provisioning checks; only fixed public RFC test material is used."""
import importlib
import io
from unittest.mock import patch

setup = importlib.import_module('scripts.setup-admin-2fa')
secret = b'12345678901234567890'  # Public RFC6238 test secret, never an operational key.
assert setup.matches(secret, '287082', 59)
assert not setup.matches(secret, '287082', 120)
assert not setup.matches(secret, '１２３４５６', 59)

class Terminal(io.StringIO):
    def isatty(self):
        return True

with patch.object(setup.sys, 'stdin', io.StringIO()), patch.object(setup.sys, 'stdout', io.StringIO()), \
     patch.object(setup.sys, 'stderr', io.StringIO()), patch.object(setup.secrets, 'token_bytes') as generate:
    assert setup.main(['--create']) == 2
    generate.assert_not_called()

for otp, status in [('287082', 0), ('000000', 1)]:
    output = Terminal()
    with patch.object(setup.sys, 'stdin', Terminal()), patch.object(setup.sys, 'stdout', output), \
         patch.object(setup.secrets, 'token_bytes', return_value=secret), \
         patch.object(setup.getpass, 'getpass', return_value=otp), patch.object(setup.time, 'time', return_value=59):
        assert setup.main(['--create']) == status
    assert ('ADMIN_REQUIRE_2FA = on' in output.getvalue()) == (status == 0)
print('PASS: noninteractive secret generation refused, authenticator validation, invalid codes block activation instructions')
