"""Calculs de distance : grand cercle, route maritime."""
from __future__ import annotations

from functools import lru_cache

import numpy as np

RAYON_TERRE_KM = 6371.0088


def haversine_km(lat1, lon1, lat2, lon2):
    """Distance orthodromique en km, vectorisée (scalaires ou tableaux numpy)."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * RAYON_TERRE_KM * np.arcsin(np.sqrt(a))


@lru_cache(maxsize=256)
def distance_mer_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance par voie maritime (réseau de routes du paquet searoute, données Eurostat/ORNL)."""
    import searoute

    route = searoute.searoute([lon1, lat1], [lon2, lat2])
    return float(route["properties"]["length"])
