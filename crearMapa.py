import os
import folium
from folium.plugins import MarkerCluster
import simplekml
import gpxpy
import gpxpy.gpx
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
import io
import base64
import argparse
import sys
import tempfile
import shutil
import datetime

# Importaciones para Google Drive - Condicionales
DRIVE_AVAILABLE = False
try:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    import pickle
    DRIVE_AVAILABLE = True
except ImportError:
    pass

def get_exif_data(image):
    """Extrae datos EXIF de una imagen"""
    exif_data = {}
    try:
        info = image._getexif()
        if info:
            for tag, value in info.items():
                decoded = TAGS.get(tag, tag)
                if decoded == "GPSInfo":
                    gps_data = {}
                    for t in value:
                        sub_decoded = GPSTAGS.get(t, t)
                        gps_data[sub_decoded] = value[t]
                    exif_data[decoded] = gps_data
                else:
                    exif_data[decoded] = value
    except Exception as e:
        print(f"Error al obtener datos EXIF: {e}")
    return exif_data

def get_decimal_coordinates(gps_info):
    """Convierte coordenadas GPS de formato EXIF a decimal"""
    if not gps_info:
        return None
    
    try:
        lat_data = gps_info.get("GPSLatitude")
        lat_ref = gps_info.get("GPSLatitudeRef", "N")
        lon_data = gps_info.get("GPSLongitude")
        lon_ref = gps_info.get("GPSLongitudeRef", "E")
        
        if not lat_data or not lon_data:
            return None
            
        lat = float(lat_data[0]) + float(lat_data[1])/60 + float(lat_data[2])/3600
        lon = float(lon_data[0]) + float(lon_data[1])/60 + float(lon_data[2])/3600
        
        if lat_ref == "S":
            lat = -lat
        if lon_ref == "W":
            lon = -lon
            
        return (lat, lon)
    except Exception as e:
        print(f"Error al convertir coordenadas: {e}")
        return None

def get_readable_exif(exif_data):
    """Extrae información EXIF útil en formato legible"""
    exif_info = {}
    
    # Función auxiliar para convertir cualquier valor a string de forma segura
    def safe_str(value):
        """Convierte cualquier valor a string de forma segura"""
        if hasattr(value, 'numerator') and hasattr(value, 'denominator'):
            # Es un IFDRational
            num = value.numerator
            den = value.denominator
            if den == 0:
                return "0"
            elif num == 0:
                return "0"
            elif den == 1:
                return str(num)
            elif num > den and den != 0:
                return f"{num/den:.2f}"
            else:
                return f"{num}/{den}"
        elif isinstance(value, tuple) and len(value) == 2:
            # Es una tupla que representa una fracción
            num, den = value
            if den == 0:
                return "0"
            elif num == 0:
                return "0"
            elif den == 1:
                return str(num)
            elif num > den and den != 0:
                return f"{num/den:.2f}"
            else:
                return f"{num}/{den}"
        else:
            # Otro tipo
            return str(value)
    
    # Fecha y hora
    if 'DateTimeOriginal' in exif_data:
        exif_info['Fecha'] = str(exif_data['DateTimeOriginal'])
    elif 'DateTime' in exif_data:
        exif_info['Fecha'] = str(exif_data['DateTime'])
    
    # Cámara y lente
    if 'Make' in exif_data:
        exif_info['Marca'] = str(exif_data['Make'])
    if 'Model' in exif_data:
        exif_info['Modelo'] = str(exif_data['Model'])
    if 'LensMake' in exif_data:
        exif_info['Marca Lente'] = str(exif_data['LensMake'])
    if 'LensModel' in exif_data:
        exif_info['Modelo Lente'] = str(exif_data['LensModel'])
        
    # Configuración de captura
    if 'ExposureTime' in exif_data:
        if hasattr(exif_data['ExposureTime'], 'numerator') and hasattr(exif_data['ExposureTime'], 'denominator'):
            num = exif_data['ExposureTime'].numerator
            den = exif_data['ExposureTime'].denominator
            if num == 1 and den > 1:
                exposure = f"1/{den}s"
            else:
                exposure = f"{safe_str(exif_data['ExposureTime'])}s"
        elif isinstance(exif_data['ExposureTime'], tuple):
            num, den = exif_data['ExposureTime']
            if num == 1 and den > 1:
                exposure = f"1/{den}s"
            else:
                exposure = f"{num}/{den}s"
        else:
            exposure = f"{exif_data['ExposureTime']}s"
        exif_info['Velocidad'] = exposure
        
    if 'FNumber' in exif_data:
        exif_info['Apertura'] = f"f/{safe_str(exif_data['FNumber'])}"
        
    if 'ISOSpeedRatings' in exif_data:
        exif_info['ISO'] = str(exif_data['ISOSpeedRatings'])
        
    if 'FocalLength' in exif_data:
        exif_info['Distancia Focal'] = f"{safe_str(exif_data['FocalLength'])}mm"
        
    # Resolución
    if 'ExifImageWidth' in exif_data and 'ExifImageHeight' in exif_data:
        exif_info['Resolución'] = f"{exif_data['ExifImageWidth']}x{exif_data['ExifImageHeight']}"
    elif 'ImageWidth' in exif_data and 'ImageLength' in exif_data:
        exif_info['Resolución'] = f"{exif_data['ImageWidth']}x{exif_data['ImageLength']}"
    
    # GPS Altitud
    if 'GPSInfo' in exif_data and 'GPSAltitude' in exif_data['GPSInfo']:
        alt_ref = exif_data['GPSInfo'].get('GPSAltitudeRef', 0)
        altitude = exif_data['GPSInfo']['GPSAltitude']
        
        # Convertir la altitud a un valor decimal
        alt_value = 0
        if hasattr(altitude, 'numerator') and hasattr(altitude, 'denominator'):
            if altitude.denominator != 0:
                alt_value = altitude.numerator / altitude.denominator
        elif isinstance(altitude, tuple) and len(altitude) == 2:
            num, den = altitude
            if den != 0:
                alt_value = num / den
        else:
            try:
                alt_value = float(altitude)
            except (ValueError, TypeError):
                alt_value = 0
                
        # Si alt_ref es 1, la altitud es negativa (bajo el nivel del mar)
        if alt_ref == 1:
            alt_value = -alt_value
            
        exif_info['Altitud'] = f"{alt_value:.1f}m"
    
    return exif_info

