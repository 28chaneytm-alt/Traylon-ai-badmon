import json
import os
import re
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
NWS_HOST = "https://api.weather.gov"
USER_AGENT = os.environ.get(
    "NWS_USER_AGENT",
    "MarshallWeather/1.0 (local weather dashboard)"
)
COORDINATES = re.compile(r"-?\d{1,3}(?:\.\d+)?,-?\d{1,3}(?:\.\d+)?\Z")
GRID_FORECAST = re.compile(
    r"/gridpoints/[A-Z]{3,4}/\d+,\d+/(?:forecast|forecast/hourly)\Z"
)


def allowed_nws_path(path, query):
    if re.fullmatch(r"/points/-?\d{1,3}(?:\.\d+)?,-?\d{1,3}(?:\.\d+)?", path):
        return not query
    if path == "/alerts/active":
        params = parse_qs(query, strict_parsing=True)
        return set(params) == {"point"} and len(params["point"]) == 1 and bool(
            COORDINATES.fullmatch(params["point"][0])
        )
    return not query and bool(GRID_FORECAST.fullmatch(path))


class WeatherHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        parsed = urlsplit(self.path)
        if not parsed.path.startswith("/nws/"):
            return super().do_GET()

        api_path = parsed.path[len("/nws"):]
        try:
            if not allowed_nws_path(api_path, parsed.query):
                self.send_error(404, "Unsupported NWS endpoint")
                return
        except ValueError:
            self.send_error(400, "Invalid NWS query")
            return

        upstream_url = f"{NWS_HOST}{api_path}"
        if parsed.query:
            upstream_url = f"{upstream_url}?{parsed.query}"
        request = Request(
            upstream_url,
            headers={
                "Accept": "application/geo+json",
                "User-Agent": USER_AGENT,
            },
        )

        try:
            with urlopen(request, timeout=20) as response:
                body = response.read()
                self.send_response(response.status)
                self.send_header("Content-Type", response.headers.get("Content-Type", "application/geo+json"))
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        except HTTPError as error:
            body = error.read()
            self.send_response(error.code)
            self.send_header("Content-Type", error.headers.get("Content-Type", "application/geo+json"))
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (TimeoutError, URLError, OSError) as error:
            message = json.dumps({"error": f"NWS request failed: {error}"}).encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(message)))
            self.end_headers()
            self.wfile.write(message)


def main():
    port = int(os.environ.get("PORT", "4173"))
    server = ThreadingHTTPServer(("127.0.0.1", port), WeatherHandler)
    print(f"Weather app running at http://127.0.0.1:{port}/")
    server.serve_forever()


if __name__ == "__main__":
    main()
