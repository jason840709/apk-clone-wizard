# SPDX-License-Identifier: MIT
"""Read-only Darwin statfs check before compiler module lock creation."""
import ctypes, os, sys
from pathlib import Path
class StatFS64(ctypes.Structure):
    _fields_=[("bsize",ctypes.c_uint32),("iosize",ctypes.c_int32),
        ("blocks",ctypes.c_uint64),("bfree",ctypes.c_uint64),("bavail",ctypes.c_uint64),
        ("files",ctypes.c_uint64),("ffree",ctypes.c_uint64),("fsid",ctypes.c_int32*2),
        ("owner",ctypes.c_uint32),("type",ctypes.c_uint32),("flags",ctypes.c_uint32),
        ("subtype",ctypes.c_uint32),("fstype",ctypes.c_char*16),("mount",ctypes.c_char*1024),
        ("source",ctypes.c_char*1024),("flags_ext",ctypes.c_uint32),("reserved",ctypes.c_uint32*7)]
def filesystem(path):
    if sys.platform!="darwin":raise OSError("This native launcher requires macOS")
    path=Path(path).expanduser().resolve()
    while not path.exists():
        if path==path.parent:raise OSError("No existing parent for build directory")
        path=path.parent
    libc=ctypes.CDLL(None,use_errno=True);func=libc.statfs64
    func.argtypes=[ctypes.c_char_p,ctypes.POINTER(StatFS64)];func.restype=ctypes.c_int
    value=StatFS64()
    if func(os.fsencode(path),ctypes.byref(value))!=0:raise OSError(ctypes.get_errno(),"Unable to inspect filesystem")
    name=value.fstype.decode("ascii")
    if not name:raise OSError("Unknown filesystem")
    return name.lower()
