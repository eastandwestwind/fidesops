from functools import reduce
from typing import List, Dict, TypeVar, Iterable, Callable, Any, Optional

T = TypeVar("T")
U = TypeVar("U")


def merge_dicts(*dicts: Dict[T, U]) -> Dict[T, U]:
    """Merge any number of dictionaries.

    Right-hand values take precedence. That is,
    merge_dicts({"A": 1, "B": 2}, {"A": 2, "C": 4})
    =>  {'A': 2, 'B': 2, 'C': 4}
    """
    if dicts:
        return reduce(lambda x, y: x | y, dicts) or {}
    return {}


def append(d: Dict[T, List[U]], key: T, val: U) -> None:
    """Append to values stored under a dictionary key.

    append({},"A",1) sets dict to {"A":[1]}
    append({"A":[1],"A",2) sets dict to {"A":[1,2]}
    """
    if val:
        if key in d:
            d[key].append(val)
        else:
            d[key] = [val]


def partition(_iterable: Iterable[T], extractor: Callable[[T], U]) -> Dict[U, List[T]]:
    """partition a collection by the output of an arbitrary extractor function"""
    out: Dict[U, List[T]] = {}
    for t in _iterable:
        append(out, extractor(t), t)
    return out


def filter_nonempty_values(d: Optional[Dict[Any, Any]]) -> Dict[Any, Any]:
    """Return the input map with empty values removed. On an input of None
    will return an empty Dict."""
    if d:
        return {e[0]: e[1] for e in d.items() if e[1]}
    return {}