def get_images_from_folder(folder_path):
    """Carga imágenes desde una carpeta local"""
    images = []
    
    # Extensiones de imagen comunes
    image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.tiff', '.bmp']
    
    try:
        # Verificar que la carpeta existe
        if not os.path.isdir(folder_path):
            print(f"La carpeta {folder_path} no existe.")
            return images
        
        # Recorrer archivos en la carpeta
        for filename in os.listdir(folder_path):
            # Comprobar si es una imagen por su extensión
            if any(filename.lower().endswith(ext) for ext in image_extensions):
                try:
                    file_path = os.path.join(folder_path, filename)
                    image = Image.open(file_path)
                    images.append({
                        'name': filename,
                        'image': image,
                        'path': file_path
                    })
                    print(f"Imagen cargada: {filename}")
                except Exception as e:
                    print(f"Error al cargar {filename}: {e}")
    
    except Exception as e:
        print(f"Error al acceder a la carpeta: {e}")
    
    print(f"Se cargaron {len(images)} imágenes.")
    return images

def format_fecha_exif(fecha_exif):
    """Convierte fecha EXIF (YYYY:MM:DD HH:MM:SS) a formato dd/mm/yyyy"""
    try:
        # Ejemplo de fecha EXIF: "2023:05:15 14:30:00"
        fecha_str = fecha_exif.split()[0]  # Obtiene "2023:05:15"
        year, month, day = fecha_str.split(':')
        return f"{day}/{month}/{year}"  # Formato español
    except:
        return fecha_exif  # Si falla, devuelve el valor original

