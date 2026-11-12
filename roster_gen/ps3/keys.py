"""PS3 save crypto constants and key derivation."""
from binascii import unhexlify
import re

SYSCON_MANAGER_KEY = unhexlify("D413B89663E1FE9F75143D3BB4565274")  # SYSCON_MANAGER_KEY
KEYGEN_KEY = unhexlify("6B1ACEA246B745FD8F93763B920594CD53483B82")
NCAA14_SECURE_FILE_ID_HEX = "0F" * 16


def make_secure_file_id(hexid: str) -> bytes:
    """Insert 0b,0f,0e,0a at the positions defined by the PARAM.PFD spec."""
    arr = re.findall("..", hexid)
    arr.insert(5, "0a")
    arr.insert(3, "0e")
    arr.insert(1, "0f")
    arr.insert(1, "0b")
    return unhexlify("".join(arr))


NCAA14_SFI = make_secure_file_id(NCAA14_SECURE_FILE_ID_HEX)