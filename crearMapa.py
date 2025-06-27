import os
import folium
from folium.plugins import MarkerCluster
from folium.plugins import HeatMap
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
from branca.element import Html
from folium import Map, TileLayer, FeatureGroup, Marker, LayerControl, CustomIcon, Html
from branca.element import Element
from folium.plugins import MarkerCluster, HeatMap

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

icon_create_function = """
function(cluster) {
    var count = cluster.getChildCount();
    var color = '#FFA500'; // orange

    if (count < 10) {
        color = '#FFA500'; // light orange
    } else if (count < 30) {
        color = '#FF7F50'; // coral
    } else if (count < 60) {
        color = '#FF4500'; // orange red
    } else {
        color = '#B22222'; // dark red
    }

    return new L.DivIcon({
        html: '<div style="background-color:' + color + '; border-radius: 50%; width: 40px; height: 40px; display: flex; align-items: center; justify-content: center;">' +
              '<span style="color:white; font-weight:bold;">' + count + '</span></div>',
        className: 'marker-cluster',
        iconSize: new L.Point(40, 40)
    });
}
"""

legend_html = """
<style>
/* Shared layout and styling */
#custom-legends, #cluster-legend, #heatmap-legend, .leaflet-control-layers {
    width: 240px !important;
    font-size: 16px;
}

/* Stack everything in a vertical column */
#custom-legends {
    position: fixed;
    top: 10px;
    right: 10px;
    z-index: 1000;
    display: flex;
    flex-direction: column;
    gap: 10px;
}

/* Match style for all boxes */
.legend-box, .leaflet-control-layers {
    background-color: white;
    border: 1px solid rgba(0,0,0,0.2);
    padding: 10px;
    border-radius: 8px;
    box-shadow: 0 1px 5px rgba(0,0,0,0.4);
}

/* Cluster visibility */
.marker-cluster-small, .marker-cluster-medium, .marker-cluster-large {
    opacity: 1;
    transition: opacity 0.5s;
}
</style>

<div id="custom-legends"></div>

<div id="cluster-legend" class="legend-box">
<b>Tamaño de grupo</b><br>
<div style='background:#FFA500;width:20px;height:20px;display:inline-block;margin-right:5px;'></div>Pequeño (1–9)<br>
<div style='background:#FF7F50;width:20px;height:20px;display:inline-block;margin-right:5px;'></div>Mediano (10–29)<br>
<div style='background:#FF4500;width:20px;height:20px;display:inline-block;margin-right:5px;'></div>Grande (30–59)<br>
<div style='background:#B22222;width:20px;height:20px;display:inline-block;margin-right:5px;'></div>Muy grande (60+)
</div>

<div id="heatmap-legend" class="legend-box">
<b>Densidad</b><br>
<div style="height: 15px; margin: 6px 0; background: linear-gradient(to right, blue, cyan, lime, yellow, orange, red); border: 1px solid #aaa;"></div>
<div style="display: flex; justify-content: space-between;"><span>Baja</span><span>Alta</span></div>
</div>

<script>
document.addEventListener("DOMContentLoaded", function () {
    const clusterLegend = document.getElementById("cluster-legend");
    const heatmapLegend = document.getElementById("heatmap-legend");
    const legendsContainer = document.getElementById("custom-legends");

    const leafletLayers = document.querySelector('.leaflet-control-layers');
    if (leafletLayers && legendsContainer) {
        legendsContainer.appendChild(leafletLayers);
    }

    legendsContainer.appendChild(clusterLegend);
    legendsContainer.appendChild(heatmapLegend);

    let map = null;
    for (let key in window) {
        if (window[key] instanceof L.Map) {
            map = window[key];
            break;
        }
    }
    if (!map) return;

    function updateLegendVisibility() {
        const checkboxes = document.querySelectorAll(".leaflet-control-layers-overlays input[type='checkbox']");
        clusterLegend.style.display = "none";
        heatmapLegend.style.display = "none";
        let heatmapEnabled = false;

        checkboxes.forEach(cb => {
            const label = cb.closest("label");
            if (!label || !cb.checked) return;
            if (label.textContent.includes("Fotos Geolocalizadas")) {
                clusterLegend.style.display = "block";
            }
            if (label.textContent.includes("Densidad")) {
                heatmapLegend.style.display = "block";
                heatmapEnabled = true;
            }
        });

        // Re-apply opacity to dynamically updated cluster elements
        const clusterElements = document.querySelectorAll(".marker-cluster");
        clusterElements.forEach(el => {
            el.style.opacity = heatmapEnabled ? 0.5 : 1;
        });
    }

    map.on("overlayadd overlayremove zoomend moveend", updateLegendVisibility);
    setTimeout(updateLegendVisibility, 500);
});
</script>

"""

