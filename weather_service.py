"""
weather_service.py — HSE PYXIS
================================
Service météo via OpenWeather API (offre gratuite : 60 appels/minute).

Sert à alimenter automatiquement les champs météo de l'étude de dispersion
(dispersion_aloha.py) : vitesse/direction du vent, température, pression,
humidité — à partir :
    - soit d'une VILLE (recherche par nom)
    - soit de coordonnées (latitude/longitude)

Dans cette version, la saisie manuelle reste possible par défaut.
Ce module est prêt à être branché quand la clé API OPENWEATHER_API_KEY
sera disponible.

Usage :
    from weather_service import (
        is_configured, get_status,
        get_weather_by_city, get_weather_by_coords,
        get_weather_or_none, WeatherServiceError,
    )

    if is_configured():
        data = get_weather_by_city("Alger")
        print(data["vitesse_vent_m_s"], data["direction_vent_deg"])
"""

import os
from pathlib import Path

import requests
from dotenv import load_dotenv

# ---- Charger .env (racine du projet) ----
_ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH)

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")

BASE_URL = "https://api.openweathermap.org/data/2.5/weather"
DEFAULT_TIMEOUT_S = 6


# ============================================================
# EXCEPTION
# ============================================================
class WeatherServiceError(Exception):
    """Erreur du service météo (réseau, API, réponse invalide)."""
    pass


# ============================================================
# CONFIGURATION
# ============================================================
def is_configured() -> bool:
    """Vérifie que la clé API OpenWeather est disponible (.env ou st.secrets)."""
    if OPENWEATHER_API_KEY:
        return True
    try:
        import streamlit as st
        return bool(st.secrets.get("OPENWEATHER_API_KEY"))
    except Exception:
        return False


def _resolve_api_key() -> str:
    """Retourne la clé API (env prioritaire, puis st.secrets)."""
    if OPENWEATHER_API_KEY:
        return OPENWEATHER_API_KEY
    try:
        import streamlit as st
        return st.secrets["OPENWEATHER_API_KEY"]
    except Exception:
        raise WeatherServiceError(
            "❌ OPENWEATHER_API_KEY introuvable. "
            "Ajoutez-la dans .env (OPENWEATHER_API_KEY=...) "
            "ou dans .streamlit/secrets.toml"
        )


def get_status() -> dict:
    """État BRUT (non traduit) de la configuration météo."""
    configured = is_configured()
    return {
        "configured": configured,
        "provider": "OpenWeather",
        "env_path": str(_ENV_PATH),
        "env_exists": _ENV_PATH.exists(),
    }


# ============================================================
# EXTRACTION COMMUNE (réutilisée par city et coords)
# ============================================================
def _parse_openweather_response(raw: dict, fallback_city: str = "—") -> dict:
    """
    Transforme la réponse brute OpenWeather en dict HSE PYXIS.

    Clés de sortie :
        - vitesse_vent_m_s : float (m/s)
        - direction_vent_deg : float (0-360)
        - temperature_c : float
        - pression_hpa : float
        - humidite_pct : float
        - source : "openweather"
        - ville_detectee : str
        - pays : str
        - latitude, longitude : float
        - description : str (ex: "ciel dégagé")
    """
    main = raw.get("main", {})
    wind = raw.get("wind", {})
    weather_list = raw.get("weather", [{}])
    weather = weather_list[0] if weather_list else {}
    sys = raw.get("sys", {})
    coord = raw.get("coord", {})

    return {
        "vitesse_vent_m_s": float(wind.get("speed", 0.0)),
        "direction_vent_deg": float(wind.get("deg", 0.0)),
        "temperature_c": float(main.get("temp", 0.0)),
        "pression_hpa": float(main.get("pressure", 1013)),
        "humidite_pct": float(main.get("humidity", 0.0)),
        "source": "openweather",
        "ville_detectee": str(raw.get("name", fallback_city)),
        "pays": str(sys.get("country", "")),
        "latitude": float(coord.get("lat", 0.0)),
        "longitude": float(coord.get("lon", 0.0)),
        "description": str(weather.get("description", "")).capitalize(),
        "icon": str(weather.get("icon", "")),
    }


