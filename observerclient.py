import socket
import json
import uuid
import argparse
import time
import logging


# configuracion del logger con -v sino entra en info
def configurar_logger(verbose):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s - %(levelname)s - %(message)s") 


# guardar notificacion en archivo json
def guardar_output(data, path):
    try:
        with open(path, "a") as file: #abre el archivo con append
            json.dump(data, file, indent=4)
            file.write("\n")
        logging.info(f"Notificacion guardada en {path}")
    except Exception as e:
        logging.error(f"Error al guardar la notificacion: {e}")


# cliente observer
def iniciar_observer(host, port, output_file):
    while True:
        try:
            logging.info(f"Conectando al servidor {host}:{port}...")
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((host, port))
                #crear peticion
                request = {"UUID": str(uuid.getnode()), "ACTION": "subscribe"}
                s.sendall(json.dumps(request).encode("utf-8"))
                print(" Suscripto al servidor, esperando notificaciones...\n")

                while True:
                    #lee hasta 4096 bytes del socket
                    data = s.recv(4096)
                    if not data:
                        raise ConnectionError("Conexion interrumpida")
                    
                    message = json.loads(data.decode("utf-8"))
                    print("Notificación recibida:")
                    print(json.dumps(message, indent=4))

                    # Guardar si se especificó archivo
                    if output_file:
                        guardar_output(message, output_file)
        #requerimiento de 30 segundos
        except Exception as e:
            logging.error(f"Error en la conexion: {e}")
            print(" Reintentando en 30 segundos...")
            time.sleep(30)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cliente Observer para patrón Observer")
    parser.add_argument("-s", "--server", default="localhost", help="Host del servidor") #server
    parser.add_argument("-p", "--port", type=int, default=8080, help="Puerto del servidor") #puerto
    parser.add_argument("-o", "--output", required=False, help="Archivo para guardar actualizaciones") #salida
    parser.add_argument("-v", "--verbose", action="store_true", help="Modo verbose") #verbose

    args = parser.parse_args()
    configurar_logger(args.verbose)

    iniciar_observer(args.server, args.port, args.output)
