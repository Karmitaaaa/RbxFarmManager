# RbxFarm Manager

Gestor de escritorio para Windows que organiza el farmeo en Roblox: cuentas cifradas, varias instancias
a la vez, anti-AFK, auto-reconexión, autoclicker y macros con perfiles. La interfaz imita la web clásica
de Roblox (barra azul, fondo gris, tarjetas blancas, avatares circulares) e incluye un tema oscuro.

**Stack:** Python 3.11+ con PySide6. Las librerías clave para automatizar Windows (pywin32, pynput, psutil)
son nativas de Python y el desarrollo es más rápido que con C#/WPF, sin perder una interfaz nativa.

> Solo usa automatización externa (ventanas, teclado y ratón de Windows). No inyecta código y no lee
> ni modifica la memoria del cliente de Roblox. Aun así, automatizar o usar cuentas alternativas puede ir
> contra los Términos de Uso de Roblox o de algunos juegos: úsalo bajo tu responsabilidad.

---

## Instalar (sin programar nada)

1. Ve a **[Releases](https://github.com/Karmitaaaa/RbxFarmManager/releases/latest)** y descarga
   `RbxFarmManager-Setup-x.y.z.exe`.
2. Ábrelo y sigue los pasos. Se instala solo para tu usuario (no pide permisos de administrador) y crea
   el acceso en el menú Inicio (y en el escritorio, si lo marcas).
3. Abre **RbxFarm Manager** e inicia sesión con tu cuenta de Roblox.

Para actualizar, instala la versión nueva encima: tus cuentas y ajustes se conservan. Para desinstalar,
usa «Agregar o quitar programas» de Windows (tus datos en `%APPDATA%\RbxFarmManager` no se borran).

> Como el instalador no está firmado digitalmente, Windows SmartScreen puede mostrar «Windows protegió
> su PC». Pulsa **Más información → Ejecutar de todas formas**.

## Requisitos (para ejecutar o compilar desde el código)

- Windows 10/11 y Python 3.11 o superior (probado con 3.14).
- Roblox Player instalado (también funciona si tienes Bloxstrap o Fishstrap).
- Para crear el instalador: [Inno Setup 6](https://jrsoftware.org/isinfo.php)
  (`winget install JRSoftware.InnoSetup`).

## Ejecutar desde el código

```bat
cd RbxFarmManager
py -3 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

> Si la carpeta está en una ruta muy larga, Windows puede dar el error *"El nombre del archivo o la
> extensión es demasiado largo"* al cargar `cryptography`. Mueve el proyecto a una ruta corta
> (por ejemplo `C:\RbxFarmManager`).

## Crear el .exe y el instalador

```bat
build.bat
```

El script crea el entorno virtual, instala las dependencias, genera el icono y ejecuta PyInstaller.
El resultado queda en la carpeta `Build`, al lado de la carpeta del proyecto:
`..\Build\RbxFarmManager\RbxFarmManager.exe`. Si Inno Setup 6 está instalado, también crea el instalador
`..\Build\Instalador\RbxFarmManager-Setup-<versión>.exe` (la versión sale del archivo `VERSION`).
Los archivos intermedios de PyInstaller van a `%TEMP%\RbxFarmManager-build`.

Para publicar una versión nueva: cambia `VERSION`, ejecuta `build.bat` y crea una Release en GitHub
con el instalador adjunto (`gh release create v1.0.1 ..\Build\Instalador\RbxFarmManager-Setup-1.0.1.exe`).
Comando de PyInstaller equivalente (desde la carpeta del proyecto):

```bat
pyinstaller --noconfirm --clean --windowed --name RbxFarmManager --icon assets\icon.ico ^
  --collect-submodules pynput --hidden-import win32timezone --distpath ..\Build main.py
```

---

## Estructura

```
RbxFarmManager/
├─ main.py                  Punto de entrada: logging, tema, desbloqueo del baúl, ventana
├─ requirements.txt
├─ build.bat                Empaquetado con PyInstaller
├─ tools/make_icon.py       Genera assets/icon.ico
├─ core/                    Lógica (sin interfaz)
│  ├─ models.py             Account, Instance, LaunchTarget y estados
│  ├─ roblox_api.py         Ticket de autenticación, verificar cookie, resolver enlaces /share
│  ├─ launcher.py           Enlaces de lanzamiento, mutex multi-instancia, límite de FPS, logs del cliente
│  ├─ instance_manager.py   Cola de lanzamiento + monitor de estado + auto-reconexión
│  ├─ reconnect.py          Espera progresiva, detección de desconexión, comprobación de internet
│  ├─ anti_afk.py           Anti-AFK con intervalo aleatorio
│  ├─ autoclicker.py        Autoclicker
│  ├─ macro.py              Grabador y reproductor de macros
│  └─ timing.py             Temporizador de 1 ms para tiempos exactos
├─ storage/
│  ├─ crypto.py             Fernet + scrypt, o Windows DPAPI
│  ├─ vault.py              Baúl cifrado de cuentas (importar/exportar)
│  ├─ config.py             Ajustes JSON con guardado automático
│  ├─ games.py              Perfiles de juego (games.json)
│  └─ profiles.py           Perfiles de macro (un JSON por macro, con su juego)
├─ ui/
│  ├─ theme.py              Hoja de estilos clásica (clara y oscura)
│  ├─ icons.py              Iconos vectoriales de Windows (Segoe Fluent Icons / MDL2)
│  ├─ widgets.py            Tarjetas de juego, avatares, cabeceras, estados vacíos, notificaciones
│  ├─ avatars.py            Caché de fotos de avatar e iconos de juegos
│  ├─ dialogs.py            Bienvenida, desbloqueo, editar cuenta, contraseñas
│  ├─ roblox_login.py       Inicio de sesión con la página oficial de Roblox (navegador integrado)
│  ├─ game_dialog.py        Crear/editar perfil de juego
│  ├─ main_window.py        Barra superior, menú lateral, bandeja, hotkeys
│  └─ tabs/                 Inicio, Juegos, Instancias, Anti-AFK, Autoclicker, Macros, Registro
└─ utils/
   ├─ winapi.py             SendInput, ventanas y foco (APIs públicas de Windows)
   ├─ hotkeys.py            Hotkeys globales (pynput)
   ├─ logger.py             Log rotativo a archivo; oculta cookies y tickets
   └─ paths.py              Rutas de datos
```

Los datos se guardan en `%APPDATA%\RbxFarmManager`:
`vault.dat` (cuentas cifradas), `games.json`, `settings.json`, `macros\*.json`, `avatars\` y
`logs\rbxfarm.log`.

---

## Uso

### Primera vez
- La app te da la bienvenida con un solo botón: **Iniciar sesión con Roblox**. Se abre la página
  oficial de Roblox dentro de la app y tú inicias sesión ahí, como en el navegador (usuario, contraseña,
  captcha y verificación en dos pasos los gestiona Roblox; RbxFarm nunca ve tu contraseña).
- Al entrar, la app recoge la sesión, comprueba con roblox.com de quién es, la guarda cifrada y te deja
  dentro con tu nombre y tu foto como **cuenta principal**.
- También puedes elegir «Usar la sesión que ya tengo abierta en Roblox» (solo pide tu nombre de usuario)
  o «Ahora no».
- No hay que crear ninguna contraseña: las cuentas se cifran con tu usuario de Windows (DPAPI) y la app
  se abre sin pedir nada. Si compartes el PC, en **Registro → Ajustes → «Pedir una contraseña al
  abrir»** puedes añadir una contraseña maestra (Fernet + scrypt).
- Si Google o Apple no funcionan dentro de la ventana, usa usuario y contraseña u «Otras opciones de
  inicio de sesión» (por ejemplo, el código por correo).

### Cómo se organiza
- **Menú lateral** siempre visible (☰ lo oculta): *Inicio*, *Juegos* e *Instancias* arriba;
  *Anti-AFK*, *Autoclicker* y *Macros* en «Automatización»; *Registro* en «Sistema». Cada sección
  empieza con una frase que explica para qué sirve.
- **Primeros pasos** en el Inicio: agregar una cuenta → crear un perfil de juego → grabar una macro
  (opcional) → pulsar «Jugar». Desaparece al completarlos o con «Ocultar».
- El botón verde **Jugar** del menú lateral abre el último juego que usaste.

### Perfiles de juego (pestaña Juegos)
- Cada perfil guarda: el juego (PlaceId o enlace, también servidor privado o `/share`), JobId opcional,
  las **cuentas que entran**, la **macro** y/o el **preset de autoclicker**, si se inician solos al
  entrar al servidor, y si usan anti-AFK y reconexión.
- Al pegar el enlace, «Detectar» busca en Roblox el **nombre y el icono** del juego.
- Las tarjetas muestran el icono, cuántas cuentas tiene, su macro y cuántas instancias están en juego.
  «Jugar» abre todas sus cuentas; «⋯» permite editar, duplicar, ver sus macros, cerrar sus instancias o
  eliminarlo. Doble clic en la tarjeta también lo edita.
- En el Inicio, «Continuar jugando» muestra tus perfiles ordenados por último uso.
- Si un perfil no tiene macro, cada cuenta usa la suya.

### 1. Cuentas (Inicio)
- **+ Agregar**: pulsa **Iniciar sesión con Roblox** y la cuenta se rellena sola (cada ventana empieza
  sin sesión, así puedes añadir varias cuentas seguidas). También puedes pegar la cookie a mano.
  Además: alias, etiquetas, notas, macro y autoclicker.
  - *Cookie .ROBLOSECURITY*: cada cuenta entra con la suya. «Verificar» comprueba que es válida y
    rellena el usuario. La cookie solo se envía a `roblox.com` para pedir el ticket de entrada.
  - *Sesión actual de Roblox*: abre el juego con la cuenta que ya tengas iniciada en la app de Roblox.
- Haz clic en los avatares (o marca las casillas de la tabla) para seleccionar varias cuentas.
- **Exportar/Importar** generan un archivo `.rbxvault` cifrado con una contraseña que tú eliges.
- La caja de búsqueda de la barra azul filtra por alias, usuario, notas y etiquetas.
- La portada te saluda según la hora («Buenos días», «Buenas tardes» o «Buenas noches») con el nombre
  y la foto de tu **cuenta principal**. Haz clic en la foto (o clic derecho en la tabla → «Marcar como
  cuenta principal») para elegir otra.
- Las fotos de avatar se descargan de roblox.com a partir del nombre de usuario (es un dato público) y se
  guardan en `%APPDATA%\RbxFarmManager\avatars`. Se actualizan una vez al día y puedes desactivarlas en
  Registro → Ajustes. Sin foto, se muestran las iniciales.

### 2. Instancias (multi-instancer)
- Lo normal es lanzar desde un perfil de juego. Para una prueba puntual, en **Inicio → Juego rápido**
  pega un PlaceId o un enlace (`/games/123…`, servidor privado con `privateServerLinkCode`,
  o `/share?code=…&type=Server`) y pulsa **Jugar con N cuentas** (las seleccionadas). «Guardar como
  perfil de juego» lo convierte en perfil.
- Las cuentas se abren una a una (con la espera configurada) para asociar cada proceso a su cuenta sin
  confusiones. La columna «Juego» muestra el perfil con el que se lanzó cada instancia.
- La pestaña Instancias muestra el estado (Lanzando, Abierto, En juego, Reconectando, Desconectado,
  Fallido…), PID, CPU, RAM, reintentos y botones para ver, ejecutar macro/autoclicker, reiniciar y cerrar.
- **Rendimiento**: límite de FPS (en `ClientAppSettings.json`), minimizar al abrir, prioridad baja y alias
  en el título de la ventana.
- La multi-instancia funciona reservando el mutex de cliente único de Roblox antes de abrirlo.
  Si Roblox ya estaba abierto antes que la app, ciérralo y vuelve a lanzar.

### 3. Anti-AFK
- Intervalo aleatorio (60–240 s por defecto) y acción: saltar, paso W/S, girar cámara, tecla
  personalizada o clic derecho en el centro.
- **Método «Foco breve»** (recomendado): enfoca la ventana ~0,3 s, envía la tecla y te devuelve el foco.
  Si estás usando el PC, espera unos segundos para no interrumpirte.
- **Método «Mensajes de ventana»**: no roba el foco, pero Roblox suele ignorar estos mensajes.
- Se activa o desactiva por instancia en la tabla de Instancias.

### 4. Auto-reconexión
- Detecta: proceso cerrado, ventanas de error o crash, desconexión del servidor (leyendo el archivo de log
  de texto que escribe Roblox en `%LOCALAPPDATA%\Roblox\logs`), juego que no termina de cargar y caída de
  internet.
- Reintenta con espera progresiva (inicial × 2 por intento, hasta la máxima) y un límite de intentos.
  Si se cae internet, espera a que vuelva sin gastar intentos.
- Cada evento aparece en el panel **Notificaciones** (abajo a la derecha), en «Eventos de conexión» y en
  el log con fecha y hora. Los errores también salen como aviso de Windows.

### 5. Autoclicker
- Botón izquierdo/derecho/medio, intervalo en ms con variación aleatoria, duración del clic,
  cantidad (infinito o limitada), en el cursor o en una posición fija («Capturar» la toma en 3 s).
- Hotkey global (por defecto **F6**) en modo **Alternar** o **Mantener**.
- Opcional: ventana destino; la enfoca y usa coordenadas relativas a esa ventana.
- Los **presets** guardan la configuración y se pueden asignar a cuentas.

### 6. Macros
- **Grabar** (F8) captura teclado y ratón con sus tiempos exactos; **Parar** (F9) la guarda como un perfil
  con fecha y hora; **Reproducir** (F10) reproduce el perfil seleccionado.
- Velocidad, repeticiones (0 = infinito), pausa entre bucles, ratón relativo (para girar la cámara) e
  instancia destino.
- Renombrar, duplicar, eliminar, importar y exportar macros (JSON).
- **Organizadas por juego:** el filtro de arriba muestra solo las macros de un juego (con su icono), y
  «Juego de esta macro» la mueve a otro. Si grabas con un juego elegido en el filtro, la macro se guarda
  dentro de ese juego. En el perfil de juego, sus macros aparecen primero con ★.
- Asigna una macro a un perfil de juego (recomendado) o a una cuenta. Con «Iniciarlos solos al entrar al
  servidor» arranca sola cuando la instancia entra al juego.

### 7. Registro y ajustes
- Log en vivo con filtro por nivel y botón para abrir la carpeta de logs.
- Tema clásico (claro) u oscuro, cerrar a la bandeja e iniciar minimizado.
- Cambiar la contraseña maestra o pasar a DPAPI.
- La configuración se guarda automáticamente cada 2 s.

---

## Notas técnicas y límites

- **Entradas reales compartidas:** anti-AFK, macros y autoclicker usan el teclado y el ratón del sistema,
  así que no pueden actuar a la vez. Un candado global las turna: una macro en bucle libera el turno entre
  repeticiones para que el anti-AFK de otras cuentas pueda actuar.
- **«En juego» y desconexiones** se deducen del log de texto del cliente. Si Roblox cambia el formato de
  sus logs, revisa `core/reconnect.py` (`JOIN_MARKERS`, `DISCONNECT_MARKERS`).
- **Límite de FPS:** se aplica a las instancias que se abran después del cambio. Bloxstrap/Fishstrap
  gestionan sus propios ajustes, así que configúralo también allí.
- El aviso de desconexión que Roblox muestra *dentro* del juego no es una ventana de Windows; por eso se
  detecta por el log y no por la ventana.
- Las cookies y los tickets nunca se escriben en el log (se sustituyen por `<cookie-oculta>`).

## Entrega por etapas

1. Estructura, almacenamiento cifrado y gestor de cuentas: `storage/`, `core/models.py`, `ui/tabs/accounts_tab.py`
2. Multi-instancer: `core/launcher.py`, `core/roblox_api.py`, `core/instance_manager.py`, `ui/tabs/instances_tab.py`
3. Anti-AFK y auto-reconexión: `core/anti_afk.py`, `core/reconnect.py`, `ui/tabs/afk_tab.py`
4. Autoclicker: `core/autoclicker.py`, `ui/tabs/clicker_tab.py`
5. Macros y hotkeys: `core/macro.py`, `utils/hotkeys.py`, `ui/tabs/macros_tab.py`
6. Interfaz, bandeja y empaquetado: `ui/main_window.py`, `ui/theme.py`, `build.bat`
