import requests
import sys
import argparse
import jwt
import json
import time
import logging

def get_auth_token(api_url, username, password):
    """Obtain authentication token from the API."""
    url = f"{api_url}/auth/login/"
    payload = {
        "username": username,
        "password": password
    }
    headers = {
        "Content-Type": "application/json"
    }

    logging.debug(f"Sending authentication request to {url} with payload: {payload}")

    response = requests.post(url, json=payload, headers=headers)

    if response.status_code == 200:
        data = response.json()
        if "token" in data["user"]:
            logging.debug(f"Authentication successful, response received: {data}")
            logging.debug(f"Authentication successful, token received: {data['user']['token']}")
            return data["user"]["token"]
        else:
            print("Error: Token not found in the response.")
            sys.exit(1)
    else:
        print(f"Failed to login. Status code: {response.status_code}, Response: {response.text}")
        sys.exit(1)

def send_message(api_url, token, endpoint, message_payload):
    """Send a message to the API using the obtained token."""
    url = f"{api_url}{endpoint}"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

    logging.debug(f"Sending message to {url} with payload: {message_payload}")

    response = requests.post(url, json=message_payload, headers=headers)

    if response.status_code == 200:
        print("Message sent successfully:", response.json())
    else:
        print(f"Failed to send message. Status code: {response.status_code}, Response: {response.text}")
        sys.exit(1)

def get_current_media(api_url, token):
    """Retrieve the current media information from the API."""
    url = f"{api_url}/api/control/1/media/current"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

    logging.debug(f"Fetching current media information from {url}")

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        print("Current media information:", response.json())
    else:
        print(f"Failed to retrieve current media. Status code: {response.status_code}, Response: {response.text}")
        sys.exit(1)

def decode_token(token):
    """Decode a JWT token and extract expiration time."""
    try:
        decoded = jwt.decode(token, algorithms=["HS256"], options={"verify_signature": False})
        expiration = decoded.get("exp")
        print("Decoded Token Information:", decoded)
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
    parser.add_argument("--get-current-media", action="store_true", help="Retrieve current media information.")
    parser.add_argument("--send-text", metavar="TEXT", type=str, help="Send a text message to the API.")
    parser.add_argument("--text-parameters", metavar="JSON", type=str, help="JSON string of additional text parameters.")
    parser.add_argument("--decode-token-jwt", action="store_true", help="Decode the JWT token and display its information.")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode for additional logging.")
    args = parser.parse_args()

    # Configure logging
    logging_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(level=logging_level, format='%(asctime)s - %(levelname)s - %(message)s')

    api_url = "http://127.0.0.1:8787"  # Base API URL
    endpoint = "/api/control/1/text/"

    # Message payload default values
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

    # Override default payload with custom parameters if provided
    if args.text_parameters:
        try:
            custom_parameters = json.loads(args.text_parameters)
            default_message_payload.update(custom_parameters)
            logging.debug("Updated message payload: %s", default_message_payload)
        except json.JSONDecodeError:
            print("Invalid JSON string provided for --text-parameters.")
            sys.exit(1)

    # Obtain authentication token
    print("Obtaining authentication token...")
    token = get_auth_token(api_url, args.username, args.password)
    print("Token obtained successfully.")

    # Perform operations based on arguments
    if args.send_text:
        print("Sending message...")
        send_message(api_url, token, endpoint, default_message_payload)

    if args.get_current_media:
        print("Retrieving current media...")
        get_current_media(api_url, token)

    if args.decode_token_jwt:
        print("Decoding token...")
        decode_token(token)

if __name__ == "__main__":
    main()
