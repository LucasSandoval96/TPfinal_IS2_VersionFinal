import socket
import threading
import json
import boto3
import uuid
import argparse
import logging
from datetime import datetime
from decimal import Decimal


# configuracion del logger
def configurar_logger(verbose):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s - %(levelname)s - %(message)s")

#  conexion a la DB (singleton)
class DynamoSingleton:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    logging.debug("Creando instancia singleton de DB")
                    cls._instance = super().__new__(cls)
                    cls._instance.dynamodb = boto3.resource("dynamodb")
                    cls._instance.data_table = cls._instance.dynamodb.Table("CorporateData")
                    cls._instance.log_table = cls._instance.dynamodb.Table("CorporateLog")
        return cls._instance

# clase para gestionar los clientes suscriptos
class ObserverManager:
    def __init__(self):
        self.subscribers = {}

    # guarda los clientes que se suscriben
    def subscribe(self, uuid_client, conn):
        self.subscribers[uuid_client] = conn
        logging.info(f"Cliente {uuid_client} suscripto correctamente")

    # registro de cliente con uuid y conexion tcp
    def notify_all(self, message):
        dead = []
        for uuid_client, conn in list(self.subscribers.items()):
            try:
                conn.sendall(json.dumps(message, default=str).encode("utf-8"))
            except Exception as e:
                logging.warning(f"No se pudo notificar al cliente {uuid_client}: {e}")
                dead.append(uuid_client)
        for d in dead:
            del self.subscribers[d]

class CustomException(Exception):
    def init(self, message):
        self.message = message
# ProxyServer
class ProxyServer:
    def __init__(self, host="localhost", port=8080): 
        self.host = host
        self.port = port
        self.db = DynamoSingleton()
        self.observer = ObserverManager()
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            logging.info(f"Servidor Proxy escuchando en {self.host}:{self.port}")
        except Exception:
            logging.error("Error: ya existe una instancia del servidor en el puerto.")
            raise CustomException("Error: ya existe una instancia del servidor en el puerto.")

    # guardar en la tabla CorporateLog la accion ejecutada por un cliente

    def log_action(self, uuid_client, action, extra=""):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        record = {
            "id": str(uuid.uuid4()),
            "CPUid": str(uuid_client),
            "sessionid": str(uuid.uuid4()),
            "timestamp": now,
            "action": action,
            "extra": extra
        }
        self.db.log_table.put_item(Item=record)
        return record["id"]

    
    # def para manejar los clientes segun la accion
    def handle_client(self, conn, addr):
        action = None   #modificado para el test
        try:
            data = conn.recv(4096).decode("utf-8")
            if not data:
                conn.close()
                return

            request = json.loads(data)
            action = request.get("ACTION")
            uuid_client = request.get("UUID", "desconocido")

            logging.debug(f"Solicitud recibida de {uuid_client}: {action}")

            if not action:
                conn.sendall(b'{"Error":"Falta campo ACTION"}')
                return
            
            # suscribe para recibir notificaciones cuando se actualicen datos
            if action == "subscribe":
                self.observer.subscribe(uuid_client, conn)
                self.log_action(uuid_client, "subscribe")
                return  # mantiene la conexión abierta

            # get busca en la DB por id y lo devuelve al cliente
            if action == "get":
                item_id = request.get("ID")
                if not item_id:
                    conn.sendall(json.dumps({"Error": "Falta ID para accion get"}).encode("utf-8"))
                    return
                try:
                    response = self.db.data_table.get_item(Key={"id": item_id})
                    result = response.get("Item", {"Error": "ID no encontrado"})
                    log_id = self.log_action(uuid_client, "get", item_id)
                    result["log_id"] = log_id
                    conn.sendall(json.dumps(result, default=str).encode("utf-8"))
                except Exception as e:
                    logging.error(f"Error en acción GET: {e}")
                    conn.sendall(json.dumps({"Error": str(e)}).encode("utf-8"))

            # list devuelve todos los registros de la tabla corporatedata
            elif action == "list":
                try:
                    response = self.db.data_table.scan()
                    items = response.get("Items", [])
                    log_id = self.log_action(uuid_client, "list")
                    items[0]["log_id"] = log_id
                    conn.sendall(json.dumps(items, default=str).encode("utf-8"))
                except Exception as e:
                    logging.error(f"Error en la accion LIST: {e}")
                    conn.sendall(json.dumps({"Error": str(e)}).encode("utf-8"))

            # set guardar o actualizar 
            elif action == "set":
                item = request.get("DATA")
                if not item:
                    conn.sendall(b'{"Error":"Falta campo DATA"}')
                    return
                try:
                    # convertir a Decimal sólo para DynamoDB
                    for key, value in item.items():
                        if isinstance(value, (int, float)):
                            item[key] = Decimal(str(value))
                    self.db.data_table.put_item(Item=item)
                    log_id = self.log_action(uuid_client, "set", item.get("id", ""))
                    item["log_id"] = log_id
                    conn.sendall(json.dumps(item, default=str).encode("utf-8"))
                    self.observer.notify_all(item)
                except Exception as e:
                    logging.error(f"Error en accion SET: {e}")
                    conn.sendall(json.dumps({"Error": str(e)}).encode("utf-8"))

            elif action == "get_log":
                item_id = request.get("ID")
                if not item_id:
                    conn.sendall(json.dumps({"Error": "Falta ID para accion get"}).encode("utf-8"))
                    return
                try:
                    response = self.db.log_table.get_item(Key={"id": item_id})
                    result = response.get("Item", {"Error": "ID no encontrado"})
                    self.log_action(uuid_client, "get", item_id)
                    conn.sendall(json.dumps(result, default=str).encode("utf-8"))
                except Exception as e:
                    logging.error(f"Error en acción GET: {e}")
                    conn.sendall(json.dumps({"Error": str(e)}).encode("utf-8"))
            else:
                conn.sendall(b'{"Error":"Accion no reconocida"}')

        except Exception as e:
            logging.error(f"Error procesando solicitud: {e}")
            conn.sendall(json.dumps({"Error": str(e)}).encode("utf-8"))
        #cierra la conexion si el cliente no esta suscripto
        finally:
            
            if action != "subscribe":
                conn.close()

    
    # Iniciar servidor y crea un hilo por cliente
    def start(self):
        logging.info("Servidor inicializado, esperando conexiones...")
        while True:
            conn, addr = self.server_socket.accept()
            threading.Thread(target=self.handle_client, args=(conn, addr), daemon=True).start()
    

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Servidor Proxy-Singleton-Observer")
    parser.add_argument("-p", "--port", type=int, default=8080, help="Puerto de escucha")
    parser.add_argument("-v", "--verbose", action="store_true", help="Modo verbose")

    args = parser.parse_args()
    configurar_logger(args.verbose)

    server = ProxyServer(port=args.port)
    server.start()
