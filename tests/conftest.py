"""Pytest bootstrap for Direct Mode testing.

Two gltest behaviours are normalised here so the suite runs identically on
Linux, macOS, and Windows:

1. Transaction timestamps. Contracts read `gl.message_raw["datetime"]` but
   the VM context only refreshes the built-in fields. After each refresh we
   additionally mirror the VM's current datetime into `gl.message_raw`, so
   `vm.warp(...)` is observable from contract code.

2. Loader file handling on Windows. The gltest loader injects the GenLayer
   message by dup2'ing a temporary file over stdin and unlinking it at once.
   Windows refuses to unlink an open stdin file, so unlinks on the live
   stdin descriptor are deferred until stdin has been restored.
"""

import os
import sys


def pytest_configure():
    from gltest.direct.vm import VMContext

    original_refresh = VMContext._refresh_gl_message

    def refresh_and_mirror_datetime(vm):
        original_refresh(vm)
        gl_module = sys.modules.get("genlayer.gl")
        raw_message = getattr(gl_module, "message_raw", None) if gl_module else None
        if isinstance(raw_message, dict):
            raw_message["datetime"] = vm._datetime

    VMContext._refresh_gl_message = refresh_and_mirror_datetime

    if os.name != "nt":
        return

    from gltest.direct import loader

    original_loader = loader.load_contract_class

    def windows_safe_loader(contract_path, vm, sdk_version=None):
        deferred = []
        real_unlink = os.unlink

        def defer_open_stdin_unlink(path, *args, **kwargs):
            try:
                return real_unlink(path, *args, **kwargs)
            except PermissionError as error:
                if getattr(error, "winerror", None) != 32:
                    raise
                deferred.append(path)

        os.unlink = defer_open_stdin_unlink
        try:
            return original_loader(contract_path, vm, sdk_version)
        finally:
            os.unlink = real_unlink
            stdin_backup = getattr(vm, "_original_stdin_fd", None)
            if stdin_backup is not None:
                os.dup2(stdin_backup, 0)
                os.close(stdin_backup)
                vm._original_stdin_fd = None
            for path in deferred:
                real_unlink(path)

    loader.load_contract_class = windows_safe_loader
