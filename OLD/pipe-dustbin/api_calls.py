import requests, os, json
from os.path import join, dirname

class API_calls:

    def __init__(self):         
        self.api = "https://api.photonranch.org/api"

    def base_url(self):
        return "https://api.photonranch.org/api"
        #return "http://localhost:5000"
        
    def authenticated_request(self, method: str, uri: str, payload: dict = None) -> str:

        # Populate the request parameters. Include data only if it was sent.
        request_kwargs = { 
            "method": method,
            "url": f"{self.base_url()}/{uri}",
        }
        if payload is not None: 
            request_kwargs["data"] = json.dumps(payload)

        response = requests.request(**request_kwargs)
        return response.json()