# ============================================================
# MÉTÉO PAR VILLE
# ============================================================
def get_weather_by_city(
    city: str,
    api_key: str | None = None,
    timeout: int = DEFAULT_TIMEOUT_S,
) -> dict:
    """
    Récupère la météo actuelle d'une ville.

    Args:
        city : nom de la ville (ex: "Alger", "Oran,DZ", "Hassi Messaoud")
        api_key : clé API (si None, utilise .env ou st.secrets)
        timeout : timeout en secondes

    Returns:
        dict (voir _parse_openweather_response)

    Raises:
        WeatherServiceError : si erreur réseau, ville introuvable, ou clé invalide
    """
    if not city or len(city.strip()) < 2:
        raise WeatherServiceError("Nom de ville trop court.")

    if api_key is None:
        api_key = _resolve_api_key()

    params = {
        "q": city.strip(),
        "appid": api_key,
        "units": "metric",
        "lang": "fr",
    }

    try:
        resp = requests.get(BASE_URL, params=params, timeout=timeout)
        resp.raise_for_status()
        raw = resp.json()
    except requests.HTTPError as e:
        status = e.response.status_code if e.response else "?"
        if status == 404:
            raise WeatherServiceError(f"Ville introuvable : « {city} »") from e
        if status == 401:
            raise WeatherServiceError(
                "Clé OpenWeather invalide (401). Vérifiez OPENWEATHER_API_KEY."
            ) from e
        raise WeatherServiceError(f"Erreur OpenWeather ({status}) : {e}") from e
    except requests.RequestException as e:
        raise WeatherServiceError(f"Échec réseau : {e}") from e

    try:
        return _parse_openweather_response(raw, fallback_city=city)
    except (KeyError, TypeError, ValueError) as e:
        raise WeatherServiceError(f"Réponse OpenWeather inattendue : {e}") from e


# ============================================================
# MÉTÉO PAR COORDONNÉES
# ============================================================
def get_weather_by_coords(
    latitude: float,
    longitude: float,
    api_key: str | None = None,
    timeout: int = DEFAULT_TIMEOUT_S,
) -> dict:
    """
    Récupère la météo actuelle aux coordonnées données.

    Mêmes conventions que get_weather_by_city.
    """
    if api_key is None:
        api_key = _resolve_api_key()

    params = {
        "lat": latitude,
        "lon": longitude,
        "appid": api_key,
        "units": "metric",
        "lang": "fr",
    }

    try:
        resp = requests.get(BASE_URL, params=params, timeout=timeout)
        resp.raise_for_status()
        raw = resp.json()
    except requests.HTTPError as e:
        status = e.response.status_code if e.response else "?"
        if status == 401:
            raise WeatherServiceError(
                "Clé OpenWeather invalide (401). Vérifiez OPENWEATHER_API_KEY."
            ) from e
        raise WeatherServiceError(f"Erreur OpenWeather ({status}) : {e}") from e
    except requests.RequestException as e:
        raise WeatherServiceError(f"Échec réseau : {e}") from e

    try:
        return _parse_openweather_response(raw, fallback_city="—")
    except (KeyError, TypeError, ValueError) as e:
        raise WeatherServiceError(f"Réponse OpenWeather inattendue : {e}") from e


# ============================================================
# VARIANTE SILENCIEUSE
# ============================================================
def get_weather_or_none(
    *,
    city: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    api_key: str | None = None,
) -> dict | None:
    """
    Variante silencieuse : retourne None au lieu de lever une exception.

    Utilisation :
        data = get_weather_or_none(city="Alger")
        if data:
            print(data["vitesse_vent_m_s"])

    Accepte soit `city`, soit `lat`+`lon`.
    """
    try:
        if city:
            return get_weather_by_city(city, api_key=api_key)
        if lat is not None and lon is not None:
            return get_weather_by_coords(lat, lon, api_key=api_key)
        return None
    except WeatherServiceError:
        return None


# ============================================================
# TEST RAPIDE
# ============================================================
if __name__ == "__main__":
    print("Test du service météo (OpenWeather)...")
    print("Configuré :", is_configured())
    print("Status :", get_status())

    if not is_configured():
        print("\n⚠️ Ajoutez OPENWEATHER_API_KEY dans .env")
    else:
        for city in ["Alger", "Oran", "Hassi Messaoud"]:
            data = get_weather_or_none(city=city)
            if data:
                print(f"\n📍 {city} → {data['ville_detectee']} ({data['pays']})")
                print(f"   Vent : {data['vitesse_vent_m_s']:.1f} m/s @ {data['direction_vent_deg']:.0f}°")
                print(f"   Température : {data['temperature_c']:.1f}°C")
                print(f"   Humidité : {data['humidite_pct']:.0f}%")
                print(f"   Description : {data['description']}")
            else:
                print(f"\n📍 {city} : ❌ Aucune donnée")