def create_folium_map(image_data_list, output_file="images_map.html", no_thumbnails=False):
    """Crea un mapa interactivo con Folium"""
    # Encontrar el punto central para el mapa
    valid_coords = [coords for _, coords, _, _ in image_data_list if coords]
    if not valid_coords:
        return None
    
    avg_lat = sum(lat for lat, _ in valid_coords) / len(valid_coords)
    avg_lon = sum(lon for _, lon in valid_coords) / len(valid_coords)
    
    # Crear mapa
    map_obj = folium.Map(location=[avg_lat, avg_lon], zoom_start=10)
    marker_cluster = MarkerCluster().add_to(map_obj)
    
    for img_name, coords, img_obj, exif_info in image_data_list:
        if coords:
            # Obtener fecha de captura o usar nombre de archivo como fallback
            fecha_raw = exif_info.get('Fecha', img_name)  # Usa 'Fecha' EXIF o el nombre si no hay fecha
            fecha = format_fecha_exif(fecha_raw)

            if no_thumbnails:
                # Modo solo chinchetas: título = fecha
                marker = folium.Marker(
                    location=coords,
                    popup=fecha,  # Solo muestra la fecha como popup
                    tooltip=fecha  # También en el tooltip
                ).add_to(marker_cluster)
            else:
                # Modo con miniaturas: título = fecha (sin otros datos)
                img_copy = img_obj.copy()
                img_copy.thumbnail((300, 300), Image.LANCZOS)
                
                buffered = io.BytesIO()
                img_copy.save(buffered, format="JPEG", quality=85)
                img_str = base64.b64encode(buffered.getvalue()).decode()
                
                # Popup con solo la miniatura y la fecha 
                html = f"""
                <div style="max-width:300px;">
                    <img src="data:image/jpeg;base64,{img_str}" style="width:100%;">
                    <p style="text-align:center; margin-top:5px;"><strong>{fecha}</strong></p>
                </div>
                """
            
                iframe = folium.IFrame(html=html, width=340, height=450 if not no_thumbnails else 150)
                popup = folium.Popup(iframe, max_width=340)
                marker = folium.Marker(
                    location=coords,
                    popup=popup,
                    tooltip=img_name
                )

            marker.add_to(marker_cluster)
    
    map_obj.save(output_file)
    print(f"Mapa HTML generado: {output_file}")
    return output_file

def create_kml(image_data_list, output_file="images_map.kml"):
    """Genera un archivo KML con las imágenes geolocalizadas"""
    kml = simplekml.Kml()
    
    for img_name, coords, img_obj, exif_info in image_data_list:
        if coords:
            # Crear punto en KML
            pnt = kml.newpoint(name=img_name, coords=[(coords[1], coords[0])])
            
            # Guardar imagen como archivo temporal
            buffered = io.BytesIO()
            img_obj.copy().thumbnail((300, 300))
            img_obj.save(buffered, format="JPEG")
            
            # Construir descripción con imagen e información EXIF
            description = f'<h3>{img_name}</h3>'
            description += f'<img src="data:image/jpeg;base64,{base64.b64encode(buffered.getvalue()).decode()}" width="300px"><br/>'
            
            # Añadir información EXIF
            description += '<table border="0" cellpadding="2" cellspacing="0">'
            description += f'<tr><td><b>Coordenadas:</b></td><td>{coords[0]:.6f}, {coords[1]:.6f}</td></tr>'
            
            for key, value in exif_info.items():
                description += f'<tr><td><b>{key}:</b></td><td>{value}</td></tr>'
                
            description += '</table>'
            
            pnt.description = description
    
    kml.save(output_file)
    print(f"Archivo KML generado: {output_file}")
    return output_file

def create_gpx(image_data_list, output_file="images_map.gpx"):
    """Genera un archivo GPX con las imágenes geolocalizadas"""
    gpx = gpxpy.gpx.GPX()
    
    for img_name, coords, _, exif_info in image_data_list:
        if coords:
            # Crear waypoint en GPX
            waypoint = gpxpy.gpx.GPXWaypoint(
                latitude=coords[0],
                longitude=coords[1],
                name=img_name
            )
            
            # Añadir información EXIF como comentario
            comment_parts = []
            for key, value in exif_info.items():
                comment_parts.append(f"{key}: {value}")
            
            if comment_parts:
                waypoint.comment = " | ".join(comment_parts)
            
            gpx.waypoints.append(waypoint)
    
    with open(output_file, 'w') as f:
        f.write(gpx.to_xml())
    
    print(f"Archivo GPX generado: {output_file}")
    return output_file

