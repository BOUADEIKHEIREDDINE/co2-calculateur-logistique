"""Télécharge les référentiels publics s'ils manquent (python -m co2.telechargement)."""
import io
import zipfile

import requests

from . import config as C

SOURCES = {
    "base_carbone_ademe.csv": "https://data.ademe.fr/data-fair/api/v1/datasets/base-carboner/raw",
    "airports_openflights.dat": "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airports.dat",
    "cities5000.txt": "https://download.geonames.org/export/dump/cities5000.zip",
}


def telecharger(forcer: bool = False) -> None:
    C.EXTERNAL.mkdir(parents=True, exist_ok=True)
    for nom, url in SOURCES.items():
        cible = C.EXTERNAL / nom
        if cible.exists() and not forcer:
            continue
        print(f"téléchargement de {nom}")
        contenu = requests.get(url, timeout=300).content
        if url.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(contenu)) as z:
                cible.write_bytes(z.read(nom))
        else:
            cible.write_bytes(contenu)


if __name__ == "__main__":
    telecharger()
