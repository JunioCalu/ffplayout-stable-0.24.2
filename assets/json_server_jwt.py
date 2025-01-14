from flask import Flask, jsonify, request
from functools import wraps
import jwt
import datetime
import argparse

app = Flask(__name__)

# Configurações de autenticação
USERNAME = "admin"
PASSWORD = "admin"
SECRET_KEY = "your_secret_key"

# JSON de resposta simulada
media_data = {
    "elapsed": 52025.24,
    "index": 0,
    "ingest": False,
    "media": {
        "category": "",
        "duration": 0.0,
        "in": 0.0,
        "out": 0.0,
        "source": ""
    },
    "mode": "playlist",
    "shift": 0.0
}

# Middleware de autenticação JWT
def authenticate_jwt(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth = request.headers.get("Authorization")
        if app.config.get("DEBUG_MODE"):
            print(f"Content of auth header: {auth}")
        if not auth:
            return jsonify({"message": "Token JWT é necessário no cabeçalho 'Authorization' no formato 'Bearer <TOKEN>'"}), 401
        try:
            if not auth.startswith("Bearer "):
                return jsonify({"message": "Formato de cabeçalho 'Authorization' inválido. Deve começar com 'Bearer '"}), 401
            token_provided = auth.split()[1]
            if app.config.get("DEBUG_MODE"):
                print(f"Extracted token: {token_provided}")
            jwt.decode(token_provided, SECRET_KEY, algorithms=["HS256"])
        except IndexError:
            return jsonify({"message": "Token JWT ausente no cabeçalho 'Authorization'"}), 401
        except jwt.ExpiredSignatureError:
            return jsonify({"message": "Token expirado"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"message": "Token inválido"}), 401
        return f(*args, **kwargs)
    return decorated_function

# Rota de login para gerar o token JWT
@app.route("/auth/login/", methods=["POST"])
def login():
    auth = request.json
    if not auth or auth.get("username") != USERNAME or auth.get("password") != PASSWORD:
        return jsonify({"message": "Credenciais inválidas"}), 401

    token_data = {
        "id": 1,
        "channels": [1, 2, 3, 4],
        "username": USERNAME,
        "role": "GlobalAdmin",
        "exp": int((datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)).timestamp())
    }
    token = jwt.encode(token_data, SECRET_KEY, algorithm="HS256")

    response = {
        "message": "login correct!",
        "user": {
            "id": 1,
            "mail": "contact@example.com",
            "username": USERNAME,
            "role_id": 1,
            "channel_ids": [1, 2, 3, 4],
            "token": token
        }
    }
    return jsonify(response), 200

# Rota para retornar JSON
@app.route("/api/control/<int:channel_id>/media/current", methods=["GET"])
@authenticate_jwt
def get_current_media(channel_id):
    return jsonify(media_data), 200

# Rota para alterar o valor de "ingest"
def create_set_ingest_route(channel_id):
@app.route(f"/api/control/<int:channel_id>/media/ingest", methods=["POST"])
@authenticate_jwt
def set_ingest(channel_id):
    data = request.json
    print("Json ingest data:", data)
    if "ingest" not in data:
        return jsonify({"message": "O campo 'ingest' é obrigatório."}), 400
    if not isinstance(data["ingest"], bool):
        return jsonify({"message": "O campo 'ingest' deve ser do tipo booleano."}), 400

    media_data["ingest"] = data["ingest"]
    return jsonify({"message": "O valor de 'ingest' foi atualizado com sucesso.", "ingest": media_data["ingest"]}), 200

@app.route("/error", methods=["GET"])
def trigger_error():
    raise Exception("Erro de teste para acionar o debugger!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Flask JSON server with optional debug mode and configurable channel ID.")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--channel-id", type=int, default=1, help="Set the default channel ID (default: 1)")
    args = parser.parse_args()

    app.config["DEBUG_MODE"] = args.debug
    channel_id = args.channel_id

    #create_get_current_media_route(channel_id)
    create_set_ingest_route(channel_id)

    app.run(host="127.0.0.1", port=8787, debug=args.debug)