def get_drive_service():
    """Configura y devuelve el servicio de Google Drive API"""
    if not DRIVE_AVAILABLE:
        print("Error: No se pueden cargar las bibliotecas de Google Drive.")
        print("Por favor instala los paquetes necesarios con:")
        print("pip install google-api-python-client google-auth-oauthlib google-auth")
        sys.exit(1)
        
    SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
    creds = None
    
    # El archivo token.pickle almacena los tokens de acceso y actualización del usuario
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    
    # Si no hay credenciales válidas disponibles, el usuario debe iniciar sesión
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # credentials.json debe descargarse desde la consola de Google Cloud
            if not os.path.exists('credentials.json'):
                print("Error: No se encuentra el archivo credentials.json")
                print("Por favor, descargue sus credenciales OAuth desde la consola de Google Cloud")
                print("y guárdelas como 'credentials.json' en el directorio del script.")
                sys.exit(1)
                
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Guardar las credenciales para la próxima ejecución
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    
    return build('drive', 'v3', credentials=creds)

def is_image_file(filename):
    """Comprueba si un archivo es una imagen basándose en su extensión"""
    image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.tiff', '.bmp']
    return any(filename.lower().endswith(ext) for ext in image_extensions)

def get_images_from_drive(folder_id):
    """Obtiene imágenes desde una carpeta de Google Drive"""
    if not DRIVE_AVAILABLE:
        print("Error: No se pueden cargar las bibliotecas de Google Drive.")
        print("Por favor instala los paquetes necesarios con:")
        print("pip install google-api-python-client google-auth-oauthlib google-auth")
        return [], None
        
    print(f"Obteniendo imágenes de Google Drive (Carpeta ID: {folder_id})...")
    images = []
    
    try:
        # Obtener servicio de Drive
        service = get_drive_service()
        
        # Consultar archivos en la carpeta
        query = f"'{folder_id}' in parents and trashed=false"
        results = service.files().list(
            q=query,
            fields="files(id, name, mimeType)"
        ).execute()
        
        items = results.get('files', [])
        
        if not items:
            print("No se encontraron archivos en la carpeta especificada.")
            return images, None
        
        # Crear directorio temporal para descargar imágenes
        temp_dir = tempfile.mkdtemp()
        print(f"Descargando imágenes a directorio temporal: {temp_dir}")
        
        # Filtrar solo imágenes y descargarlas
        for item in items:
            file_name = item['name']
            file_id = item['id']
            
            if is_image_file(file_name):
                try:
                    # Descargar archivo
                    request = service.files().get_media(fileId=file_id)
                    file_path = os.path.join(temp_dir, file_name)
                    
                    with open(file_path, 'wb') as f:
                        downloader = MediaIoBaseDownload(f, request)
                        done = False
                        while not done:
                            status, done = downloader.next_chunk()
                            print(f"Descargando {file_name}: {int(status.progress() * 100)}%")
                    
                    # Abrir imagen con PIL
                    image = Image.open(file_path)
                    images.append({
                        'name': file_name,
                        'image': image,
                        'path': file_path
                    })
                    print(f"Imagen cargada desde Drive: {file_name}")
                except Exception as e:
                    print(f"Error al descargar o procesar {file_name}: {e}")
        
        print(f"Se cargaron {len(images)} imágenes desde Google Drive.")
        
        # Registrar el directorio temporal para limpieza al finalizar
        return images, temp_dir
        
    except Exception as e:
        print(f"Error al acceder a Google Drive: {e}")
        return images, None

