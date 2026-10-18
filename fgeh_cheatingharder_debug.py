import datetime
import os
import sys
import traceback

try:
    import fgeh_cheatingharder_settings as settings
except Exception:
    settings = None


_LOG_PATHS = None


def _dedupe_directories(directories):
    seen = set()
    for directory in directories:
        if not directory:
            continue
        try:
            normalized = os.path.abspath(directory)
        except Exception:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        yield normalized


def _windows_documents_directory():
    try:
        import ctypes

        buffer = ctypes.create_unicode_buffer(260)
        # CSIDL_PERSONAL; this respects a redirected Documents folder.
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buffer) == 0:
            return buffer.value
    except Exception:
        return None
    return None


def _candidate_log_directories():
    candidates = []

    documents_directory = _windows_documents_directory()
    if documents_directory:
        sims_directory = os.path.join(
            documents_directory,
            "Electronic Arts",
            "The Sims 4",
        )
        candidates.extend((os.path.join(sims_directory, "Mods"), sims_directory))

    try:
        module_path = os.path.abspath(__file__)
        marker = ".ts4script"
        marker_index = module_path.lower().find(marker)
        if marker_index != -1:
            archive_path = module_path[:marker_index + len(marker)]
            candidates.append(os.path.dirname(archive_path))
        candidates.append(os.path.dirname(module_path))
    except Exception:
        pass

    try:
        for path_entry in sys.path:
            if not path_entry:
                continue
            lowered = path_entry.lower()
            if "mods" in lowered or lowered.endswith(".ts4script"):
                candidates.append(
                    os.path.dirname(path_entry)
                    if lowered.endswith(".ts4script")
                    else path_entry
                )
    except Exception:
        pass

    try:
        candidates.append(os.getcwd())
    except Exception:
        pass

    return tuple(_dedupe_directories(candidates))


def get_log_paths():
    global _LOG_PATHS
    if _LOG_PATHS is not None:
        return _LOG_PATHS
    log_name = getattr(settings, "LOG_FILE_NAME", "fgeh_cheatingharder_debug.log")
    paths = []
    for directory in _candidate_log_directories():
        try:
            if os.path.isdir(directory):
                paths.append(os.path.join(directory, log_name))
        except Exception:
            continue
    _LOG_PATHS = tuple(paths)
    return _LOG_PATHS


def log(message, *args):
    if not getattr(settings, "ENABLE_DEBUG_LOG", False):
        return
    try:
        text = message.format(*args) if args else str(message)
    except Exception:
        text = "{} args={}".format(message, args)
    line = "[{}] [FGEH_CheatingHarder] {}\n".format(
        datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        text,
    )
    paths = get_log_paths()
    for path in paths:
        try:
            with open(path, "a", encoding="utf-8") as log_file:
                log_file.write(line)
        except Exception:
            continue


def log_exception(label):
    log("{}\n{}", label, traceback.format_exc())
