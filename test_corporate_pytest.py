import pytest
import socket
import json
import threading
import time
import logging
from singletonproxyobservertpfi import ProxyServer, configurar_logger

# ---------- CONFIGURACIÓN ----------
HOST = "localhost"
PORT = 9090
TEST_ID = "UADER-FCyT-IS2-TEST"

# ---------- FUNCIONES AUXILIARES ----------
def send_request(request):
    """Envía una solicitud JSON al servidor y devuelve la respuesta decodificada."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((HOST, PORT))
        s.sendall(json.dumps(request).encode("utf-8"))
        data = b""
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            data += chunk
    return json.loads(data.decode("utf-8"))


def start_server():
    """Crea e inicia el servidor Proxy."""
    configurar_logger(verbose=False)
    logging.basicConfig(level=logging.CRITICAL, format="%(asctime)s - %(levelname)s - %(message)s")
    server = ProxyServer(host=HOST, port=PORT)
    server.start()


# ---------- FIXTURE PARA EL SERVIDOR ----------
@pytest.fixture(scope="session", autouse=True)
def run_server():
    """Levanta el servidor en segundo plano y espera a que el puerto esté listo."""
    thread = threading.Thread(target=start_server, daemon=True)
    thread.start()

    # Esperar hasta 10 segundos a que el servidor levante
    for _ in range(20):
        try:
            with socket.create_connection((HOST, PORT), timeout=1):
                print("✅ Servidor disponible en el puerto", PORT)
                break
        except (ConnectionRefusedError, OSError):
            time.sleep(0.5)
    else:
        pytest.fail(f"❌ El servidor no se pudo iniciar en el puerto {PORT}")

    yield


# ---------- TESTS ----------
def test_set():
    set_request = {
        "UUID": "123456",
        "ACTION": "set",
        "DATA": {
            "id": TEST_ID,
            "cp": "3260",
            "CUIT": "30-70925411-8",
            "domicilio": "25 de Mayo 385-1P",
            "idreq": "473",
            "idSeq": "1146",
            "localidad": "Concepción del Uruguay",
            "provincia": "Entre Ríos",
            "sede": "FCyT",
            "seqID": "23",
            "telefono": "03442 43-1442",
            "web": "http://www.uader.edu.ar"
        }
    }

    response_set = send_request(set_request)
    assert response_set["id"] == TEST_ID

    response_get = send_request({"ACTION": "get", "ID": TEST_ID})
    assert response_get["id"] == response_set["id"]

    response_get_log = send_request({"ID": response_set["log_id"], "ACTION": "get_log"})
    assert response_get_log["extra"] == response_set["id"]
    assert response_get_log["action"] == "set"


def test_list():
    response_list = send_request({"ACTION": "list"})
    assert any(item["id"] == TEST_ID for item in response_list)

    response_get_log = send_request({"ID": response_list[0]["log_id"], "ACTION": "get_log"})
    assert response_get_log["action"] == "list"


def test_get():
    response_get = send_request({"ACTION": "get", "ID": TEST_ID})
    assert response_get["id"] == TEST_ID

    response_get_log = send_request({"ID": response_get["log_id"], "ACTION": "get_log"})
    assert response_get_log["extra"] == TEST_ID
    assert response_get_log["action"] == "get"


def test_errorget():
    response_get = send_request({"ACTION": "get"})
    assert response_get["Error"] == "Falta ID para accion get"


def test_dobleserver():
    with pytest.raises(Exception) as excinfo:
        start_server()
    assert "ya existe una instancia del servidor" in str(excinfo.value)


def test_errorset():
    response_set = send_request({
        "UUID": "123456",
        "ACTION": "set"
    })
    assert response_set["Error"] == "Falta campo DATA"


def test_errorlist():
    response_list = send_request({"ACTION": "list"})

    if isinstance(response_list, dict) and "Error" in response_list:
        assert "Error" in response_list
    else:
        assert isinstance(response_list, list)
        assert len(response_list) > 0
        assert "id" in response_list[0]

    response_get_log = send_request({"ID": "x-noestoy_enladb-x", "ACTION": "get_log"})
    assert "Error" in response_get_log or "id" in response_get_log
