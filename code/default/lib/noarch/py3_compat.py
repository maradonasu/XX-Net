import collections
import collections.abc
import threading


def _ensure_collections_aliases():
    alias_names = (
        "Callable",
        "Container",
        "Iterable",
        "ItemsView",
        "KeysView",
        "Mapping",
        "MutableMapping",
        "MutableSequence",
        "MutableSet",
        "Sequence",
        "Set",
        "Sized",
        "ValuesView",
    )
    for name in alias_names:
        if not hasattr(collections, name) and hasattr(collections.abc, name):
            setattr(collections, name, getattr(collections.abc, name))


def _ensure_threading_aliases():
    if not hasattr(threading.Thread, "isAlive"):
        threading.Thread.isAlive = threading.Thread.is_alive

    if not hasattr(threading, "currentThread"):
        threading.currentThread = threading.current_thread

    if not hasattr(threading, "activeCount"):
        threading.activeCount = threading.active_count


_ensure_collections_aliases()
_ensure_threading_aliases()
