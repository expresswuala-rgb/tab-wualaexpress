# Tabuladores WualaExpress — App Android (Capacitor)

Esta carpeta contiene el proyecto Capacitor que envuelve la versión HTML
offline de la app en un APK de Android.

## Estructura
- `www/index.html` — la app web (un solo archivo, auto-contenida).
- `capacitor.config.json` — configuración de Capacitor.
- `package.json` — dependencias.

## Construir el APK en tu PC
Requisitos: Node.js 18+, Android Studio (con SDK y JDK 17).

```bash
cd android-app
npm install
npx cap add android          # solo la primera vez
npx cap sync android
npx cap open android         # abre Android Studio
# En Android Studio: Build > Build Bundle(s) / APK(s) > Build APK(s)
```

El APK queda en `android/app/build/outputs/apk/debug/`.

## Construir en la nube (GitHub Actions)
Sube este repositorio a GitHub y ejecuta el workflow
`.github/workflows/build-android.yml` (pestaña Actions > Run workflow).
El APK se genera y se descarga como artifact.

## Notas
- La app funciona 100% sin internet (el tabulador y el logo van incrustados).
- Importar CSV y exportar config funcionan desde el WebView.
- Las descargas se guardan en la carpeta de Descargas del dispositivo.
- Para actualizar el tabulador embebido, regenera `www/index.html` con
  `cd tabuladores && python3 build_html.py` y copia el resultado a `www/`.