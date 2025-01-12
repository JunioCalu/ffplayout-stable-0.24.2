import os
import json
import time
import logging
import requests
import jwt
from typing import Optional
from pathlib import Path

class TokenManager:
    def __init__(
        self,
        api_url: str,
        username: str,
        password: str,
        channel_id: int,
        storage_path: str = "~/.tokens"
    ):
        self.api_url = api_url
        self.username = username
        self.password = password
        self.channel_id = channel_id
        self.storage_path = os.path.expanduser(storage_path)
        self.token: Optional[str] = None
        self.expiry: Optional[float] = None
        self._ensure_storage_directory()
        self._load_token()

    def _ensure_storage_directory(self) -> None:
        """Creates the storage directory if it does not exist."""
        os.makedirs(self.storage_path, mode=0o700, exist_ok=True)

    def _get_storage_file(self) -> str:
        """Returns the path to the token storage file."""
        return os.path.join(self.storage_path, f"token_channel_{self.channel_id}.json")

    def _decode_token_expiry(self, token: str) -> Optional[float]:
        """Decodes the JWT token to extract the expiration date."""
        try:
            decoded = jwt.decode(token, algorithms=["HS256"], options={"verify_signature": False})
            return decoded.get("exp")
        except jwt.PyJWTError as e:
            logging.error(f"Error decoding token: {e}")
            return None

    def _save_token(self, token: str, expiry: float) -> None:
        """Saves the token and its expiration time to disk."""
        data = {
            "token": token,
            "expiry": expiry
        }
        with open(self._get_storage_file(), 'w') as f:
            json.dump(data, f)
        os.chmod(self._get_storage_file(), 0o600)

    def _load_token(self) -> None:
        """Loads the token from disk and verifies its validity."""
        try:
            if not os.path.exists(self._get_storage_file()):
                return

            with open(self._get_storage_file(), 'r') as f:
                data = json.load(f)

            self.token = data.get("token")
            self.expiry = data.get("expiry")

            # Check if the token is expired (with a 5-minute margin)
            if self.expiry is None or time.time() + 300 >= self.expiry:
                self.token = None
                self.expiry = None

        except Exception as e:
            logging.error(f"Error loading token: {e}")
            self.token = None
            self.expiry = None

    def _request_new_token(self) -> None:
        """Requests a new token from the API and updates memory and disk."""
        url = f"{self.api_url}/auth/login/"
        payload = {
            "username": self.username,
            "password": self.password
        }
        headers = {
            "Content-Type": "application/json"
        }

        try:
            logging.debug(f"Sending authentication request to {url}")
            response = requests.post(url, json=payload, headers=headers)

            if response.status_code == 200:
                data = response.json()
                if "token" in data["user"]:
                    self.token = data["user"]["token"]
                    self.expiry = self._decode_token_expiry(self.token)
                    if self.expiry is None:
                        raise ValueError("Unable to decode token expiry.")
                    self._save_token(self.token, self.expiry)
                else:
                    raise ValueError("Token not found in the response")
            else:
                raise ValueError(f"Failed to login. Status code: {response.status_code}")
        except Exception as e:
            raise Exception(f"Error during authentication: {e}")

    def get_valid_token(self) -> str:
        """Returns a valid token, requesting a new one if the current token is expired."""
        if self.token is None or self.expiry is None or time.time() >= self.expiry:
            logging.debug("Token is expired or not available, requesting a new one.")
            self._request_new_token()
        return self.token

def get_current_media(api_url, token, channel_id):
    """Retrieve the current media information from the API."""
    url = f"{api_url}/api/control/{channel_id}/media/current"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

    try:
        logging.debug(f"Fetching current media information from {url}")
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            print("Current media information:", response.json())
        else:
            print(f"Failed to retrieve current media. Status code: {response.status_code}, Response: {response.text}")
            sys.exit(1)
    except requests.RequestException as e:
        print(f"Network error while retrieving current media: {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"Error parsing media response: {e}")
        sys.exit(1)

# Example usage
def main():
    # Logging configuration
    logging.basicConfig(level=logging.DEBUG,
                       format='%(asctime)s - %(levelname)s - %(message)s')

    # API parameters
    api_url = "http://127.0.0.1:8787"
    username = "admin"
    password = "senha"
    channel_id = 1

    # Initialize the token manager
    token_manager = TokenManager(api_url, username, password, channel_id)

    try:
        # Get a valid token
        token = token_manager.get_valid_token()

        # Retrieve current media information
        get_current_media(api_url, token, channel_id)

    except Exception as e:
        logging.error(f"Error: {e}")

if __name__ == "__main__":
    main()
