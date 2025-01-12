import os
import sys
import json
import time
import logging
import requests
import argparse
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
        """Creates the storage directory if it doesn't exist."""
        os.makedirs(self.storage_path, mode=0o700, exist_ok=True)

    def _get_storage_file(self) -> str:
        """Returns the path to the token storage file."""
        return os.path.join(self.storage_path, f"token_channel_{self.channel_id}.json")

    def _decode_token_expiry(self, token: str) -> Optional[float]:
        """Decodes the JWT token to extract its expiration date."""
        try:
            decoded = jwt.decode(token, algorithms=["HS256"], options={"verify_signature": False})
            return decoded.get("exp")
        except jwt.PyJWTError as e:
            logging.error(f"Error decoding token: {e}")
            return None

    def _save_token(self, token: str, expiry: float) -> None:
        """Saves the token and its expiration date to disk."""
        data = {
            "token": token,
            "expiry": expiry
        }
        with open(self._get_storage_file(), 'w') as f:
            json.dump(data, f)
        os.chmod(self._get_storage_file(), 0o600)

    def _load_token(self) -> None:
        """Loads the token from disk and checks its validity."""
        try:
            if not os.path.exists(self._get_storage_file()):
                return

            with open(self._get_storage_file(), 'r') as f:
                data = json.load(f)

            self.token = data.get("token")
            self.expiry = data.get("expiry")

            # Checks if the token is expired (adding a 5-minute buffer)
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
                        raise ValueError("Unable to decode token expiration.")
                    self._save_token(self.token, self.expiry)
                else:
                    raise ValueError("Token not found in response.")
            else:
                raise ValueError(f"Login failed. Status code: {response.status_code}")
        except Exception as e:
            raise Exception(f"Error during authentication: {e}")

    def get_valid_token(self) -> str:
        """
        Returns a valid token, requesting a new one if the current token is expired
        or doesn't exist.
        """
        if self.token is None or self.expiry is None or time.time() >= self.expiry:
            logging.debug("Token expired or not available, requesting a new token.")
            self._request_new_token()
        return self.token

def send_message(api_url, token, endpoint, message_payload):
    """Sends a message to the API using the obtained token."""
    url = f"{api_url}{endpoint}"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

    try:
        logging.debug(f"Sending message to {url} with payload: {message_payload}")
        response = requests.post(url, json=message_payload, headers=headers)

        if response.status_code == 200:
            print("Message sent successfully:", response.json())
        else:
            print(f"Failed to send message. Status code: {response.status_code}, Response: {response.text}")
            sys.exit(1)
    except requests.RequestException as e:
        print(f"Network error while sending message: {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"Error interpreting message response: {e}")
        sys.exit(1)

def get_current_media(api_url, token, channel_id):
    """Retrieves current media information from the API."""
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
        print(f"Error interpreting media response: {e}")
        sys.exit(1)

def decode_token(token):
    """Decodes a JWT token and displays its expiration time."""
    try:
        decoded = jwt.decode(token, algorithms=["HS256"], options={"verify_signature": False})
        expiration = decoded.get("exp")
        print("Decoded token information:", decoded)
        if expiration:
            human_readable_time = time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(expiration))
            print(f"Token expiration time (epoch): {expiration}")
            print(f"Token expiration time (human-readable): {human_readable_time}")
        else:
            print("No expiration information found in the token.")
    except jwt.PyJWTError as e:
        print(f"Error decoding token: {e}")

def main():
    parser = argparse.ArgumentParser(description="API Automation Script")
    parser.add_argument("--username", type=str, required=True, help="Username for authentication.")
    parser.add_argument("--password", type=str, required=True, help="Password for authentication.")
    parser.add_argument("--get-current-media", action="store_true", help="Retrieves current media information.")
    parser.add_argument("--send-text", metavar="TEXT", type=str, help="Sends a text message to the API.")
    parser.add_argument("--text-parameters", metavar="JSON", type=str, help="JSON string with additional text parameters.")
    parser.add_argument("--decode-token-jwt", action="store_true", help="Decodes the JWT token and displays its information.")
    parser.add_argument("--debug", action="store_true", help="Enables debug mode for detailed logging.")
    parser.add_argument("--api-url", type=str, default="http://127.0.0.1:8787", help="Base URL of the API. Default: http://127.0.0.1:8787.")
    parser.add_argument("--channel-id", type=int, default=1, help="Channel ID for API calls. Default: 1.")
    args = parser.parse_args()

    # Adjusts the API URL if it doesn't have the http/https scheme
    if not args.api_url.startswith(("http://", "https://")):
        args.api_url = f"http://{args.api_url}"

    # Configures the logging level
    logging_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(level=logging_level, format='%(asctime)s - %(levelname)s - %(message)s')

    api_url = args.api_url
    channel_id = args.channel_id
    endpoint = f"/api/control/{channel_id}/text/"

    # Default parameters for the message
    default_message_payload = {
        "text": args.send_text or "Default text message",
        "x": "(w-text_w)/2",
        "y": "(h-text_h)/2",
        "fontsize": "24",
        "line_spacing": "4",
        "fontcolor": "#ffffff",
        "box": "1",
        "boxcolor": "#000000",
        "boxborderw": "4",
        "alpha": "1.0"
    }

    # Updates payload if a JSON with text parameters is provided
    if args.text_parameters:
        try:
            custom_parameters = json.loads(args.text_parameters)
            default_message_payload.update(custom_parameters)
            logging.debug("Payload updated with custom parameters: %s", default_message_payload)
        except json.JSONDecodeError:
            print("Invalid JSON string provided for --text-parameters.")
            sys.exit(1)

    # Creates the token manager and obtains a valid token
    try:
        print("Obtaining authentication token...")
        manager = TokenManager(api_url, args.username, args.password, channel_id)
        token = manager.get_valid_token()
        print("Token obtained successfully.")
    except Exception as e:
        print(f"Unexpected error while obtaining token: {e}")
        sys.exit(1)

    # Executes operations based on provided arguments
    if args.send_text:
        print("Sending text message...")
        send_message(api_url, token, endpoint, default_message_payload)

    if args.get_current_media:
        print("Retrieving current media...")
        get_current_media(api_url, token, channel_id)

    if args.decode_token_jwt:
        print("Decoding JWT token...")
        decode_token(token)

if __name__ == "__main__":
    main()