def create_folium_map(image_data_list, output_file="images_map.html", include_heatmap=False):
    """Crea un mapa interactivo con Folium usando un lightbox fullscreen y aplica transparencia a los marker-clusters cuando la capa de densidad está activa."""
    # 0) Preparar icono custom
    icon = CustomIcon(
        icon_image='waste-icon.png',
        icon_size=(40, 40),
        icon_anchor=(15, 15)
    )

    # 1) Filtrar datos válidos
    valid = [img for img in image_data_list if img.get('coords') and img.get('id')]
    if not valid:
        return None

    avg_lat = sum(lat for lat, _ in (img['coords'] for img in valid)) / len(valid)
    avg_lon = sum(lon for _, lon in (img['coords'] for img in valid)) / len(valid)

    # 2) Crear mapa base
    m = Map(
        location=[avg_lat, avg_lon],
        zoom_start=12,
        tiles=None,
        prefer_canvas=False
    )
    TileLayer("Cartodb Positron", name="Mapa base").add_to(m)

    # 3) CSS para full-screen y sin scroll
    layout_css = """
    <style>
      html, body { margin: 0; padding: 0; width: 100%; height: 100%; overflow: hidden; }
      div[id^=\"html_\"] { width: auto !important; height: auto !important; position: static !important; }
      .folium-map, .leaflet-container { position: absolute !important; top: 0 !important; bottom: 0 !important; left: 0 !important; right: 0 !important; }
    </style>
    """
    m.get_root().html.add_child(Html(layout_css, script=True))

    # 4) Lightbox fullscreen
    lightbox = """
    <style>
      .img-modal { display: none; position: fixed; z-index: 10000; left: 0; top: 0; width: 100vw; height: 100vh;
                   background: rgba(0,0,0,0.8); align-items: center; justify-content: center; }
      .img-modal__content { max-width: 90vw; max-height: 90vh; box-shadow: 0 0 20px rgba(0,0,0,0.5);
                            border-radius: 4px; object-fit: contain; }
      .img-modal__close { position: absolute; top: 1rem; right: 1rem; font-size: 2rem; color: #fff; cursor: pointer; }
    </style>
    <div id="imgModal" class="img-modal">
      <span id="imgModalClose" class="img-modal__close">&times;</span>
      <img id="imgModalContent" class="img-modal__content" src="" alt="Foto" />
    </div>
    <script>
      const modal = document.getElementById("imgModal");
      const modalImg = document.getElementById("imgModalContent");
      const modalClose = document.getElementById("imgModalClose");
      function showImageLightbox(url) {
        const tmp = new Image();
        tmp.onload = () => { modalImg.src = url; modal.style.display = "flex"; };
        tmp.src = url;
      }
      modalClose.onclick = () => modal.style.display = "none";
      modal.onclick = e => { if (e.target === modal) modal.style.display = "none"; };
      document.addEventListener("keydown", e => { if (e.key === "Escape") modal.style.display = "none"; });
    </script>
    """
    m.get_root().html.add_child(Html(lightbox, script=True))

    # 5) Fotos con clustering
    fg_photos = FeatureGroup(name="📍 Fotos Geolocalizadas")
    mc = MarkerCluster(icon_create_function=icon_create_function).add_to(fg_photos)
    bindings = []
    for img in valid:
        lat, lon = img['coords']
        fid = img['id']
        url = f"https://drive.google.com/thumbnail?id={fid}&sz=w1600"
        mk = Marker(location=[lat, lon], icon=icon).add_to(mc)
        bindings.append((mk.get_name(), url))
    fg_photos.add_to(m)

    # 6) Capa heatmap opcional
    if include_heatmap:
        fg_heat = FeatureGroup(name="🔥 Densidad", show=False)
        HeatMap([img['coords'] for img in valid], radius=15, blur=10, min_opacity=0.4).add_to(fg_heat)
        fg_heat.add_to(m)

    # 7) Prepara líneas de binding para clicks
    binding_lines = "\n".join(
        f"{nm}.off('click').on('click', function(){{ showImageLightbox('{url}'); }});"
        for nm, url in bindings
    )

    # 8) Leyenda y control de capas en contenedor
    legend = f"""
    <style>
      #custom-legends {{ display: flex; flex-direction: column; gap: 10px;
                         position: fixed; top: 10px; right: 10px; z-index: 1000;
                         background: white; padding: 10px; border-radius: 8px;
                         box-shadow: 0 1px 5px rgba(0,0,0,0.4); }}
      #custom-legends .leaflet-control-layers {{ position: static !important;
                                               margin-bottom: 10px; width: auto !important;
                                               box-shadow: none !important; }}
      .legend-box {{ margin-bottom: 10px; }}
      .marker-cluster-small, .marker-cluster-medium, .marker-cluster-large {{ transition: opacity 0.5s; opacity: 1; }}
    </style>
    <div id="custom-legends">
      <div class="legend-box" id="cluster-legend">
        <b>Tamaño de grupo</b><br>
        <span style="background:#FFA500;width:12px;height:12px;display:inline-block"></span> 1–9<br>
        <span style="background:#FF7F50;width:12px;height:12px;display:inline-block"></span> 10–29<br>
        <span style="background:#FF4500;width:12px;height:12px;display:inline-block"></span> 30–59<br>
        <span style="background:#B22222;width:12px;height:12px;display:inline-block"></span> 60+<br>
      </div>
      <div class="legend-box" id="heatmap-legend">
        <b>Densidad</b><br>
        <div style="height:12px;background:linear-gradient(to right,blue,cyan,lime,yellow,orange,red)"></div>
        <div style="display:flex;justify-content:space-between"><small>Baja</small><small>Alta</small></div>
      </div>
    </div>
    <script>
      document.addEventListener("DOMContentLoaded", function() {{
        var container = document.getElementById("custom-legends");
        var lc = document.querySelector(".leaflet-control-layers");
        if (lc) container.prepend(lc);

        (function waitForMap() {{
          var m = Object.values(window).find(v => v instanceof L.Map);
          if (!m) return setTimeout(waitForMap, 50);
          function update() {{
            var fotosOn = false, densOn = false;
            document.querySelectorAll(".leaflet-control-layers-overlays input[type='checkbox']").forEach(cb => {{
              var lbl = cb.closest("label").textContent;
              if (cb.checked && /Fotos Geolocalizadas/.test(lbl)) fotosOn = true;
              if (cb.checked && /Densidad/.test(lbl)) densOn = true;
            }});
            document.getElementById("cluster-legend").style.display = fotosOn ? "block" : "none";
            document.getElementById("heatmap-legend").style.display = densOn ? "block" : "none";
            document.querySelectorAll(".marker-cluster").forEach(el => el.style.opacity = densOn ? 0.5 : 1);
          }}
          m.on("overlayadd overlayremove zoomend moveend", update);
          update();
          // Ejecutar binding de clicks
          {binding_lines}
        }})();
      }});
    </script>
    """
    m.get_root().html.add_child(Html(legend, script=True))

    # 9) Control de capas final y guardado
    LayerControl(collapsed=False).add_to(m)
    m.save(output_file)
    print(f"Mapa HTML generado: {output_file}")
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

