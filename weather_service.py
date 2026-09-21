"""
weather_service.py
===================
Intégration OpenWeather API (offre gratuite, jusqu'à 60 appels/minute, cf. architecture
du projet). Sert à alimenter automatiquement les champs météo de l'étude de dispersion
(dispersion_aloha.py) : vitesse/direction du vent, température, pression, humidité --
à partir de la position (latitude/longitude) saisie par l'inspecteur.

Dans cette version, la saisie reste manuelle par défaut (cf. document de cadrage : "à
faire en étape ultérieure"). Ce module est prêt à être branché quand la clé API
OPENWEATHER_API_KEY sera disponible.

Utilisation :
    from weather_service import get_current_weather
    meteo = get_current_weather(lat=36.75, lon=3.06, api_key="...")
"""

import requests

BASE_URL = "https://api.openweathermap.org/data/2.5/weather"


class WeatherServiceError(Exception):
    pass


def get_current_weather(lat: float, lon: float, api_key: str, timeout: int = 5) -> dict:
    """Interroge OpenWeather pour la météo actuelle à une position donnée.

    Retourne un dict directement compatible avec les paramètres attendus par
    dispersion_aloha.evaluer_dispersion (vitesse_vent_m_s, direction_vent_deg,
    temperature_c, pression_hpa, humidite_pct).

    Lève WeatherServiceError en cas d'échec réseau ou de réponse invalide -- l'appelant
    (interface Streamlit) doit alors proposer à l'inspecteur de saisir la météo manuellement
    (c'est le comportement par défaut de ce prototype).
    """
    params = {"lat": lat, "lon": lon, "appid": api_key, "units": "metric"}
    try:
        resp = requests.get(BASE_URL, params=params, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        raise WeatherServiceError(f"Échec de l'appel OpenWeather : {e}") from e

    try:
        return {
            "vitesse_vent_m_s": float(data["wind"]["speed"]),
            "direction_vent_deg": float(data["wind"].get("deg", 0)),
            "temperature_c": float(data["main"]["temp"]),
            "pression_hpa": float(data["main"]["pressure"]),
            "humidite_pct": float(data["main"]["humidity"]),
            "source": "openweather",
            "ville_detectee": data.get("name"),
        }
    except (KeyError, TypeError) as e:
        raise WeatherServiceError(f"Réponse OpenWeather inattendue : {data}") from e


def get_weather_or_none(lat: float, lon: float, api_key: str) -> dict | None:
    """Variante silencieuse : retourne None au lieu de lever une exception, pratique pour
    l'UI (bascule automatique vers la saisie manuelle si l'appel échoue).
    """
    try:
        return get_current_weather(lat, lon, api_key)
    except WeatherServiceError:
        return None


if __name__ == "__main__":
    import os
    key = os.environ.get("OPENWEATHER_API_KEY")
    if not key:
        print("Définir la variable d'environnement OPENWEATHER_API_KEY pour tester.")
    else:
        print(get_current_weather(lat=36.75, lon=3.06, api_key=key))