def parse_arguments():
    """Procesa los argumentos de línea de comandos"""
    parser = argparse.ArgumentParser(
        description='Lee las imágenes de una carpeta y genera un mapa, mostrando una chincheta con una miniatura, en la coordenada GPS que hay en los metadatos de la imagen',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    parser.add_argument('-s', '--source', type=int, choices=[1, 2], default=1,
                        help='Origen de las imágenes: 1 para directorio local, 2 para Google Drive.')
    
    parser.add_argument('-d', '--directory', type=str, default='./imagenes',
                        help='Directorio local de imágenes (para source=1) o ID de carpeta de Google Drive (para source=2).')
    
    parser.add_argument('-n', '--name', type=str, default='images_map',
                        help='Nombre base para los archivos de mapa generados (sin extensión).')
    
    parser.add_argument('-t', '--type', type=int, choices=[1, 2, 3], default=0,
                        help='Tipo de mapa a generar: 1 para HTML, 2 para GPX, 3 para KML. Si no se especifica, genera los tres tipos.')
    
    parser.add_argument('--no-thumbnails', action='store_true',
                        help='Generar mapa HTML sin miniaturas (solo chinchetas)')
    
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Mostrar información detallada durante la ejecución')
    
    args = parser.parse_args()
    
    # Validar argumentos
    if args.source == 2 and args.directory == './imagenes':
        parser.error("Para source=2 (Google Drive), debe especificar el ID de la carpeta con -d/--directory")
    
    # Verificar disponibilidad de Google Drive si se solicita
    if args.source == 2 and not DRIVE_AVAILABLE:
        print("ADVERTENCIA: La funcionalidad de Google Drive no está disponible.")
        print("Por favor, instala las bibliotecas necesarias con:")
        print("pip install google-api-python-client google-auth-oauthlib google-auth")
        print("Continuando con la configuración por defecto (carpeta local)...")
        args.source = 1
    
    return args

def main():
    # Procesar argumentos de línea de comandos
    args = parse_arguments()
    
    # Mostrar información sobre los parámetros si verbose está activado
    if args.verbose:
        print(f"Configuración:")
        print(f"- Origen: {'Local' if args.source == 1 else 'Google Drive'}")
        print(f"- {'Directorio' if args.source == 1 else 'ID de carpeta'}: {args.directory}")
        print(f"- Nombre base: {args.name}")
        print(f"- Tipo(s) de mapa: {args.type if args.type > 0 else 'Todos'}")
        print(f"- Sin miniaturas: {'Sí' if args.no_thumbnails else 'No'}")
        print("")
    
    temp_dir = None
    try:
        # Obtener imágenes según el origen
        if args.source == 1:
            image_list = get_images_from_folder(args.directory)
        else:  # args.source == 2
            image_list, temp_dir = get_images_from_drive(args.directory)
            
        if not image_list:
            print("No se encontraron imágenes.")
            return
        
        # Extraer datos GPS y EXIF de cada imagen
        image_data_list = []
        for img_data in image_list:
            image = img_data['image']
            name = img_data['name']
            
            # Obtener todos los datos EXIF
            exif_data = get_exif_data(image)
            
            # Extraer información GPS
            gps_info = exif_data.get('GPSInfo', None)
            coords = get_decimal_coordinates(gps_info) if gps_info else None
            
            # Extraer información EXIF legible
            exif_info = get_readable_exif(exif_data)
            
            if coords:
                print(f"Coordenadas de {name}: {coords}")
                # Añadir información de metadatos
                if exif_info:
                    print("Información EXIF encontrada:")
                    for key, value in exif_info.items():
                        print(f"  - {key}: {value}")
                
                image_data_list.append((name, coords, image, exif_info))
            else:
                print(f"No se encontraron coordenadas GPS en {name}")
        
        if not image_data_list:
            print("No se encontraron imágenes con coordenadas GPS.")
            return
        
        # Generar mapas según tipo especificado
        files_generated = []
        
        # Si no se especifica tipo, generar todos
        if args.type == 0 or args.type == 1:
            html_file = f"{args.name}.html"
            file = create_folium_map(image_data_list, html_file, args.no_thumbnails)
            files_generated.append(file)
        
        if args.type == 0 or args.type == 2:
            gpx_file = f"{args.name}.gpx"
            file = create_gpx(image_data_list, gpx_file)
            files_generated.append(file)
        
        if args.type == 0 or args.type == 3:
            kml_file = f"{args.name}.kml"
            file = create_kml(image_data_list, kml_file)
            files_generated.append(file)
        
        print("\n¡Proceso completado con éxito!")
        print(f"Archivos generados: {', '.join(files_generated)}")
    
    finally:
        # Limpiar directorio temporal si existe
        if temp_dir and os.path.exists(temp_dir):
            print(f"Limpiando archivos temporales de {temp_dir}")
            shutil.rmtree(temp_dir)

if __name__ == "__main__":
    main()