def get_images_from_drive_public(file_id_list):
    """Carga imágenes desde Google Drive usando IDs públicos (sin API ni autenticación)"""
    images = []

    for file_id in file_id_list:
        try:
            url = f"https://drive.google.com/uc?export=download&id={file_id}"
            response = requests.get(url, stream=True)
            if response.status_code == 200:
                img_bytes = io.BytesIO(response.content)
                image = Image.open(img_bytes)
                images.append({
                    'name': f"{file_id}.jpg",
                    'image': image,
                    'id': file_id
                })
                print(f"Imagen cargada desde URL pública: {file_id}")
            else:
                print(f"Error al descargar imagen con ID {file_id}: HTTP {response.status_code}")
        except Exception as e:
            print(f"Error al procesar imagen {file_id}: {e}")

    print(f"Se cargaron {len(images)} imágenes desde enlaces públicos.")
    return images, None


def get_images_from_drive(folder_id):
    """Obtiene imágenes desde una carpeta de Google Drive (con paginación)"""
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

        # Consulta para obtener archivos en la carpeta especificada
        query = f"'{folder_id}' in parents and trashed=false"

        # Lista de archivos con paginación
        items = []
        page_token = None

        while True:
            response = service.files().list(
                q=query,
                fields="nextPageToken, files(id, name, mimeType)",
                pageSize=2,  # Máximo permitido
                pageToken=page_token
            ).execute()

            items.extend(response.get('files', []))
            page_token = response.get('nextPageToken', None)
            if not page_token:
                break

        if not items:
            print("No se encontraron archivos en la carpeta especificada.")
            return images, None

        # Crear directorio temporal para descargar imágenes
        temp_dir = tempfile.mkdtemp()
        print(f"Descargando imágenes a directorio temporal: {temp_dir}")

        # Filtrar y descargar solo archivos de imagen

        counter = 0

        for item in items:
            if counter >= 3:
                break
            counter += 1
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
                        'path': file_path,
                        'id': file_id
                    })
                    print(f"Imagen cargada desde Drive: {file_name}")

                except Exception as e:
                    print(f"Error al descargar o procesar {file_name}: {e}")

        print(f"Se cargaron {len(images)} imágenes desde Google Drive.")
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
                        help='Origen de las imágenes: 1 para directorio local, 2 para Google Drive')
    
    parser.add_argument('-d', '--directory', type=str, default='./imagenes',
                        help='Directorio local de imágenes (para source=1) o ID de carpeta de Google Drive (para source=2)')
    
    parser.add_argument('-n', '--name', type=str, default='images_map',
                        help='Nombre base para los archivos de mapa generados (sin extensión)')
    
    parser.add_argument('-t', '--type', type=int, choices=[1, 2, 3], default=0,
                        help='Tipo de mapa a generar: 1 para HTML, 2 para GPX, 3 para KML. Si no se especifica, genera los tres tipos')
    
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
        
        # Extraer datos GPS de cada imagen
        image_data_list = []
        for img_data in image_list:
            image = img_data['image']
            width, height = image.size
            img_data['width'] = width
            img_data['height'] = height
            name = img_data['name']
            
            exif_data = get_exif_data(image)
            gps_info = exif_data.get('GPSInfo', None)
            coords = get_decimal_coordinates(gps_info) if gps_info else None
            
            if coords:
                print(f"Coordenadas de {name}: {coords}")
                img_data['coords'] = coords
                image_data_list.append(img_data)
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
            file = create_folium_map(image_data_list, html_file, include_heatmap=True)
            files_generated.append(file)
        
        if args.type == 0 or args.type == 2:
            gpx_file = f"{args.name}.gpx"
            file = create_gpx(image_data_list, gpx_file)
            files_generated.append(file)
        
        if args.type == 0 or args.type == 3:
            kml_file = f"{args.name}.kml"
            file = create_kml(image_data_list, kml_file)
            files_generated.append(file)
        
        print("\n¡Proceso completado exitosamente!")
        print(f"Archivos generados: {', '.join(files_generated)}")
    
    finally:
        # Limpiar directorio temporal si existe
        if temp_dir and os.path.exists(temp_dir):
            print(f"Limpiando archivos temporales de {temp_dir}")
            shutil.rmtree(temp_dir)

if __name__ == "__main__":
    main()
